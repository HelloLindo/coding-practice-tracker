"""Problem folders on disk: problem.json identity, README blocks, practice entries.

problem.json holds identity only (platform, title, URL, companies, tags,
related problems). Practice history stays in the dated code files and the
README, so there is still a single record of progress.
"""

import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

import providers
from common import ArchiveError, atomic_write, clean_list, read_json

BLOCK = "<!-- practice:{name}:{edge} -->"
META_NAME = "problem.json"
META_FIELDS = ("platform", "key", "id", "slug", "title", "url", "companies", "tags", "related", "created")
ENTRY = re.compile(r"(?m)^### (\d{4}-\d{2}-\d{2}) · (independent|improved|learned)[ \t]*$")
CODE_NAME = re.compile(r"(\d{8})(?:_(\d+))?\.py")
STATUSES = ("independent", "improved", "learned")


# --- README blocks -----------------------------------------------------
def marker(name, edge):
    return BLOCK.format(name=name, edge=edge)


def block_content(text, name):
    _, start, rest = text.partition(marker(name, "start"))
    content, end, _ = rest.partition(marker(name, "end"))
    return content.strip() if start and end else ""


def replace_block(text, name, content):
    start, end = marker(name, "start"), marker(name, "end")
    if text.count(start) != 1 or text.count(end) != 1:
        raise ArchiveError("README's {} markers were changed; original notes are preserved.".format(name))
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    return before + start + "\n" + content.strip() + "\n" + end + after


def check_statement(statement):
    if not isinstance(statement, str) or len(statement) > 100000:
        raise ArchiveError("The statement is too long.")
    if "<!-- practice:" in statement:
        raise ArchiveError("Remove README markers (<!-- practice:… -->) from the statement.")
    return statement.strip()


def set_statement(text, statement):
    """Store the full statement in README so it travels with Git."""
    statement = check_statement(statement)
    if marker("statement", "start") in text:
        return replace_block(text, "statement", statement)
    end = marker("problem", "end")
    if text.count(end) != 1:
        raise ArchiveError("README's problem markers were changed; cannot add the statement.")
    block = ("\n\n### Full statement\n\n" + marker("statement", "start") + "\n" + statement
             + "\n" + marker("statement", "end"))
    return text.replace(end, end + block, 1)


def statement_revision(text):
    return hashlib.sha256(block_content(text, "statement").encode()).hexdigest()


def heading(problem, title=None):
    prefix = providers.get(problem["platform"]).heading_prefix(problem)
    return "# " + prefix + (title if title is not None else problem["title"])


def set_heading(text, problem):
    return re.sub(r"(?m)^# .+$", lambda _: heading(problem), text, count=1)


def initial_readme(problem):
    source = problem["url"] or "none (manual entry)"
    return (heading(problem) + "\n\nSource: " + source + "\n\n"
            "## Problem\n\n" + marker("problem", "start") + "\n"
            "Source summary pending. Do not infer constraints from the solution.\n"
            + marker("problem", "end") + "\n\n## Quick recall\n\n"
            + marker("recall", "start") + "\nAI summary pending.\n"
            + marker("recall", "end") + "\n\n## Practice notes\n")


# --- problem.json ------------------------------------------------------
def normalize_meta(problem):
    meta = {"schema": 1}
    for field in META_FIELDS:
        value = problem.get(field, [] if field in ("companies", "tags", "related") else "")
        if field in ("companies", "tags"):
            value = clean_list(value or [])
        elif field == "related":
            value = sorted({v for v in (value or []) if isinstance(v, str) and v})
        elif not isinstance(value, str):
            value = str(value)
        meta[field] = value
    return meta


def read_meta(folder):
    data = read_json(Path(folder) / META_NAME, None)
    if data is not None and not isinstance(data, dict):
        raise ArchiveError("{} is not a JSON object.".format(Path(folder) / META_NAME))
    return data


def meta_text(problem):
    return json.dumps(normalize_meta(problem), ensure_ascii=False, indent=2) + "\n"


def write_meta(folder, problem):
    atomic_write(Path(folder) / META_NAME, meta_text(problem))


def meta_revision(folder):
    path = Path(folder) / META_NAME
    return hashlib.sha256(path.read_bytes() if path.exists() else b"").hexdigest()


