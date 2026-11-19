"""Multi-platform identity, problem.json, statements and migration; temporary data only."""

from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import archive
import common
import migrate
import providers
import records

CODE = "def fixture(values):\n    return len(values)\n"
H2H = "https://www.hack2hire.com/question-bank/companies/doordash/coding-questions/abc123/practice"


class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="coding-practice-platforms-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def save(self, problem, **kwargs):
        return archive.save_practice(self.root, problem, CODE, kwargs.pop("status", "learned"), kwargs.pop("notes", ""),
                                     kwargs.pop("date", "20261115"), kwargs.pop("difficulty", 3), **kwargs)

    def test_urls_are_detected_by_host(self):
        cases = {"https://leetcode.com/problems/two-sum/": "leetcode", "0001": "leetcode",
                 H2H: "hack2hire", "https://www.lintcode.com/problem/663/": "lintcode",
                 "https://neetcode.io/problems/two-integer-sum": "neetcode",
                 "https://www.hackerrank.com/challenges/ctci-ransom-note/problem": "hackerrank",
                 "https://app.codesignal.com/arcade/intro/level-1": "codesignal",
                 "https://www.geeksforgeeks.org/problems/kadanes-algorithm": "geeksforgeeks",
                 "https://www.1point3acres.com/bbs/thread-123456-1-1.html": "1point3acres",
                 "https://interviews.example.com/q/42": "other"}
        for value, name in cases.items():
            with self.subTest(value=value):
                self.assertEqual(providers.detect(value).name, name)
        self.assertIsNone(providers.detect("just some words"))

    def test_generic_site_needs_title_and_strips_tracking_parameters(self):
        problem = archive.resolve_problem(self.root, "auto", "https://www.lintcode.com/problem/663/?utm_source=x#top",
                                          title="Walls and Gates")
        self.assertEqual(problem["platform"], "lintcode")
        self.assertEqual(problem["url"], "https://www.lintcode.com/problem/663")
        self.assertEqual(problem["id"], "663")
        self.assertTrue(problem["key"].startswith("walls-and-gates-"))
        with self.assertRaises(common.ArchiveError):
            archive.resolve_problem(self.root, "lintcode", "https://leetcode.com/problems/two-sum/")
        with self.assertRaises(common.ArchiveError):
            archive.resolve_problem(self.root, "other", "http://insecure.example.com/q")

    def test_new_problem_writes_problem_json_statement_and_companies(self):
        problem = archive.resolve_problem(self.root, "hack2hire", H2H, title="Find the Nearest City")
        statement = "# Find the Nearest City\n\n- $1 \\le n \\le 10^4$\n"
        path = self.save(problem, title="Find the Nearest City", statement=statement, companies=["Databricks"])
        meta = json.loads((path.parent / "problem.json").read_text())
        self.assertEqual(meta["title"], "Find the Nearest City")
        self.assertEqual(meta["companies"], ["DoorDash", "Databricks"])
        self.assertEqual(meta["created"], "2026-11-15")
        readme = (path.parent / "README.md").read_text()
        self.assertEqual(records.block_content(readme, "statement"), statement.strip())
        self.assertEqual(archive.source_for(self.root, problem)["statement"], statement.strip())
        # The same URL with tracking noise reuses the folder; a new title renames it in place.
        again = archive.resolve_problem(self.root, "auto", H2H + "?utm_campaign=x")
        self.assertEqual(again["key"], problem["key"])
        second = self.save(again, title="Nearest City", date="20261116")
        self.assertEqual(second.parent, path.parent)
        self.assertEqual(records.load_problem(self.root, path.parent)["title"], "Nearest City")
        self.assertTrue((path.parent / "README.md").read_text().startswith("# Nearest City\n"))

    def test_statement_markers_are_rejected_before_anything_is_saved(self):
        problem = archive.resolve_problem(self.root, "manual", "", title="Design a Rate Limiter")
        with self.assertRaises(common.ArchiveError):
            self.save(problem, statement="<!-- practice:recall:end -->")
        self.assertFalse((self.root / "problems").exists())

    def test_manual_problems_match_by_title(self):
        first = archive.resolve_problem(self.root, "manual", "", title="Design a Rate Limiter")
        self.assertEqual(first["url"], "")
        path = self.save(first)
        again = archive.resolve_problem(self.root, "manual", "", title="  design a RATE limiter ")
        self.assertEqual(again["key"], first["key"])
        self.assertIn("Source: none (manual entry)", (path.parent / "README.md").read_text())
        with self.assertRaises(common.ArchiveError):
            archive.resolve_problem(self.root, "manual", "", title="")

    def test_parts_of_one_question_are_related_both_ways(self):
        part1 = archive.resolve_problem(self.root, "hack2hire", H2H + "?questionId=one", title="Part 1")
        part2 = archive.resolve_problem(self.root, "hack2hire", H2H + "?questionId=two", title="Part 2")
        self.assertNotEqual(part1["key"], part2["key"])
        first = self.save(part1, title="Part 1")
        second = self.save(part2, title="Part 2")
        self.assertEqual(records.load_problem(self.root, first.parent)["related"], ["hack2hire/" + part2["key"]])
        self.assertEqual(records.load_problem(self.root, second.parent)["related"], ["hack2hire/" + part1["key"]])

    def test_practices_pair_code_with_notes(self):
        problem = archive.resolve_problem(self.root, "manual", "", title="Notes fixture")
        self.save(problem, notes="First note\n\n### Not a practice heading\n")
        self.save(problem, status="independent", difficulty=1, notes="")
        folder = self.root / "problems/manual" / problem["key"]
        history = records.practices(folder)
        self.assertEqual([p["filename"] for p in history], ["20261115.py", "20261115_02.py"])
        self.assertEqual(history[0]["notes"], "First note\n\n### Not a practice heading")
        self.assertEqual(history[0]["code"], CODE)
        self.assertEqual((history[1]["status"], history[1]["difficulty"], history[1]["notes"]), ("independent", 1, ""))

    def test_pacific_date_without_a_tz_database(self):
        def fake_now(tz=None):
            return datetime(2026, 7, 1, 6, 30, tzinfo=timezone.utc) if tz else datetime(2026, 7, 1, 6, 30)
        with patch("zoneinfo.ZoneInfo", side_effect=LookupError("no tzdata")), \
                patch.object(common, "datetime", wraps=datetime) as clock:
            clock.now.side_effect = fake_now
            self.assertEqual(common.pacific_now().strftime("%Y%m%d %H:%M %z"), "20260630 23:30 -0700")
            clock.now.side_effect = lambda tz=None: datetime(2026, 12, 1, 7, 30, tzinfo=timezone.utc)
            self.assertEqual(common.pacific_now().strftime("%Y%m%d %H:%M %z"), "20261130 23:30 -0800")

    def test_slugs_and_lists(self):
        self.assertEqual(common.slugify("Dasher Payment Model Part 3 - Peak Pay Windows"), "dasher-payment-model-part-3-peak-pay-windows")
        self.assertEqual(common.slugify("限流器设计"), "problem")
        self.assertEqual(common.clean_list(" DoorDash, doordash ,, Databricks"), ["DoorDash", "Databricks"])


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="coding-practice-migrate-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def legacy(self, platform, key, title, url, statement=None):
        folder = self.root / "problems" / platform / key
        folder.mkdir(parents=True)
        problem = {"platform": platform, "key": key, "id": key.split("-")[0] if platform == "leetcode" else "",
                   "title": title, "url": url}
        if platform == "leetcode":
            problem["id"] = str(int(problem["id"]))
        readme = records.initial_readme(problem)
        readme = records.replace_block(readme, "recall", "AI-generated.\n\nPatterns: two pointers, array\n\n### 中文\n\n- 中\n\n### English\n\n- En")
        (folder / "README.md").write_text(readme + "\n### 2026-11-15 · learned\n\nCode: [20261115.py](20261115.py)\n\nMy notes:\n\nKeep me.\n")
        (folder / "20261115.py").write_text("# Practice: learned\n# Difficulty: 3\n" + CODE)
        if statement:
            cache = self.root / ".cache/sources" / platform / (key + ".json")
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"statement": statement, "provenance": migrate.USER_SUPPLIED}))
        return folder

    def run_migrate(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(migrate.main(list(args), root=self.root), 0)
        return output.getvalue()

    def test_dry_run_changes_nothing_then_apply_is_idempotent(self):
        legacy_key = "practice-" + common.short_hash(H2H + "?questionId=q1")
        h2h = self.legacy("hack2hire", legacy_key, "Dasher Payment Model Part 1", H2H + "?questionId=q1", "Full **statement**.")
        part2 = self.legacy("hack2hire", "practice-" + common.short_hash(H2H), "Dasher Payment Model Part 2", H2H)
        leet = self.legacy("leetcode", "0011-container-with-most-water", "Container With Most Water",
                           "https://leetcode.com/problems/container-with-most-water/")
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        plan = self.run_migrate()
        self.assertIn("Dry run", plan)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file() and p.name != "archive.lock"})
        self.run_migrate("--apply")
        new = self.root / "problems/hack2hire" / ("dasher-payment-model-part-1-" + legacy_key.split("-")[1])
        self.assertTrue(new.is_dir())
        self.assertFalse(h2h.exists())
        self.assertFalse(part2.exists())
        meta = json.loads((new / "problem.json").read_text())
        self.assertEqual(meta["companies"], ["DoorDash"])
        self.assertEqual(meta["tags"], ["two pointers", "array"])
        self.assertEqual(len(meta["related"]), 1)
        self.assertTrue(meta["related"][0].startswith("hack2hire/dasher-payment-model-part-2-"))
        readme = (new / "README.md").read_text()
        self.assertEqual(records.block_content(readme, "statement"), "Full **statement**.")
        self.assertIn("Keep me.", readme)
        self.assertEqual((new / "20261115.py").read_text(), "# Practice: learned\n# Difficulty: 3\n" + CODE)
        self.assertTrue((self.root / ".cache/sources/hack2hire" / (new.name + ".json")).exists())
        self.assertTrue((leet / "problem.json").exists())
        self.assertIn("up to date", self.run_migrate())
        # Archiving the same URL again lands in the migrated folder.
        again = archive.resolve_problem(self.root, "hack2hire", H2H + "?questionId=q1")
        self.assertEqual(again["key"], new.name)


if __name__ == "__main__":
    unittest.main()
