# Coding Practice Tracker — User Guide

Long-term Python practice, with one final, understood, user-reported Accepted
solution per practice. Keep the work focused on solving problems.

Problems can come from LeetCode, Hack2Hire, LintCode, NeetCode, HackerRank,
CodeSignal, GeeksforGeeks, 1Point3Acres, any other website, or no website at
all (an interview question you only have in writing).

## Browser workspace

On macOS, run `./web.command` from this directory (or double-click it in
Finder). On Windows, double-click `web.cmd`. It starts a local service and
opens `http://127.0.0.1:8765/` in your browser. Keep that window open while
using the page; Ctrl-C stops the service after active archives finish.

Nothing needs to be installed besides Python 3.9+: no packages, no frontend
build, no database. The page is plain HTML, CSS and JavaScript modules served
from `web/`. Use `--port 8766` if the default port is occupied and
`--no-browser` to start without opening another tab.

### New practice

1. Paste the problem link. The platform is detected from the link; choose it
   from **Platform** to override, or choose **No link** for a question without
   a page. A LeetCode number or title slug (such as `0001` or `two-sum`) also
   works.
2. A preview says whether the problem is new or already archived, and how many
   practices it has. An archived problem gets another practice, never a second
   folder.
3. For a new non-LeetCode problem, enter the title shown on the page and paste
   the statement as Markdown. It is saved in the problem's README, so it
   travels with Git. LeetCode statements are looked up automatically; paste one
   only if the lookup fails. Companies are optional and comma-separated
   (Hack2Hire company pages fill this in from the link).
4. Paste your final AC code. The editor highlights Python; Tab/Shift-Tab
   indent, Enter keeps the indentation (and adds a level after `:`), and
   Cmd/Ctrl-/ toggles comments. Press Esc first if you want Tab to leave the
   editor.
5. Choose your practice status and a required personal difficulty from 1–5,
   add optional notes, and select **Archive practice**.

Code and notes are saved first; bilingual Quick recall is then generated in the
background. An existing complete recall is retained. The form is kept as a
draft in this browser tab until it is archived or you select **Clear form**.

### Problem page

Every saved problem has its own page (`#/p/<platform>/<folder>`), so it can be
bookmarked and the browser's Back button works.

- **Problem statement** shows the full Markdown statement (code blocks,
  tables and `$math$` are rendered) or the generated summary. **Edit
  statement** / **Add full statement** saves it into the README.
- **Practice history** lists every dated solution with its status, difficulty,
  highlighted code and your original notes.
- **Quick recall** is edited directly in Chinese and English. **Preview** shows
  the formatted result; **Save recall** (or Cmd/Ctrl-S) writes only the marked
  Quick recall block. **Regenerate** creates a new model draft for the latest
  solution without adding a practice; a statement pasted there is saved to the
  README first.
- **Edit details** changes the title, display number, companies, tags and
  related problems. Related links are kept on both problems; Part 1/2/3 of one
  Hack2Hire question are linked automatically.
- **Practice again** opens the form for this problem without re-entering its
  link.

Saves check the revision on disk. If another tab or a CLI refresh changed the
same recall, statement or details, your unsaved text stays in the editor and
the page asks you to reload. Leaving a page with unsaved edits asks first.

### Sidebar and review

The sidebar searches titles, notes, code, companies and tags, and filters by
platform, latest status, latest difficulty, company and tag. It can sort by
recent practice, difficulty, number of practices or title, and group by
platform, company, status or difficulty. The light/dark theme follows the
system unless you pick one at the bottom of the sidebar.

**Review** shows totals, a six-month practice calendar, the latest status and
difficulty distribution, review candidates and personally easiest problems,
using the same rules as `scripts/report.py` (below).

The service listens only on 127.0.0.1 and accepts changes from its own local
page. AI generation uses the same Codex CLI as the terminal workflow. Job status
is held in memory: after restarting the service, open the problem from the
sidebar. Duplicate requests in the same running service reuse their task ID
rather than adding another practice.

## Supported platforms

| Platform | Identify the problem by | Statement |
| --- | --- | --- |
| LeetCode (`leetcode.com`, `leetcode.cn`) | Number, title slug or URL | Looked up; paste if lookup fails |
| Hack2Hire | Exact question URL (`questionId` is kept) | Paste as Markdown |
| LintCode, NeetCode, HackerRank, CodeSignal, GeeksforGeeks, 1Point3Acres | Exact problem/post URL | Paste as Markdown |
| Other website | Any HTTPS URL | Paste as Markdown |
| No link | A title you choose | Paste as Markdown |

For non-LeetCode problems a title is required the first time. Tracking
parameters (`utm_*`, `ref`, …) and fragments are ignored when matching a link
to an archived problem. Pages are never scraped and no credentials or cookies
are collected. A new site needs only a small `Provider` class in
`scripts/providers/`.

## Start a practice archive in Terminal

