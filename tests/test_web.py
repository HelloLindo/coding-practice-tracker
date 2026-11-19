"""Browser API and recall editing checks; all practice data is temporary."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import archive
import web_app

CODE = "def synthetic_fixture(values):\n    return len(values)\n"
NOTES = "Original personal notes.\n原始中文笔记。\n\n"
SUMMARY = {"problem_summary": "A source-based fixture summary.", "constraints": ["A source fact."],
           "quick_recall": {"zh": ["测试函数返回输入长度。"], "en": ["The fixture returns the input length."]},
           "tags": ["Synthetic fixture"]}


class WebFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="coding-practice-web-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = web_app.PracticeApp(self.root, model="test-model")
        self.addCleanup(self.app.close)
        self.problem = archive.resolve_problem(self.root, "leetcode", "0001")

    def fixture(self):
        path = archive.save_practice(self.root, self.problem, CODE, "learned", NOTES, "20261029", 4)
        archive.apply_summary(path, self.problem, SUMMARY)
        return path

    def payload(self, **changes):
        data = {"request_id": "test-request-001", "platform": "leetcode", "problem": "0001",
                "code": CODE, "status": "learned", "difficulty": 4, "notes": NOTES}
        data.update(changes)
        return data

    def wait_job(self, ident):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = self.app.job(ident)
            if job["state"] in ("ready", "partial", "failed", "conflict"):
                return job
            time.sleep(.01)
        self.fail("Background archive did not finish")

class WebSettingsTests(unittest.TestCase):
    def test_app_reads_workspace_settings(self):
        with tempfile.TemporaryDirectory(prefix="coding-practice-web-test-") as temp, \
                patch.dict(web_app.os.environ, {"PRACTICE_MODEL": "", "PRACTICE_EFFORT": ""}):
            root = Path(temp)
            (root / "settings.json").write_text('{"model": "gpt-6.2-sol", "reasoning_effort": "medium"}', encoding="utf-8")
            app = web_app.PracticeApp(root)
            self.addCleanup(app.close)
            self.assertEqual((app.model, app.effort), ("gpt-6.2-sol", "medium"))
            with patch.object(archive, "generate_summary", return_value=SUMMARY) as generate:
                job = app.submit({"request_id": "settings-request-1", "platform": "leetcode", "problem": "0001",
                                  "code": CODE, "status": "learned", "difficulty": 3, "notes": ""})
                deadline = time.monotonic() + 5
                while app.job(job["id"])["state"] not in ("ready", "partial", "failed", "conflict"):
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(.01)
            self.assertEqual(generate.call_args.args[4:], ("gpt-6.2-sol", 120, "medium"))


class WebTests(WebFixture):
    def test_search_reads_title_notes_and_all_code_files(self):
        self.fixture()
        archive.save_practice(self.root, self.problem, "def newer_version():\n    pass\n", "independent", "", "20261101", 2)
        for query in ("TWO SUM", "原始中文笔记", "SYNTHETIC_FIXTURE", "newer_version", "0001"):
            with self.subTest(query=query):
                self.assertEqual(len(self.app.listing(query)), 1)
        self.assertEqual(self.app.listing("no such content"), [])

    def test_manual_save_changes_only_recall_and_survives_a_new_app_instance(self):
        path = self.fixture()
        readme = path.parent / "README.md"
        before = readme.read_text(encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        old = self.app.problem("leetcode/0001-two-sum")
        result = self.app.save_recall({"key": old["key"], "revision": old["recall"]["revision"],
                                       "zh": "- 我自己的解释。\n- 保留 `代码`。", "en": "- My own explanation.\n- Keep `code`."})
        after = readme.read_text(encoding="utf-8")
        def without_recall(text):
            start, end = archive.marker("recall", "start"), archive.marker("recall", "end")
            a, rest = text.split(start, 1)
            return a + rest.split(end, 1)[1]
        self.assertEqual(without_recall(before), without_recall(after))
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
        self.assertEqual(len(list(path.parent.glob("*.py"))), 1)
        another = web_app.PracticeApp(self.root)
        try:
            restored = another.problem(old["key"])
            self.assertEqual(restored["recall"]["zh"], result["recall"]["zh"])
        finally:
            another.close()

    def test_stale_revision_cannot_overwrite_newer_manual_edits(self):
        self.fixture()
        old = self.app.problem("leetcode/0001-two-sum")
        data = {"key": old["key"], "revision": old["recall"]["revision"], "zh": "我的解释", "en": "My explanation"}
        self.app.save_recall(data)
        with self.assertRaises(web_app.WebError) as error:
            self.app.save_recall(dict(data, en="Stale replacement"))
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.app.problem(old["key"])["recall"]["en"], "My explanation")

    def test_new_notes_do_not_prevent_saving_recall_or_get_lost(self):
        code = self.fixture()
        old = self.app.problem("leetcode/0001-two-sum")
        archive.save_practice(self.root, self.problem, CODE, "independent", "New original note.", "20261101", 2)
        self.app.save_recall({"key": old["key"], "revision": old["recall"]["revision"], "zh": "解释", "en": "Explanation"})
        self.assertIn("New original note.", (code.parent / "README.md").read_text(encoding="utf-8"))

    def test_manual_save_rejects_empty_languages_and_reserved_markers(self):
        self.fixture()
        old = self.app.problem("leetcode/0001-two-sum")
        for value in ("", "<!-- practice:recall:end -->", "### English\nWrong heading"):
            with self.subTest(value=value), self.assertRaises(web_app.WebError):
                self.app.save_recall({"key": old["key"], "revision": old["recall"]["revision"], "zh": value, "en": "English"})

    def test_invalid_difficulty_and_syntax_are_rejected_before_any_save(self):
        for data in (self.payload(difficulty=None), self.payload(difficulty=True), self.payload(difficulty=6), self.payload(code="def broken(")):
            with self.assertRaises(web_app.WebError):
                self.app.submit(data)
        self.assertFalse((self.root / "problems").exists())

    def test_path_traversal_is_rejected(self):
        for key in ("../README.md", "leetcode/../../outside", "/tmp/anything", "leetcode/a/b"):
            with self.assertRaises(web_app.WebError):
                self.app.folder(key)

    def test_archive_generates_bilingual_recall_and_preserves_notes(self):
        with patch.object(archive, "generate_summary", return_value=SUMMARY):
            job = self.app.submit(self.payload())
            result = self.wait_job(job["id"])
        self.assertEqual(result["state"], "ready")
        saved = self.app.problem(result["key"])
        self.assertEqual(saved["difficulty"], 4)
        self.assertIn(SUMMARY["quick_recall"]["zh"][0], saved["recall"]["zh"])
        self.assertIn(NOTES, (self.app.folder(result["key"]) / "README.md").read_text(encoding="utf-8"))

    def test_hack2hire_title_is_saved_and_used_in_detail_and_sidebar(self):
        url = "https://www.hack2hire.com/question-bank/coding-questions/example/practice"
        statement = "A supplied source statement."
        with patch.object(archive, "generate_summary", return_value=SUMMARY) as generate:
            job = self.app.submit(self.payload(platform="hack2hire", problem=url,
                                               title="  Find the Nearest City  ", statement=statement))
            result = self.wait_job(job["id"])
        self.assertEqual(result["state"], "ready")
        key = result["key"]
        self.assertEqual(generate.call_args.args[0]["title"], "Find the Nearest City")
        readme = self.app.folder(key) / "README.md"
        self.assertTrue(readme.read_text(encoding="utf-8").startswith("# Find the Nearest City\n"))
        self.assertEqual(self.app.listing("Find the Nearest City")[0]["key"], key)
        self.assertEqual(self.app.problem(key)["title"], "Find the Nearest City")

        for request_id, title in (("rename-title", "Nearest City"), ("keep-title", "")):
            job = self.app.submit(self.payload(request_id=request_id, platform="hack2hire",
                                               problem=url, title=title))
            result = self.wait_job(job["id"])
            self.assertEqual(result["state"], "ready")
            self.assertEqual(result["key"], key)
            self.assertEqual(self.app.problem(key)["title"], "Nearest City")
        self.assertEqual(self.app.listing()[0]["count"], 3)

    def test_duplicate_request_id_does_not_create_a_second_practice(self):
        with patch.object(archive, "generate_summary", return_value=SUMMARY):
            first = self.app.submit(self.payload())
            second = self.app.submit(self.payload())
            self.wait_job(first["id"])
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(list((self.root / "problems").glob("*/*/*.py"))), 1)
        with self.assertRaises(web_app.WebError):
            self.app.submit(self.payload(notes="Different payload"))

    def test_model_failure_keeps_saved_practice_editable(self):
        with patch.object(archive, "generate_summary", side_effect=archive.ArchiveError("Unavailable")):
            job = self.app.submit(self.payload())
            result = self.wait_job(job["id"])
        self.assertEqual(result["state"], "partial")
        saved = self.app.problem(result["key"])
        self.assertIn(NOTES, (self.app.folder(result["key"]) / "README.md").read_text(encoding="utf-8"))
        changed = self.app.save_recall({"key": result["key"], "revision": saved["recall"]["revision"], "zh": "手写速记", "en": "Manual recall"})
        self.assertEqual(changed["recall"]["en"], "Manual recall")

    def test_regenerate_adds_no_practice(self):
        self.fixture()
        with patch.object(archive, "generate_summary", return_value=SUMMARY):
            job = self.app.submit({"request_id": "regenerate-001", "key": "leetcode/0001-two-sum"}, "generate")
            result = self.wait_job(job["id"])
        self.assertEqual(result["state"], "ready")
        self.assertEqual(len(list((self.root / "problems").glob("*/*/*.py"))), 1)

    def test_saved_full_statement_is_displayed_and_survives_regeneration(self):
        path = self.fixture()
        key = "leetcode/0001-two-sum"
        self.assertIn(SUMMARY["problem_summary"], self.app.problem(key)["statement"])
        readme = path.parent / "README.md"
        statement = "Full source statement.\n\n```text\nInput: [1, 2]\n```"
        readme.write_text(readme.read_text(encoding="utf-8") + "\n" + archive.marker("statement", "start")
                          + "\n" + statement + "\n" + archive.marker("statement", "end") + "\n", encoding="utf-8")
        self.assertEqual(self.app.problem(key)["statement"], statement)

        with patch.object(archive, "generate_summary", return_value=SUMMARY) as generate:
            job = self.app.submit({"request_id": "full-statement-001", "key": key}, "generate")
            self.assertEqual(self.wait_job(job["id"])["state"], "ready")
        self.assertEqual(generate.call_args.args[1]["statement"], statement)
        self.assertEqual(self.app.problem(key)["statement"], statement)

    def test_inflight_generation_cannot_overwrite_manual_save(self):
        self.fixture()
        started, finish = threading.Event(), threading.Event()
        def delayed(*args):
            started.set()
            self.assertTrue(finish.wait(3))
            return SUMMARY
        with patch.object(archive, "generate_summary", side_effect=delayed):
            job = self.app.submit({"request_id": "conflict-001", "key": "leetcode/0001-two-sum"}, "generate")
            try:
                self.assertTrue(started.wait(3))
                saved = self.app.problem("leetcode/0001-two-sum")
                self.app.save_recall({"key": saved["key"], "revision": saved["recall"]["revision"], "zh": "保留我的修改", "en": "Keep my edit"})
            finally:
                finish.set()
            result = self.wait_job(job["id"])
        self.assertEqual(result["state"], "conflict")
        self.assertEqual(self.app.problem(saved["key"])["recall"]["en"], "Keep my edit")
        self.assertIn("draft", result)

    def test_legacy_english_recall_remains_editable(self):
        path = self.fixture()
        readme = path.parent / "README.md"
        text = archive.replace_block(readme.read_text(encoding="utf-8"), "recall", "AI-generated from an older solution.\n\n- English-only legacy recall.")
        readme.write_text(text, encoding="utf-8")
        data = self.app.problem("leetcode/0001-two-sum")
        self.assertEqual(data["recall"]["zh"], "")
        self.assertIn("English-only", data["recall"]["en"])

    def test_listing_and_problem_include_identity_and_every_practice(self):
        self.fixture()
        archive.save_practice(self.root, self.problem, "def newer():\n    pass\n", "independent", "Second note.", "20261101", 2)
        item = self.app.listing()[0]
        self.assertEqual((item["platform_label"], item["count"], item["first_date"], item["date"]), ("LeetCode", 2, "20261029", "20261101"))
        detail = self.app.problem("leetcode/0001-two-sum")
        self.assertEqual([p["filename"] for p in detail["practices"]], ["20261029.py", "20261101.py"])
        self.assertEqual(detail["practices"][1]["notes"], "Second note.")
        self.assertEqual(detail["practices"][0]["code"], CODE)
        self.assertEqual(detail["tags"], ["Synthetic fixture"])

    def test_resolve_reports_existing_and_new_problems(self):
        self.fixture()
        found = self.app.resolve({"platform": "auto", "problem": "https://leetcode.com/problems/two-sum/"})
        self.assertTrue(found["exists"])
        self.assertEqual((found["key"], found["count"]), ("leetcode/0001-two-sum", 1))
        new = self.app.resolve({"platform": "auto", "problem": "https://www.hackerrank.com/challenges/fixture/problem"})
        self.assertEqual((new["platform"], new["exists"], new["needs_title"]), ("hackerrank", False, True))
        with self.assertRaises(web_app.WebError):
            self.app.resolve({"platform": "auto", "problem": "not a link"})

    def test_new_non_leetcode_problem_requires_a_title(self):
        url = "https://www.lintcode.com/problem/663/"
        job = self.app.submit(self.payload(platform="auto", problem=url))
        self.assertEqual(self.wait_job(job["id"])["state"], "failed")
        self.assertFalse((self.root / "problems").exists())
        with patch.object(archive, "generate_summary", return_value=SUMMARY):
            job = self.app.submit(self.payload(request_id="titled-001", platform="auto", problem=url,
                                               title="Walls and Gates", statement="# Walls and Gates\n\nFill rooms.",
                                               companies=["Meta"]))
            result = self.wait_job(job["id"])
        self.assertEqual(result["state"], "ready")
        detail = self.app.problem(result["key"])
        self.assertEqual((detail["title"], detail["id"], detail["companies"]), ("Walls and Gates", "663", ["Meta"]))
        self.assertEqual(detail["full_statement"], "# Walls and Gates\n\nFill rooms.")

    def test_practice_again_by_key_and_manual_problem(self):
        with patch.object(archive, "generate_summary", return_value=SUMMARY):
            job = self.app.submit(self.payload(platform="manual", problem="", title="Design a Rate Limiter"))
            key = self.wait_job(job["id"])["key"]
            job = self.app.submit({"request_id": "again-0001", "key": key, "code": CODE, "status": "independent",
                                   "difficulty": 2, "notes": ""})
            self.assertEqual(self.wait_job(job["id"])["key"], key)
        self.assertTrue(key.startswith("manual/design-a-rate-limiter-"))
        self.assertEqual(len(self.app.problem(key)["practices"]), 2)

    def test_meta_edit_renames_links_both_ways_and_checks_revision(self):
        self.fixture()
        other = archive.resolve_problem(self.root, "manual", "", title="Other fixture")
        archive.save_practice(self.root, other, CODE, "learned", "", "20261030", 3)
        other_key = "manual/" + other["key"]
        old = self.app.problem("leetcode/0001-two-sum")
        result = self.app.save_meta({"key": old["key"], "revision": old["meta_revision"], "title": "Two Sum (renamed)",
                                     "companies": "Amazon, amazon", "tags": ["hash map"], "related": [other_key]})
        self.assertEqual(result["title"], "Two Sum (renamed)")
        self.assertEqual(result["companies"], ["Amazon"])
        self.assertEqual([r["key"] for r in result["related"]], [other_key])
        self.assertTrue((self.app.folder(old["key"]) / "README.md").read_text(encoding="utf-8").startswith("# 0001. Two Sum (renamed)\n"))
        self.assertEqual([r["key"] for r in self.app.problem(other_key)["related"]], [old["key"]])
        with self.assertRaises(web_app.WebError) as error:
            self.app.save_meta({"key": old["key"], "revision": old["meta_revision"], "title": "Stale"})
        self.assertEqual(error.exception.status, 409)
        current = self.app.problem(old["key"])
        self.app.save_meta({"key": old["key"], "revision": current["meta_revision"], "related": []})
        self.assertEqual(self.app.problem(other_key)["related"], [])

    def test_statement_edit_is_saved_in_readme_with_revision_check(self):
        path = self.fixture()
        old = self.app.problem("leetcode/0001-two-sum")
        saved = self.app.save_statement({"key": old["key"], "revision": old["statement_revision"],
                                         "statement": "Full **statement**."})
        self.assertEqual(saved["full_statement"], "Full **statement**.")
        self.assertIn("Full **statement**.", (path.parent / "README.md").read_text(encoding="utf-8"))
        with self.assertRaises(web_app.WebError) as error:
            self.app.save_statement({"key": old["key"], "revision": old["statement_revision"], "statement": "x"})
        self.assertEqual(error.exception.status, 409)
        with self.assertRaises(web_app.WebError):
            self.app.save_statement({"key": old["key"], "revision": saved["statement_revision"],
                                     "statement": "<!-- practice:recall:start -->"})

    def test_regenerate_with_statement_persists_it(self):
        path = self.fixture()
        with patch.object(archive, "generate_summary", return_value=SUMMARY):
            job = self.app.submit({"request_id": "regen-statement", "key": "leetcode/0001-two-sum",
                                   "statement": "Pasted statement."}, "generate")
            self.assertEqual(self.wait_job(job["id"])["state"], "ready")
        self.assertEqual(archive.block_content((path.parent / "README.md").read_text(encoding="utf-8"), "statement"), "Pasted statement.")

    def test_report_lists_review_candidates_with_titles(self):
        self.fixture()
        data = self.app.report()
        self.assertEqual((data["problems"], data["practices"]), (1, 1))
        self.assertEqual(data["review"][0]["title"], "Two Sum")
        self.assertEqual(data["calendar"], {"20261029": 1})


class HttpTests(WebFixture):
    def setUp(self):
        super().setUp()
        self.server = web_app.make_server(self.app, 0)
        self.origin = "http://127.0.0.1:" + str(self.server.server_port)
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.02), daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def call(self, path, data=None, headers=None):
        body = json.dumps(data).encode() if data is not None else None
        values = {"X-Practice-Token": self.app.token, "Origin": self.origin, "Content-Type": "application/json"}
        values.update(headers or {})
        request = Request(self.origin + path, body, values)
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        return response.status, response.read(), response.headers

    def test_http_serves_local_page_and_token(self):
        status, body, headers = self.call("/")
        self.assertEqual(status, 200)
        self.assertIn(self.app.token.encode(), body)
        self.assertNotIn(b"__PRACTICE_TOKEN__", body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

    def test_http_rejects_wrong_origin_token_and_host(self):
        self.fixture()
        data = {"key": "leetcode/0001-two-sum", "revision": "wrong", "zh": "中文", "en": "English"}
        for headers in ({"Origin": "https://another-site.example"}, {"X-Practice-Token": "bad"}, {"Host": "attacker.example"}):
            status, _, _ = self.call("/api/recall", data, headers)
            self.assertEqual(status, 403)

    def test_http_manual_edit_round_trip(self):
        self.fixture()
        status, body, _ = self.call("/api/problem?key=leetcode%2F0001-two-sum")
        self.assertEqual(status, 200)
        old = json.loads(body)
        status, body, _ = self.call("/api/recall", {"key": old["key"], "revision": old["recall"]["revision"], "zh": "网页修改", "en": "Edited in the browser"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["recall"]["en"], "Edited in the browser")

    def test_http_serves_modules_but_not_other_files(self):
        status, body, headers = self.call("/js/main.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers["Content-Type"])
        for path in ("/../scripts/archive.py", "/js/../../README.md", "/web_app.py", "/js/missing.js"):
            status, _, _ = self.call(path)
            self.assertEqual(status, 404, path)

    def test_http_platforms_and_resolve(self):
        status, body, _ = self.call("/api/platforms")
        self.assertEqual(status, 200)
        names = [p["name"] for p in json.loads(body)["platforms"]]
        self.assertIn("hack2hire", names)
        self.assertIn("manual", names)
        status, body, _ = self.call("/api/resolve", {"platform": "auto", "problem": "https://neetcode.io/problems/x"})
        self.assertEqual((status, json.loads(body)["platform"]), (200, "neetcode"))


if __name__ == "__main__":
    unittest.main()
