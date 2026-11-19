#!/usr/bin/env python3
"""Upgrade existing problem folders to the problem.json layout.

Dry run by default: prints every planned change and writes nothing.
Run with --apply to perform it. Safe to run repeatedly.

- Adds problem.json (identity, companies from the URL, tags from Patterns).
- Renames folders whose name no longer matches the title, such as the
  Hack2Hire practice-<hash> folders, to <title-slug>-<hash>.
- Moves cached statements that you supplied into the README statement block,
  so they are kept in Git rather than only in the ignored .cache/.
- Links problems that share one question (Part 1/2/3) as related.

Code files, practice notes and Quick recall are never changed.
"""

import argparse
import json
from pathlib import Path
import re
import sys

import providers
import records
from archive import ROOT, archive_lock, cache_path
from common import ArchiveError, atomic_write, clean_list, read_json, require_python

USER_SUPPLIED = "Source text supplied by the user."


def plan(root):
    items = []
    for folder in records.problem_folders(root):
        platform, old_key = folder.parent.name, folder.name
        provider = providers.get(platform)
        problem = records.load_problem(root, folder)
        text = (folder / "README.md").read_text(encoding="utf-8")
        history = records.practices(folder, text)
        new_key = old_key
        if platform != "leetcode" and problem.get("url"):
            url = provider.canonical_url(problem["url"])
            problem["url"] = url
            problem["slug"] = provider.url_slug(url)
            new_key = provider.new_key(problem["title"], problem["slug"], url)
            suffix = re.search(r"-([0-9a-f]{8})$", old_key)
            if suffix and not new_key.endswith(suffix.group(0)):
                new_key = new_key.rsplit("-", 1)[0] + suffix.group(0)
        problem["companies"] = clean_list(list(problem.get("companies") or [])
                                          + provider.companies_from_url(problem.get("url", "")))
        if not problem.get("tags"):
            problem["tags"] = records.recall_tags(text)
        if not problem.get("created") and history:
            problem["created"] = history[0]["date"]
        statement = ""
        if not records.block_content(text, "statement"):
            cached = read_json(cache_path(root, {"platform": platform, "key": old_key}), {})
            if cached.get("statement") and cached.get("provenance") == USER_SUPPLIED:
                statement = cached["statement"]
        items.append({"folder": folder, "platform": platform, "old_key": old_key, "new_key": new_key,
                      "problem": problem, "statement": statement})
    # Related keys refer to the new folder names.
    renamed = {i["platform"] + "/" + i["old_key"]: i["platform"] + "/" + i["new_key"] for i in items}
    for item in items:
        item["problem"]["key"] = item["new_key"]
        item["problem"]["related"] = sorted({renamed.get(k, k) for k in item["problem"].get("related", [])})
    groups = {}
    for item in items:
        group = providers.get(item["platform"]).group_of(item["problem"])
        if group:
            groups.setdefault((item["platform"], group), []).append(item)
    for members in groups.values():
        keys = {m["platform"] + "/" + m["new_key"] for m in members}
        for member in members:
            own = member["platform"] + "/" + member["new_key"]
            member["problem"]["related"] = sorted(set(member["problem"]["related"]) | (keys - {own}))
    for item in items:
        meta_path = item["folder"] / records.META_NAME
        current = meta_path.read_text(encoding="utf-8") if meta_path.exists() else None
        item["meta_changed"] = current != records.meta_text(item["problem"])
        item["meta_new"] = current is None
    return items


def describe(item):
    changes = []
    if item["old_key"] != item["new_key"]:
        changes.append("rename → {}".format(item["new_key"]))
    if item["meta_new"]:
        changes.append("add problem.json")
    elif item["meta_changed"]:
        changes.append("update problem.json")
    if item["statement"]:
        changes.append("move cached statement into README ({} chars)".format(len(item["statement"])))
    extras = []
    if item["problem"]["companies"]:
        extras.append("companies: " + ", ".join(item["problem"]["companies"]))
    if item["problem"]["related"]:
        extras.append("related: " + ", ".join(item["problem"]["related"]))
    return changes, extras


def apply(root, items):
    for item in items:
        if item["old_key"] != item["new_key"]:
            target = item["folder"].parent / item["new_key"]
            if target.exists():
                raise ArchiveError("Cannot rename {}: {} already exists.".format(item["folder"], target))
    for item in items:
        folder = item["folder"]
        old_cache = cache_path(root, {"platform": item["platform"], "key": item["old_key"]})
        if item["old_key"] != item["new_key"]:
            target = folder.parent / item["new_key"]
            folder.rename(target)
            folder = target
            if old_cache.exists():
                cached = read_json(old_cache, {})
                cached.update(key=item["new_key"], title=item["problem"]["title"])
                new_cache = cache_path(root, item["problem"])
                atomic_write(new_cache, json.dumps(cached, ensure_ascii=False, indent=2) + "\n")
                old_cache.unlink()
        if item["statement"]:
            readme = folder / "README.md"
            atomic_write(readme, records.set_statement(readme.read_text(encoding="utf-8"), item["statement"]))
        if item["meta_changed"]:
            records.write_meta(folder, item["problem"])


def main(argv=None, root=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Perform the changes (default: dry run)")
    args = parser.parse_args(argv)
    root = Path(root or ROOT)
    with archive_lock(root):
        items = plan(root)
        pending = 0
        for item in items:
            changes, extras = describe(item)
            if not changes:
                continue
            pending += 1
            print("{}/{}: {}".format(item["platform"], item["old_key"], "; ".join(changes)))
            for extra in extras:
                print("    " + extra)
        if not pending:
            print("All {} problem folders are up to date.".format(len(items)))
            return 0
        if not args.apply:
            print("\nDry run: {} of {} folders would change. Re-run with --apply.".format(pending, len(items)))
            return 0
        apply(root, items)
        print("\nUpdated {} of {} folders. Review with: git status".format(pending, len(items)))
    return 0


if __name__ == "__main__":
    require_python()
    try:
        sys.exit(main())
    except (ArchiveError, OSError, ValueError) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        sys.exit(1)