# --- Loading -------------------------------------------------------------
def problem_folder(root, folder):
    folder = Path(folder).resolve()
    base = (Path(root) / "problems").resolve()
    try:
        relative = folder.relative_to(base)
    except ValueError as exc:
        raise ArchiveError("Refresh must target this repo's problems directory.") from exc
    if len(relative.parts) != 2 or relative.parts[0] not in providers.names():
        raise ArchiveError("Choose an existing problem folder or its dated code file.")
    return folder, relative.parts[0], relative.parts[1]


def recall_tags(text):
    match = re.search(r"(?m)^Patterns: (.+)$", block_content(text, "recall"))
    return [t.strip() for t in match[1].split(",") if t.strip()] if match else []


def legacy_problem(root, folder):
    """Identity reconstructed from README for folders without problem.json."""
    folder, platform, key = problem_folder(root, folder)
    text = (folder / "README.md").read_text(encoding="utf-8")
    url = re.search(r"^Source: (https://\S+)$", text, re.M)
    title = re.search(r"^# (.+)$", text, re.M)
    if not url or not title:
        raise ArchiveError("README is missing its title or Source link.")
    ident = key.split("-", 1)[0] if platform == "leetcode" else ""
    provider = providers.get(platform)
    return {"platform": platform, "key": key, "id": str(int(ident)) if ident else "",
            "slug": urlparse(url[1]).path.rstrip("/").split("/")[-1],
            "title": re.sub(r"^\d+\. ", "", title[1]) if ident else title[1], "url": url[1],
            "companies": provider.companies_from_url(url[1]), "tags": recall_tags(text), "related": []}


def load_problem(root, folder):
    folder, platform, key = problem_folder(root, folder)
    meta = read_meta(folder)
    if meta is None:
        return legacy_problem(root, folder)
    problem = normalize_meta(meta)
    del problem["schema"]
    problem.update(platform=platform, key=key)
    return problem


def find_existing(root, problem):
    """An archived folder for the same problem (same key, URL, or manual title)."""
    base = Path(root) / "problems" / problem["platform"]
    direct = base / problem["key"]
    if (direct / "README.md").is_file():
        return load_problem(root, direct)
    if not base.is_dir():
        return None
    provider = providers.get(problem["platform"])
    for folder in sorted(base.iterdir()):
        if not (folder / "README.md").is_file():
            continue
        try:
            existing = load_problem(root, folder)
        except ArchiveError:
            continue
        if provider.same_problem(existing, problem):
            return existing
    return None


def problem_folders(root):
    base = Path(root) / "problems"
    if not base.is_dir():
        return []
    return [f for f in sorted(base.glob("*/*"))
            if f.parent.name in providers.names() and (f / "README.md").is_file()]


# --- Practices -----------------------------------------------------------
def practice_files(folder):
    files = []
    for path in Path(folder).glob("*.py"):
        match = CODE_NAME.fullmatch(path.name)
        if match:
            files.append((match[1], int(match[2] or 1), path))
    return [path for _, _, path in sorted(files)]


def code_header(content):
    status = re.match(r"# Practice: (independent|improved|learned)\n", content)
    difficulty = re.match(r"# Practice: [a-z]+\n# Difficulty: ([1-5])\n", content)
    body = content
    if status:
        body = body[status.end():]
        if difficulty:
            body = body.split("\n", 1)[1] if "\n" in body else ""
    return (status[1] if status else "unknown", int(difficulty[1]) if difficulty else None, body)


def readme_entries(text):
    if "## Practice notes" not in text:
        return {}
    section = text.split("## Practice notes", 1)[1]
    matches = list(ENTRY.finditer(section))
    entries = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(section)
        body = section[match.end():end]
        code = re.search(r"(?m)^Code: \[([^\]]+)\]\(", body)
        notes = ""
        if "\nMy notes:\n\n" in body:
            notes = body.split("\nMy notes:\n\n", 1)[1].rstrip()
        if code:
            entries[code[1]] = {"notes": notes}
    return entries


def practices(folder, text=None):
    """Every dated solution with its status, difficulty, code and notes."""
    folder = Path(folder)
    text = text if text is not None else (folder / "README.md").read_text(encoding="utf-8")
    entries = readme_entries(text)
    result = []
    for path in practice_files(folder):
        status, difficulty, code = code_header(path.read_text(encoding="utf-8"))
        date = path.name[:8]
        result.append({"filename": path.name, "date": "{}-{}-{}".format(date[:4], date[4:6], date[6:]),
                       "status": status, "difficulty": difficulty, "code": code,
                       "notes": entries.get(path.name, {}).get("notes", "")})
    return result
