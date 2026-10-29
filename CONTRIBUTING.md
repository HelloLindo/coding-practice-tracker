# Contributing

Issues and pull requests are welcome. Describe the problem, expected behavior,
macOS/Python version, and minimal reproduction. Use synthetic code and notes;
remove personal data, credentials, private URLs, and restricted source content.

Keep Python standard-library-only and preserve the file-based journal format.
Save code and original notes before optional AI enrichment, never execute saved
learner submissions, and preserve manually edited recall with revision checks.
Changes must not silently rewrite existing practice history or notes.

Run the existing checks before sending a pull request:

```bash
python3 -m unittest discover -s tests -v
git diff --check
```

Add focused regression coverage for behavior changes. All test archives belong
in temporary directories, never the shipped `problems/` directory. CI uses
synthetic fixtures and does not require a Codex account or API credentials.

By contributing, you agree that your contribution may be distributed under the
project's MIT license. Do not include material you lack permission to share.
