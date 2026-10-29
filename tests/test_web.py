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

class WebTests(WebFixture):
    def test_manual_save_changes_only_recall_and_survives_a_new_app_instance(self):
        path = self.fixture()
        readme = path.parent / "README.md"
        before = readme.read_text()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        old = self.app.problem("leetcode/0001-two-sum")
        result = self.app.save_recall({"key": old["key"], "revision": old["recall"]["revision"],
                                       "zh": "- 我自己的解释。\n- 保留 `代码`。", "en": "- My own explanation.\n- Keep `code`."})
        after = readme.read_text()
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
        self.assertIn("New original note.", (code.parent / "README.md").read_text())

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
        self.assertIn(NOTES, (self.app.folder(result["key"]) / "README.md").read_text())

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
        self.assertIn(NOTES, (self.app.folder(result["key"]) / "README.md").read_text())
        changed = self.app.save_recall({"key": result["key"], "revision": saved["recall"]["revision"], "zh": "手写速记", "en": "Manual recall"})
        self.assertEqual(changed["recall"]["en"], "Manual recall")

    def test_regenerate_adds_no_practice(self):
        self.fixture()
        with patch.object(archive, "generate_summary", return_value=SUMMARY):
            job = self.app.submit({"request_id": "regenerate-001", "key": "leetcode/0001-two-sum"}, "generate")
            result = self.wait_job(job["id"])
        self.assertEqual(result["state"], "ready")
        self.assertEqual(len(list((self.root / "problems").glob("*/*/*.py"))), 1)

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
        text = archive.replace_block(readme.read_text(), "recall", "AI-generated from an older solution.\n\n- English-only legacy recall.")
        readme.write_text(text)
        data = self.app.problem("leetcode/0001-two-sum")
        self.assertEqual(data["recall"]["zh"], "")
        self.assertIn("English-only", data["recall"]["en"])


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


if __name__ == "__main__":
    unittest.main()