Requirements: Python 3.9+, curl (built into macOS and Windows 10+), and a
logged-in Codex CLI. The archiver looks for `codex` on PATH, then for the CLI
bundled inside ChatGPT.app in `/Applications` or `~/Applications`. For another
installation, set `PRACTICE_CODEX` to its executable path (this explicit
override takes precedence). There are no Python packages to install. Archiving
writes locally; Git commits and pushes are separate actions. The tool does not
automatically commit, push, or submit code to a practice platform.

Run `./practice.command` (macOS) or `practice.cmd` (Windows), or
`python3 scripts/archive.py` directly. Follow the prompts:

1. Choose the platform by number (Enter for LeetCode).
2. Enter the problem number or URL. For a new non-LeetCode problem, enter its
   title and optionally paste the statement in Markdown, ending with `:end`.
3. Paste your final Python code, then enter `:end` on a separate line. Enter
   `:paste` instead to read code from the clipboard (macOS and Windows).
4. Choose the practice status below. You are reporting that this saved solution
   was Accepted and understood; the tool does not check your platform account.
5. Enter a required personal difficulty from `1` to `5` (5 is hardest).
6. Optionally enter personal notes in any language, ending with `:end`. Press
   Enter immediately to skip notes.

Non-interactive example for a site other than LeetCode:

```bash
python3 scripts/archive.py --platform auto \
  --problem https://www.lintcode.com/problem/663/ --title 'Walls and Gates' \
  --company Meta --statement-file statement.md \
  --code-file solution.py --status learned --difficulty 3
```

The terminal enables readline/libedit line editing when available. Tab inserts
indentation. Notes and code are not saved to readline history. `NO_COLOR=1`
disables the colored section headings.

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

```text
problems/<platform>/<folder>/
  problem.json    # identity: platform, title, URL, companies, tags, related
  README.md       # source, statement, short recall, dated original notes
  20261029.py     # status header + your code; never executed by the archiver
```

LeetCode folders are named `<number>-<slug>` (for example `0001-two-sum`);
other folders are `<title-slug>-<hash>` (for example
`find-the-nearest-city-0ba15fab`), where the hash comes from the link (or the
title for problems without a link). The folder name never changes after
creation, even if you rename the title.

`problem.json` holds identity only. Practice history stays in the dated code
files and the README; there is no separate progress database. The date uses
America/Los_Angeles (computed without a time-zone database where Python lacks
one, such as on Windows). A second practice on the same date uses
`20261029_02.py`; previous code is never overwritten.

README has marked blocks: `problem` (generated summary), `statement` (the full
statement you supplied), and `recall` (Quick recall). Leave their HTML comment
markers in place if editing the file manually. Everything outside those blocks,
including the personal notes, is retained when refreshing the AI summary. Quick
recall contains Simplified Chinese first, followed by English, with
corresponding bullets. Problem summaries and tooling documentation stay in
English; personal notes are preserved in their original language.

## Updating the tool

`tracker-manifest.json` records the installed version and a hash of every tool
file. When the browser service starts it checks GitHub's latest release for
this project at most once a day (cached in `.cache/update-check.json`; failed
checks retry after an hour). A newer release shows a banner with **What's new**,
**Update now** and **Later**. **Later** hides that version until you select
**Check for updates** at the bottom of the sidebar.

**Update now** downloads the tagged release archive over HTTPS with curl,
verifies every listed file against the release manifest, and then, under the
same lock the archiver uses:

- adds new tool files and replaces tool files that match a released version;
- removes files the release dropped, but only if you did not change them;
- keeps tool files you changed (for example a personalised README or
  AGENTS.md) and writes the release copy to `.cache/update/<version>/` for
  comparison;
- never writes `problems/`, `plans/`, `STYLE.md`, `.cache/` (except its own
  cache) or `.git/`, whatever a manifest lists;
- never commits, pushes, or runs Git.

Updating waits while an archive or recall generation is running. After it
finishes, **Restart now** stops the service and starts it again with the new
code (`web.command` and `web.cmd` run a small supervisor for this), and the
page reloads. If you started the service another way, stop it with Ctrl-C and
start it again. Line-ending differences (CRLF/LF) do not count as changes.

The terminal equivalent:

```bash
python3 scripts/update.py --check   # report only
python3 scripts/update.py           # list the changes, then ask
python3 scripts/update.py --yes     # install without asking
```

After installing, the terminal runs `scripts/migrate.py` as a dry run. Disable
the automatic check with `--no-update-check` or `PRACTICE_NO_UPDATE_CHECK=1`.
The check sends no practice data: it is one anonymous request to
`api.github.com`, and an install downloads from `codeload.github.com`.

A copy made before the updater existed (v0.1.0) has no manifest. Download the
updater once into its `scripts/` folder and run it; files identical to any
published version are replaced and others are kept:

```bash
curl -fsSL https://raw.githubusercontent.com/HelloLindo/coding-practice-tracker/main/scripts/update.py -o scripts/update.py
python3 scripts/update.py
```

On Windows, run the same commands with `py -3` in place of `python3`.

## Upgrading older records

Records created before `problem.json` existed (v0.1.0) still load, but upgrade
them once per checkout. The browser shows **Upgrade records** with the planned
changes for each folder; or use the terminal:

