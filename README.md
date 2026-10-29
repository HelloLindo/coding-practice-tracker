# Coding Practice Tracker

English | [简体中文](README_zh.md)

A local Python coding practice journal: save the final solution you understand and report as Accepted, preserve your original notes, and revisit the approach with bilingual Quick recall.

Use the browser workspace or terminal workflow with the Python standard library. No Python dependencies, frontend build, or database setup is needed. This public repository starts with **0 problems and 0 practices**, with no personal solution history included.

## Features

- **Archive practices**: use a LeetCode number or URL, or an exact Hack2Hire question URL. Archived solutions currently use Python.
- **Record the process**: choose `independent`, `improved`, or `learned`, plus a required personal difficulty from 1–5 for each practice. One Accepted submission does not establish permanent mastery.
- **Keep the originals**: dated solution files never overwrite earlier attempts, and personal notes are preserved verbatim.
- **Build recall**: generate Chinese and English reminders through your own Codex CLI, then edit, preview, and save them in the browser.
- **Review progress**: find review candidates based on the latest practice status, personal difficulty, and date.

## Quick start

Requirements: **macOS, Python 3.9+, and curl**. AI generation requires a separately installed, logged-in Codex CLI; no API key belongs in this project. The browser workflow attempts AI generation after saving. To archive without AI, use the terminal's `--no-ai` option.

```bash
git clone https://github.com/HelloLindo/coding-practice-tracker.git
cd coding-practice-tracker
python3 --version
./web.command
```

Your browser opens `http://127.0.0.1:8765/`. You can also double-click `web.command` in Finder. Keep the terminal open while using the app; press Ctrl-C to stop it.

1. Solve a problem on the practice platform, obtain Accepted, and make sure you understand the solution.
2. Enter the problem number or URL and paste your final code.
3. Choose a practice status and personal difficulty, and optionally add original notes.
4. Select **Archive practice**. Code and notes are saved first; Quick recall is generated in the background.
5. Edit the Chinese and English reminders, then select **Save recall** or press Cmd/Ctrl-S.

If generation fails, your saved practice remains available. Write recall manually or select **Regenerate** later. The tool does not verify Accepted through your platform account or execute pasted solutions.

```bash
# Use a different port if the default is occupied.
./web.command --port 8766

# Choose a model available to your CLI account; replace MODEL_ID.
./web.command --model MODEL_ID

# Archive interactively in the terminal without AI generation.
./practice.command --no-ai

# View progress without calling a model.
python3 scripts/report.py
```

The default model is `gpt-6-luna`. Model availability and CLI argument compatibility depend on your installation and account. Set the model with `--model` or `PRACTICE_MODEL`, and set a custom CLI executable with `PRACTICE_CODEX`. The browser has no separate switch to disable AI generation; use the terminal workflow above when the CLI is unavailable.

See the [full user guide](docs/USER_GUIDE.md) for file-based input, source lookup failures, summary retries, conflict handling, and the main options.

## Practice statuses

| Status | What happened during this practice |
| --- | --- |
| `independent` | Independently reached the target approach and obtained AC. |
| `improved` | Independently obtained AC, learned an optimization, then closed the reference and rewrote the improved solution to AC. |
| `learned` | Could not solve independently; understood a reference, closed it, then implemented the solution to AC. |

Personal difficulty rates the effort to understand and implement this solution, from 1 (easiest) to 5 (hardest). It is separate from the platform's difficulty. All practice statuses are user-reported.

## Where your data lives

```text
problems/<platform>/<problem>/
  README.md       # Source, recall, and dated original notes
  YYYYMMDD.py     # Practice status, difficulty, and final code
```

Another practice on the same date creates a new file such as `_02.py`. Archive dates currently use the `America/Los_Angeles` timezone. `plans/` holds optional plans, and `STYLE.md` holds conventions you approve; neither requires daily upkeep.

The browser service listens only on `127.0.0.1` and provides no public hosting or multi-user accounts. Project files stay on your machine. Source lookup contacts the relevant website, and AI generation sends the current problem's source text, code, and notes to your own Codex CLI, consuming your account's model allowance. Browser form drafts also persist in the current tab's session storage.

## Keep your own practice records

This public project distributes the tool. Create a separate **private repository** for your code and notes, and keep personal practices out of this project's public repository.

Select **Use this template → Create a new repository** on GitHub ([create a copy](https://github.com/new?template_name=coding-practice-tracker&template_owner=HelloLindo)), name your copy, choose **Private**, and clone your new repository. The tool and your records will then live in your own private workspace.

Alternatively, create an empty private GitHub repository such as `my-coding-practice`, download and extract this project's ZIP, and run these commands in the extracted directory:

```bash
git init -b main
git add .
git commit -m "Initialize personal coding practice workspace"
# Replace this URL with your own new private repository.
git remote add origin https://github.com/YOUR_USERNAME/my-coding-practice.git
git push -u origin main
```

If you already cloned this project, keep its history and change the remotes:

```bash
git remote rename origin upstream
git remote add origin https://github.com/YOUR_USERNAME/my-coding-practice.git
git push -u origin main
```

Before pushing, confirm that `origin` points to your own private repository and review the files being uploaded. The app never runs Git operations automatically. If you retained `upstream`, you can pull tool updates from it; preserve your own records, plans, and style conventions when merging.

## Scope and limitations

- Designed primarily for macOS. The code uses Unix file locks; native Windows is unsupported. Validate other systems for your own workflow.
- Source interfaces may change or reject requests. Supply an exact URL, title, and pasted statement when needed. Missing source content stays pending rather than receiving invented constraints.
- Review AI output yourself. There is no built-in judge, solution collection, or multi-user synchronization service.
- Keep credentials, restricted problem statements, employer code, and other people's private materials out of commits.

## Development and contributions

```bash
python3 -m unittest discover -s tests -v
```

Tests use temporary directories and synthetic fixtures. Issues and improvements are welcome; see [Contributing](CONTRIBUTING.md). Report security concerns privately as described in the [security policy](SECURITY.md).

## License

The project's tool code and documentation use the [MIT License](LICENSE), allowing use, modification, and redistribution with the copyright and license notice retained.

Third-party names, problems, and platform content belong to their respective rights holders and are not licensed under MIT by this project. This project is not affiliated with or endorsed by LeetCode or Hack2Hire. You decide how to share your own solution code and notes.
