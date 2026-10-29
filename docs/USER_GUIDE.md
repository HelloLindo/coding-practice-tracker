# Coding Practice Tracker — User Guide

Long-term Python practice, with one final, understood, user-reported Accepted
solution per practice. Keep the work focused on solving problems.

## Browser workspace

From this directory, run `./web.command` (or double-click it in Finder). It
starts a local service and opens `http://127.0.0.1:8765/` in your browser. Keep
that terminal open while using the page; Ctrl-C stops the service after active
archives finish. No package installation, frontend build, or database is needed.
Use `./web.command --port 8766` if the default port is occupied; `--no-browser`
starts the service without opening another tab. The CLI entry below remains
available.

1. Paste a problem number or URL and your final understood AC code.
2. Choose your practice status, then a required personal difficulty from 1–5.
3. Add optional original notes and select **Archive practice**.
4. The page reports when code and notes are saved, then generates bilingual
   Quick recall in the background. An existing complete recall is retained.
5. Edit the Chinese and English text directly. Select **Preview** to read the
   formatted result, then **Save recall** (or Cmd/Ctrl-S) to write your edits.

The generated recall is initially saved automatically. Manual saves replace
only the marked Quick recall block in the problem's README, keeping the code,
status, difficulty, problem facts, and original notes unchanged. Chinese stays
before English. Simple Markdown bullets and inline code are supported in the
preview; HTML is shown as text. Both language fields are required for a manual
save, but manual writing is not limited to the model's five-bullet format.

Select any saved problem in the sidebar to reopen and edit its recall without
adding a practice. **Reload saved** reloads the version on disk. **Regenerate**
creates a new model draft for the latest solution without adding a practice;
optional source text for that selected problem is available below the editor.
If generation fails, the saved practice remains available for manual recall
writing or a later regeneration.

The editor checks the recall revision before saving. If another tab or a CLI
refresh changed it, your unsaved text stays in the editor and the page asks you
to reload the saved version. A background generation also keeps manual changes
made while it was running. Unsaved navigation prompts prevent accidental loss
of recall edits; the new-practice form is kept in this tab's session storage
until archived or explicitly cleared with New practice.

The service listens only on 127.0.0.1 and accepts changes from its own local
page. It serves repository files locally; AI generation uses the same Codex CLI
as the terminal workflow. There is no hosted website or remote database. Job
status is held in memory: after restarting the service, select a saved problem
from the sidebar to reopen it. Duplicate requests in the same running service
reuse their task ID rather than adding another practice.

## Start a practice archive in Terminal

Requirements: macOS, Python 3.9+, and curl. A logged-in Codex CLI is
needed for AI generation; terminal archives can use `--no-ai` without it. The archiver
looks for `codex` on PATH, then for the CLI bundled inside ChatGPT.app in
`/Applications` or `~/Applications`. You do not need to install another CLI or
change your shell PATH if that app is installed. For another installation, set
`PRACTICE_CODEX` to its executable path (this explicit override takes precedence).
There are no Python packages to install. Archiving writes locally; Git commits
and pushes are separate actions. The tool does not automatically commit, push,
or submit code to a practice platform.

Open Terminal in this directory and run:

```bash
./practice.command
```

You can also double-click `practice.command` in Finder, or run
`python3 scripts/archive.py` directly. Follow the prompts:

1. Press Enter for LeetCode, or enter `2` for Hack2Hire.
2. Enter a LeetCode display number (such as `0001`) or the exact problem URL.
3. Paste your final Python code, then enter `:end` on a separate line. On macOS,
   enter `:paste` instead to read code from the clipboard.
4. Choose the practice status below. You are reporting that this saved solution
   was Accepted and understood; the tool does not check your platform account.
5. Enter a required personal difficulty from `1` to `5` (5 is hardest).
   This rates how hard it was to understand and implement this solution.
6. Optionally enter personal notes in any language, ending with `:end`. Press
   Enter immediately to skip notes.

The terminal enables readline/libedit line editing when available, so left/right
arrows can move within the current input line. Tab inserts indentation. Notes
and code are not saved to readline history. This is still a line-oriented input
flow: submitted lines are not a full multiline editor. Use `:paste` for code
already on the clipboard. `NO_COLOR=1` disables the colored section headings.

The script saves the code and original notes first. On the first practice it
then calls Codex to generate a short problem summary and recall bullets. Later
practices append notes and keep the existing recall unless you request a refresh.
The model may need up to two minutes; failures do not discard the practice.

| Choice | Status | What happened during this practice |
| --- | --- | --- |
| 1 | `independent` | Independently reached the target approach and AC. |
| 2 | `improved` | Independently got AC, learned an optimization, then closed the reference and rewrote the improved solution to AC. |
| 3 | `learned` | Could not solve independently; understood a reference, closed it, then implemented the solution to AC. |

These describe this practice's process, not permanent mastery or whether the
final saved code is optimal. Intermediate failed submissions need not be stored.

Personal difficulty is separate from practice status:

| Rating | Personal effort |
| --- | --- |
| 1 | Understanding and implementation were easy. |
| 2 | Once the approach was clear, understanding and implementation were straightforward. |
| 3 | Required deliberate reasoning; some details were easy to get wrong. |
| 4 | Understanding or implementation was hard and required repeated reasoning. |
| 5 | Took substantial effort to understand and complete; prioritize consolidation. |

