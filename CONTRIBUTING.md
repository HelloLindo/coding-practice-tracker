# Contributing

Issues and pull requests are welcome. Describe the problem, expected behavior,
OS/Python version, and minimal reproduction. Use synthetic code and notes;
remove personal data, credentials, private URLs, and restricted source content.

Keep Python standard-library-only and preserve the file-based journal format.
Save code and original notes before optional AI enrichment, never execute saved
learner submissions, and preserve manually edited recall with revision checks.
Changes must not silently rewrite existing practice history or notes.

Run the existing checks before sending a pull request:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/release.py --check
git diff --check
```

If you change a shipped file, run `python3 scripts/release.py` so the update
manifest matches. The `--check` runs only in this repository; in a user's
workspace copy the manifest describes the installed release and is skipped. The updater must never write `problems/`, `plans/`,
`STYLE.md`, `settings.json`, `.cache/` or `.git/`, and must keep tool files users changed.

Add focused regression coverage for behavior changes. All test archives belong
in temporary directories, never the shipped `problems/` directory. CI uses
synthetic fixtures and does not require a Codex account or API credentials.

By contributing, you agree that your contribution may be distributed under the
project's MIT license. Do not include material you lack permission to share.
