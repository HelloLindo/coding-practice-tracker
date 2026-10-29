# Coding Practice Tracker

This is the public tool distribution, not a personal practice journal. Keep the
shipped problems directory empty except for .gitkeep. Users keep their own
practice history in separate private workspaces.

Read README.md, docs/USER_GUIDE.md, STYLE.md, plans/current-week.md, and the relevant problem's
README and dated Python files before advising. Run `python3 scripts/report.py`
for the current recorded progress. Plans may be empty; never invent a target
company, a completed exercise, or an adopted curriculum.

- Keep maintenance minimal: one final, understood, user-reported AC solution
  and one user-selected status plus a required personal difficulty (1–5) per
  practice. Notes are optional. Difficulty describes the effort to understand
  and implement that practice's solution; never infer or backfill old ratings.
- `independent`: independently reached the target approach and AC.
- `improved`: independently solved the problem, then learned an optimization
  and rewrote the improved solution without looking at the reference.
- `learned`: did not independently solve it; understood a reference, closed it,
  then implemented the solution and obtained AC.
- These are user reports about that practice, not independently verified
  platform results or permanent mastery labels. Do not infer the learning
  process from polished final code or count imported history as new practice.
- Preserve dated code and original personal notes. Suggest changes separately;
  do not rewrite the learner's solutions unless explicitly asked.
- README problem and recall blocks are initially generated. The browser app
  also supports user edits to Quick recall; preserve those edits unless the
  user requests regeneration. Personal notes are appended verbatim. Do not
  silently replace personal notes with an AI paraphrase.
- The local web entry is web.command. Both web and terminal flows use the same
  dated solutions and README records; do not create a second progress store.
  Saving edited recall must change only its marked block, with revision checks
  against newer edits. Test web writes only in temporary repositories.
- Base problem facts on recorded source information, not model recollection.
  If source content is unavailable, leave it pending. Keep variants separate.
- Derive review suggestions from recorded practices, noting uncertainty.
  Consider both status and personal difficulty. Low difficulty after learning
  does not establish independent recall; independent but difficult practices
  can still need review. Prefer latest records and examine the trend.
  Do not invent personal mistakes, understanding, timings, or weak algorithms.
- STYLE.md contains only user-approved conventions. Propose additions with
  examples from the user's code before treating them as established style.
- Prefer hints and review during practice; provide full solutions on request.
- Use Chinese for discussion. Quick recall must contain Simplified Chinese
  first, then English, with corresponding bullets. Keep other generated
  explanations and tooling documentation in English. Preserve personal notes
  in their original language.
- This tool repository is intentionally public. Never add real personal
  practice records, notes, account credentials, caches, or private Git history.
  Review staged paths and diffs and run git diff --cached --check before pushing.
  Personal journal copies should use their own private remotes. Do not submit
  solutions to a practice platform or publish updates without authorization.

Tooling uses the Python standard library. Run `python3 -m unittest discover -s
tests -v` after behavioral changes. Test data belongs in temporary directories,
never in the real problems directory.