All ratings still require an understood, user-reported AC solution. Each new
practice requires its own rating. The tool writes `# Difficulty: N` below the
status header and `Personal difficulty: N/5` in that date's README entry. Old
records remain unchanged and appear as `unrated (legacy)`; no rating is guessed.

## Files produced

For example, your real Two Sum practice will create:

```text
problems/leetcode/0001-two-sum/
  README.md       # source, short recall, dated original personal notes
  20261029.py     # status header + your code; never executed by the archiver
```

The date uses America/Los_Angeles. A second practice on the same date uses
`20261029_02.py`; previous code is never overwritten. Personal notes are in the
README, not duplicated in code or a separate progress database.

README has two marked generated blocks. Leave their HTML comment markers in
place if editing the file manually. Everything outside those blocks, including
the personal notes, is retained when refreshing the AI summary. The quick recall
links to the exact code it describes; after changing approaches, refresh it.
Quick recall contains Simplified Chinese first, followed by English, with
corresponding bullets. Problem summaries and tooling documentation stay in
English; personal notes are preserved in their original language.

## Problem information and source access

The initial Two Sum identity and brief factual source paraphrase are bundled,
checked against its official page on 2026-10-29. They are not a completed practice
or a solution. No real practice is pre-populated.

For other LeetCode numbers, the tool tries a cached/public catalogue and the
platform's question endpoint. These are unofficial interfaces that can change
or return 403. If a number cannot be resolved, paste its URL. If a new URL also
cannot be resolved, the interactive flow asks for the display number and title
shown on that page. You can also provide its identity explicitly:

```bash
python3 scripts/archive.py --platform leetcode \
  --problem https://leetcode.com/problems/add-two-numbers/ \
  --id 2 --title 'Add Two Numbers'
```

Hack2Hire requires an exact question URL; unrelated paths with the same title
get separate folders. Readable page extraction is best-effort; authenticated
pages may require you to paste the statement once. No credentials or browser
cookies are collected. Only HTTPS source URLs are used.

When source text is unavailable, you may paste it or skip. The model must not
invent the problem's constraints. The README keeps its problem section pending
until source text is available. Raw retrieved text is cached in ignored `.cache/`;
the README contains a short summary and the source link rather than a tutorial.

## Retry or refresh a summary

From this directory, run:

```bash
python3 scripts/archive.py --refresh problems/leetcode/0001-two-sum
```

This uses the latest dated solution and adds no practice. Pass a specific dated
`.py` file instead to summarize that version. For missing source content, supply
`--statement-file /path/to/copied-statement.txt`. For another available model,
pass `--model MODEL_ID` or set `PRACTICE_MODEL`; the default is `gpt-6-luna`.
Availability depends on your CLI account; there is no silent model substitution.

Use `--no-ai` to save without a model call. For file-based input, use
`--code-file`, `--notes-file`, `--status`, and the required `--difficulty 1` through
`--difficulty 5`. Refreshing an existing summary does not require a new rating.
An exit status of `2` means the
practice was saved but AI enrichment failed: use `--refresh`, not another
archive invocation. Other errors are printed with their context.

Codex runs non-interactively in an isolated temporary directory with read-only
tool permissions. It receives only this problem's source text, code and current
notes. It returns structured JSON; the Python script writes the README. It uses
the CLI's saved authentication and consumes the account's model allowance.
No account credentials belong in this repository.

## Progress and agents

```bash
python3 scripts/report.py
```

This prints a local report without a model call or writing another tracker.
Review candidates include problems whose latest practice is `improved` or
`learned`, or whose latest difficulty is 4–5, even if independent. They are sorted
by higher difficulty, then older practice date. Personally easiest candidates
require both latest status `independent` and difficulty 1–2. Legacy unrated
records remain visible but are not assumed to be easy. Agents can inspect notes,
code, and rating trends to suggest algorithms or writing patterns to review.
An empty review list is not evidence of mastery.

`AGENTS.md` defines how agents preserve original code and personal notes.
`STYLE.md` will hold user-approved style conventions, based on actual solutions.
`plans/` contains optional foundation and weekly company plans. There is no
obligation to write a daily review, log timings, or maintain a progress table.

## First practice on a new machine

Solve Two Sum on LeetCode yourself, obtain Accepted, and make sure you understand
the saved solution. Run `./practice.command` with problem `0001`. Check the dated
code, chosen status, original notes, generated problem facts, and recall bullets.
Tests run in temporary directories and do not count as a real practice.
Confirm that the local workflow works on the new machine before relying on it.

## Personal Git synchronization

This public repository distributes the tool and starts with no practice history.
For personal use, follow the [private-copy setup](../README.md#保存自己的练习记录)
and point `origin` at your own private repository before pushing practice data.
The app never commits or pushes automatically.

```bash
git pull --ff-only
# Complete and archive your practice, then review the changes.
git add problems
git diff --cached --check
git commit -m "Record coding practice"
git push
```

Keep `.cache/`, environment files, and account credentials out of Git. Configure
CLI login separately on each Mac. Practices created on two Macs for the same
problem and date can need Git conflict resolution; this is a file-based journal,
not a cross-device synchronization service. Keeping this repository public does
not make your local records public; pushing them to a public remote does.

## Tooling verification

```bash
python3 -m unittest discover -s tests -v
```

The tests use synthetic fixtures in temporary directories, including simulated
model/source failures. They never execute learner submissions. The integration uses the installed Codex CLI with `--output-schema`, `--ephemeral`, and a read-only sandbox.
