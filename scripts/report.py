#!/usr/bin/env python3
"""Print recorded progress without changing files or invoking a model."""

from collections import Counter
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def practices(root):
    rows = []
    for folder in sorted((root / "problems").glob("*/*")):
        found = []
        for code in folder.glob("*.py"):
            match = re.fullmatch(r"(\d{8})(?:_(\d+))?\.py", code.name)
            if not match:
                continue
            with code.open(encoding="utf-8") as stream:
                status = stream.readline().strip().removeprefix("# Practice: ")
                rating = re.fullmatch(r"# Difficulty: ([1-5])", stream.readline().strip())
            difficulty = int(rating[1]) if rating else None
            if status in ("independent", "improved", "learned"):
                found.append((match[1], int(match[2] or 1), status, code, difficulty))
        if found:
            found.sort()
            rows.append((folder, found))
    return rows


def difficulty_label(value):
    return "{}/5".format(value) if value is not None else "unrated (legacy)"


def problem_line(root, folder, entry):
    date, _, status, _, difficulty = entry
    return "- {} · {} · difficulty {} · [{}]({}/README.md)".format(
        date, status, difficulty_label(difficulty), folder.name, folder.relative_to(root).as_posix())


def report(root):
    rows = practices(root)
    count = sum(len(entries) for _, entries in rows)
    latest = Counter(entries[-1][2] for _, entries in rows)
    lines = ["# Recorded practice", "", "{} problems; {} practices.".format(len(rows), count),
             "User-reported practice statuses; no platform or mastery verification.", "",
             "Latest: {} independent, {} improved, {} learned.".format(
                 latest["independent"], latest["improved"], latest["learned"]), "",
             "## Review candidates", "",
             "Latest difficulty 4–5, or latest status improved/learned. Higher difficulty first; ties oldest practice.", ""]
    candidates = [(entries[-1], folder) for folder, entries in rows
                  if entries[-1][2] != "independent" or (entries[-1][4] or 0) >= 4]
    candidates.sort(key=lambda item: (-(item[0][4] or 0), item[0][0], item[0][1], item[1].name))
    lines += [problem_line(root, folder, entry) for entry, folder in candidates]
    if not candidates:
        lines.append("No review candidates recorded yet. This does not establish mastery.")
    lines += ["", "## Personally easiest candidates", "",
              "Latest status independent and difficulty 1–2; lower difficulty first.", ""]
    easiest = [(entries[-1], folder) for folder, entries in rows
               if entries[-1][2] == "independent" and entries[-1][4] in (1, 2)]
    easiest.sort(key=lambda item: (item[0][4], item[0][0], item[1].name))
    lines += [problem_line(root, folder, entry) for entry, folder in easiest]
    if not easiest:
        lines.append("No personally easiest candidates recorded yet.")
    lines += ["", "## All recorded problems", ""]
    for folder, entries in rows:
        date, _, status, _, difficulty = entries[-1]
        lines.append("- [{}]({}/README.md) · {} practices · latest {} / {} · difficulty {}".format(
            folder.name, folder.relative_to(root).as_posix(), len(entries), date, status, difficulty_label(difficulty)))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(report(ROOT), end="")