```bash
python3 scripts/migrate.py          # dry run: lists every planned change
python3 scripts/migrate.py --apply  # performs it; safe to repeat
```

It adds `problem.json` to every folder, renames Hack2Hire `practice-<hash>`
folders to `<title-slug>-<hash>` (keeping the hash), fills companies from the
link and tags from the recall Patterns line, moves statements you supplied from
the ignored `.cache/` into the README, and links parts of the same question.
Code files, notes and Quick recall are not changed. Review with `git status`
and commit the result; Git records the folder renames.

## Problem information and source access

The initial Two Sum identity and brief factual source paraphrase are bundled,
checked against its official page on 2026-10-29. They are not a completed
practice or a solution. No real practice is pre-populated.

For LeetCode numbers, the tool tries a cached/public catalogue and the
platform's question endpoint. These are unofficial interfaces that can change
or return 403. If a number cannot be resolved, paste its URL. If a new URL also
cannot be resolved, enter the display number and title shown on that page (the
browser asks for them; on the command line use `--id` and `--title`):

```bash
python3 scripts/archive.py --platform leetcode \
  --problem https://leetcode.com/problems/add-two-numbers/ \
  --id 2 --title 'Add Two Numbers'
```

When source text is unavailable, you may paste it or skip. The model must not
invent the problem's constraints. The README keeps its problem section pending
until source text is available. Raw retrieved LeetCode text is cached in the
ignored `.cache/`. A full statement saved between `practice:statement:start` and
`practice:statement:end` serves as source text for future refreshes; explicitly
supplied source text takes precedence for that refresh.

## Retry or refresh a summary

```bash
python3 scripts/archive.py --refresh problems/leetcode/0001-two-sum
```

This uses the latest dated solution and adds no practice. Pass a specific dated
`.py` file instead to summarize that version. For missing source content, supply
`--statement-file /path/to/statement.md` (it is also saved to the README). For
another available model, pass `--model MODEL_ID` or set `PRACTICE_MODEL`; the
default is `gpt-6-luna`. Availability depends on your CLI account; there is no
silent model substitution.

Use `--no-ai` to save without a model call. For file-based input, use
`--code-file`, `--notes-file`, `--status`, and the required `--difficulty 1`
through `--difficulty 5`. Refreshing an existing summary does not require a new
rating. An exit status of `2` means the practice was saved but AI enrichment
failed: use `--refresh`, not another archive invocation.

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
`learned`, or whose latest difficulty is 4–5, even if independent. They are
sorted by higher difficulty, then older practice date. Personally easiest
candidates require both latest status `independent` and difficulty 1–2. Legacy
unrated records remain visible but are not assumed to be easy. The browser's
**Review** page shows the same lists. An empty review list is not evidence of
mastery.

`AGENTS.md` defines how agents preserve original code and personal notes.
`STYLE.md` will hold user-approved style conventions, based on actual solutions.
`plans/` contains optional foundation and weekly company plans.

## First practice on a new machine

Solve Two Sum on LeetCode yourself, obtain Accepted, and make sure you understand
the saved solution. Archive it with problem `0001`. Check the dated code, chosen
status, original notes, generated problem facts, and recall bullets. Tests run
in temporary directories and do not count as a real practice.

## Personal Git synchronization

This public repository distributes the tool and starts with no practice history.
For personal use, follow the [private-copy setup](../README.md#keep-your-own-practice-records)
and point `origin` at your own private repository before pushing practice data.
The app never commits or pushes automatically. The checkout can live anywhere;
archive paths are relative to it.

```bash
git pull --ff-only
# Complete and archive your practice, then review the changes.
git add -A problems
git diff --cached --check
git commit -m "Record coding practice"
git push
```

After a tool update, commit the changed tool files separately, for example
with `git commit -am "Update Coding Practice Tracker to vX.Y.Z"` after
reviewing `git status`.

Keep `.cache/`, environment files, and account credentials out of Git. Configure
CLI login separately on each computer. Practices created on two computers for the
same problem and date can need Git conflict resolution; this is a file-based
journal, not a cross-device synchronization service. Keeping this repository
public does not make your local records public; pushing them to a public remote
does.

## Tooling verification

```bash
python3 -m unittest discover -s tests -v
python3 scripts/release.py --check
```

The tests use synthetic fixtures in temporary directories, including simulated
model/source failures, a legacy-record migration, and synthetic update
releases (tampered files, user edits, removed files, copies without a
manifest). They never execute learner
submissions. The integration uses
[Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
with `--output-schema`, `--ephemeral`, and a read-only sandbox.

Maintainers: after changing any shipped file, run `python3 scripts/release.py`
so `tracker-manifest.json` matches. To publish, start the next version with
`python3 scripts/release.py --version X.Y.Z`, merge it to `main`, tag the merge
`vX.Y.Z`, and publish a GitHub Release for that tag. Every hash ever listed
stays in the manifest, so unmodified copies of any earlier version update
cleanly.
