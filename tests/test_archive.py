"""Behavioral checks using temporary, synthetic practice records only."""

from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import archive
import report

CODE = "def fixture(values):\n    return len(values)\n"
NOTES = "我的原始 notes。\n\n## A heading\nKeep `code` and spacing.\n"
SUMMARY = {"problem_summary": "Return positions of a pair that reaches the target.",
           "constraints": ["Use distinct positions."],
           "quick_recall": {"zh": ["此测试函数返回输入长度。"],
                            "en": ["This synthetic fixture returns the input length."]},
           "tags": ["Synthetic fixture"]}


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="coding-practice-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.problem = archive.resolve_problem(self.root, "leetcode", "0001")

    def save(self, status="independent", date="20261029", notes=NOTES, difficulty=3):
        return archive.save_practice(self.root, self.problem, CODE, status, notes, date, difficulty)

    def cli(self, *extra):
        code = self.root / "fixture.txt"
        code.write_text(CODE, encoding="utf-8")
        notes = self.root / "notes.txt"
        notes.write_text(NOTES, encoding="utf-8")
        args = ["--platform", "leetcode", "--problem", "0001", "--status", "learned",
                "--code-file", str(code), "--notes-file", str(notes), "--date", "20261029", "--difficulty", "3"]
        with patch.object(archive, "ROOT", self.root), patch.object(archive, "catalogue", return_value=[self.problem]), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return archive.main(args + list(extra))

    def test_same_day_archives_never_overwrite_and_notes_remain_original(self):
        first = self.save("learned")
        second = self.save("improved", notes="A second original note.")
        self.assertEqual(first.name, "20261029.py")
        self.assertEqual(second.name, "20261029_02.py")
        self.assertEqual(first.read_text(), "# Practice: learned\n# Difficulty: 3\n" + CODE)
        text = (first.parent / "README.md").read_text()
        self.assertIn(NOTES, text)
        self.assertIn("A second original note.", text)
        self.assertIn("20261029_02.py", text)

    def test_repeated_practice_preserves_trailing_blank_lines_in_original_notes(self):
        notes = "Keep these blank lines.\n\n\n\n"
        first = self.save(notes=notes)
        self.save(notes="Next practice.")
        self.assertIn(notes, (first.parent / "README.md").read_text())

    def test_refresh_selects_numeric_same_day_sequence(self):
        folder = self.root / "fixtures"
        folder.mkdir()
        for name in ("20261029.py", "20261029_99.py", "20261029_100.py", "helper.py"):
            (folder / name).write_text(CODE)
        self.assertEqual(archive.practice_files(folder)[-1].name, "20261029_100.py")

    def test_manual_identity_fallback_requires_platform_url(self):
        result = archive.manual_identity("https://leetcode.com/problems/add-two-numbers/", "0002", "Add Two Numbers")
        self.assertEqual(result["key"], "0002-add-two-numbers")
        with self.assertRaises(archive.ArchiveError):
            archive.manual_identity("https://example.com/problems/add-two-numbers/", "2", "Wrong source")

    def test_summary_updates_only_generated_sections(self):
        code = self.save()
        readme = code.parent / "README.md"
        with readme.open("a") as stream:
            stream.write("\nMy manually written extra section.\n")
        with patch.object(archive, "generate_summary", return_value=SUMMARY):
            archive.update_summary(code, self.problem, self.problem, CODE, NOTES, "fake", 1)
        text = readme.read_text()
        self.assertIn(NOTES, text)
        self.assertIn("My manually written extra section.", text)
        self.assertIn("Synthetic fixture", text)
        self.assertNotIn("AI summary pending.", text)
        self.assertIn("[20261029.py](20261029.py)", text)

    def test_recall_is_chinese_first_then_english_without_changing_personal_notes(self):
        code = self.save()
        with patch.object(archive, "generate_summary", return_value=SUMMARY):
            archive.update_summary(code, self.problem, self.problem, CODE, NOTES, "fake", 1)
        text = (code.parent / "README.md").read_text()
        self.assertLess(text.index("### 中文"), text.index("### English"))
        self.assertIn(SUMMARY["quick_recall"]["zh"][0], text)
        self.assertIn(SUMMARY["quick_recall"]["en"][0], text)
        self.assertIn(NOTES, text)

    def test_missing_empty_or_misaligned_recall_language_is_rejected(self):
        for recall in ({"zh": ["中文"]}, {"zh": [], "en": ["English"]},
                       {"zh": ["中文"], "en": ["One", "Two"]},
                       {"zh": ["中文"], "en": [""]}):
            with self.subTest(recall=recall), self.assertRaises(archive.ArchiveError):
                archive.validate_summary(dict(SUMMARY, quick_recall=recall))

    def test_missing_source_cannot_promote_model_recollection_to_problem_facts(self):
        code = self.save()
        with patch.object(archive, "generate_summary", return_value=SUMMARY):
            archive.update_summary(code, self.problem, {}, CODE, "", "fake", 1)
        text = (code.parent / "README.md").read_text()
        self.assertIn("Source summary pending.", text)
        self.assertNotIn(SUMMARY["problem_summary"], text)

    def test_difficulty_is_mandatory_and_rejects_values_outside_integer_scale(self):
        for difficulty in (None, 0, 6, True, "3", 2.5):
            with self.subTest(difficulty=difficulty), self.assertRaises(archive.ArchiveError):
                self.save(difficulty=difficulty)
        self.assertFalse((self.root / "problems").exists())

    def test_difficulty_is_saved_in_code_header_and_dated_readme_entry(self):
        code = self.save(difficulty=5)
        self.assertTrue(code.read_text().startswith("# Practice: independent\n# Difficulty: 5\n"))
        self.assertIn("Personal difficulty: 5/5", (code.parent / "README.md").read_text())

    def test_missing_noninteractive_difficulty_fails_without_archiving(self):
        with patch.object(archive, "ROOT", self.root), patch.object(archive.sys.stdin, "isatty", return_value=False), \
                redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            archive.main(["--platform", "leetcode", "--problem", "0001", "--status", "independent"])
        self.assertEqual(error.exception.code, 2)
        self.assertFalse((self.root / "problems").exists())

    def test_blank_and_invalid_difficulty_choices_are_reprompted(self):
        with patch("builtins.input", side_effect=["", "0", "6", "2.5", "4"]), redirect_stdout(io.StringIO()):
            value = archive.choose("Difficulty: ", {str(i): i for i in range(1, 6)})
        self.assertEqual(value, 4)

    def test_bad_python_or_date_creates_no_practice(self):
        for code, date in (("def broken(", "20261029"), (CODE, "20260230"), (CODE, "2026102")):
            with self.assertRaises(archive.ArchiveError):
                archive.save_practice(self.root, self.problem, code, "learned", NOTES, date, 3)
        self.assertFalse((self.root / "problems").exists())

    def test_no_ai_archives_without_invoking_source_or_model(self):
        with patch.object(archive, "generate_summary") as model, patch.object(archive, "source_for") as source:
            self.assertEqual(self.cli("--no-ai"), 0)
        model.assert_not_called()
        source.assert_not_called()
        self.assertIn(NOTES, next((self.root / "problems").glob("*/*/README.md")).read_text())

    def test_model_failure_preserves_practice_and_refresh_does_not_add_one(self):
        with patch.object(archive, "source_for", return_value=self.problem), \
                patch.object(archive, "generate_summary", side_effect=archive.ArchiveError("offline")):
            self.assertEqual(self.cli(), 2)
        folder = self.root / "problems/leetcode/0001-two-sum"
        self.assertEqual(len(list(folder.glob("*.py"))), 1)
        with patch.object(archive, "ROOT", self.root), patch.object(archive, "source_for", return_value=self.problem), \
                patch.object(archive, "generate_summary", return_value=SUMMARY), redirect_stdout(io.StringIO()):
            self.assertEqual(archive.main(["--refresh", str(folder)]), 0)
        self.assertEqual(len(list(folder.glob("*.py"))), 1)
        self.assertIn(NOTES, (folder / "README.md").read_text())

    def test_repeat_practice_with_complete_readme_skips_all_network_and_model_calls(self):
        code = self.save()
        with patch.object(archive, "generate_summary", return_value=SUMMARY):
            archive.update_summary(code, self.problem, self.problem, CODE, "", "fake", 1)
        with patch.object(archive, "source_for") as source, patch.object(archive, "generate_summary") as model:
            self.assertEqual(self.cli(), 0)
        source.assert_not_called()
        model.assert_not_called()

    def test_source_failure_leaves_recoverable_pending_information(self):
        problem = dict(self.problem, statement="")
        with patch.object(archive, "fetch", side_effect=archive.ArchiveError("403")):
            source = archive.source_for(self.root, problem)
        self.assertEqual(source["statement"], "")
        supplied = archive.source_for(self.root, problem, "Exact user-supplied source constraints.")
        self.assertEqual(supplied["statement"], "Exact user-supplied source constraints.")

    def test_number_mapping_uses_frontend_display_number(self):
        catalogue = {"stat_status_pairs": [{"stat": {
            "question_id": 999, "frontend_question_id": 42,
            "question__title_slug": "fixture-problem", "question__title": "Fixture Problem"}}]}
        with patch.object(archive, "fetch", return_value=json.dumps(catalogue)):
            problem = archive.resolve_problem(self.root, "leetcode", "0042")
        self.assertEqual(problem["key"], "0042-fixture-problem")

    def test_existing_manual_identity_is_resolvable_by_number_offline(self):
        self.save()
        with patch.object(archive, "catalogue", return_value=[]), patch.object(archive, "fetch") as fetch:
            loaded = archive.resolve_problem(self.root, "leetcode", "0001")
        self.assertEqual(loaded["id"], "1")
        fetch.assert_not_called()

    def test_refresh_cannot_target_another_repository(self):
        with self.assertRaises(archive.ArchiveError):
            archive.load_problem(self.root, self.root / "elsewhere")

    def test_hack2hire_different_source_paths_do_not_merge(self):
        first = archive.resolve_problem(self.root, "hack2hire", "https://www.hack2hire.com/company-a/rate-limiter")
        second = archive.resolve_problem(self.root, "hack2hire", "https://www.hack2hire.com/company-b/rate-limiter")
        self.assertNotEqual(first["key"], second["key"])

    def test_high_difficulty_independent_practice_is_still_a_review_candidate(self):
        self.save("independent", difficulty=5)
        text = report.report(self.root)
        review = text.split("## Review candidates", 1)[1].split("## Personally easiest candidates", 1)[0]
        self.assertIn("0001-two-sum", review)
        self.assertIn("difficulty 5/5", review)

    def test_low_difficulty_learned_practice_is_not_treated_as_independently_easy(self):
        self.save("learned", difficulty=1)
        text = report.report(self.root)
        easiest = text.split("## Personally easiest candidates", 1)[1].split("## All recorded problems", 1)[0]
        self.assertNotIn("0001-two-sum", easiest)
        self.save("independent", date="20261105", difficulty=2)
        easiest = report.report(self.root).split("## Personally easiest candidates", 1)[1].split("## All recorded problems", 1)[0]
        self.assertIn("0001-two-sum", easiest)

    def test_old_records_without_rating_remain_unrated_and_unchanged(self):
        folder = self.root / "problems/leetcode/0001-two-sum"
        folder.mkdir(parents=True)
        code = folder / "20261029.py"
        original = "# Practice: independent\n" + CODE
        code.write_text(original)
        text = report.report(self.root)
        self.assertIn("unrated (legacy)", text)
        self.assertIn("No personally easiest candidates", text)
        self.assertEqual(code.read_text(), original)

    def test_report_uses_latest_practice_not_historical_failure(self):
        self.save("learned")
        self.save("independent", date="20261105")
        text = report.report(self.root)
        self.assertIn("1 problems; 2 practices", text)
        self.assertIn("1 independent, 0 improved, 0 learned", text)
        self.assertIn("No review candidates recorded yet", text)

    def test_codex_contract_and_schema_validation(self):
        def fake_run(command, **kwargs):
            self.assertIn("--ephemeral", command)
            self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
            self.assertNotEqual(kwargs["cwd"], str(self.root))
            self.assertIn("source_statement", kwargs["input"])
            Path(command[command.index("--output-last-message") + 1]).write_text(json.dumps(SUMMARY))
            return subprocess.CompletedProcess(command, 0, "", "")
        with patch.object(archive, "find_codex", return_value="codex"), \
                patch.object(archive.subprocess, "run", side_effect=fake_run):
            result = archive.generate_summary(self.problem, self.problem, CODE, NOTES, "fake", 1)
        self.assertEqual(result, SUMMARY)

    def test_cli_on_path_takes_precedence_over_app_bundle(self):
        with patch.dict(os.environ, {"PRACTICE_CODEX": ""}), \
                patch.object(archive.shutil, "which", return_value="/custom/bin/codex"), \
                patch.object(archive, "codex_app_paths") as bundles:
            self.assertEqual(archive.find_codex(), "/custom/bin/codex")
        bundles.assert_not_called()

    def test_cli_is_found_in_app_bundle_when_terminal_path_omits_it(self):
        bundled = self.root / "My Apps/ChatGPT.app/Contents/MacOS/codex"
        bundled.parent.mkdir(parents=True)
        bundled.write_text("#!/bin/sh\nexit 0\n")
        bundled.chmod(0o755)
        with patch.dict(os.environ, {"PRACTICE_CODEX": ""}), \
                patch.object(archive.shutil, "which", return_value=None), \
                patch.object(archive, "codex_app_paths", return_value=(bundled,)):
            self.assertEqual(archive.find_codex(), str(bundled))

    def test_explicit_cli_override_is_respected(self):
        cli = self.root / "custom-codex"
        cli.write_text("#!/bin/sh\nexit 0\n")
        cli.chmod(0o755)
        with patch.dict(os.environ, {"PRACTICE_CODEX": str(cli)}):
            self.assertEqual(archive.find_codex(), str(cli))

    def test_invalid_explicit_cli_override_does_not_silently_fall_back(self):
        with patch.dict(os.environ, {"PRACTICE_CODEX": str(self.root / "missing-cli")}):
            with self.assertRaisesRegex(archive.ArchiveError, "PRACTICE_CODEX"):
                archive.find_codex()

    def test_cli_missing_everywhere_has_actionable_error(self):
        with patch.dict(os.environ, {"PRACTICE_CODEX": ""}), \
                patch.object(archive.shutil, "which", return_value=None), \
                patch.object(archive, "codex_app_paths", return_value=()):
            with self.assertRaisesRegex(archive.ArchiveError, "PRACTICE_CODEX"):
                archive.find_codex()

    def test_bad_model_output_does_not_touch_notes(self):
        code = self.save()
        before = (code.parent / "README.md").read_text()
        with patch.object(archive, "generate_summary", side_effect=archive.ArchiveError("bad JSON")):
            with self.assertRaises(archive.ArchiveError):
                archive.update_summary(code, self.problem, self.problem, CODE, NOTES, "fake", 1)
        self.assertEqual((code.parent / "README.md").read_text(), before)


if __name__ == "__main__":
    unittest.main()
