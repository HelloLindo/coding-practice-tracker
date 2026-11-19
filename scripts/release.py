#!/usr/bin/env python3
"""Maintain tracker-manifest.json, the list of files the updater may replace.

  python3 scripts/release.py                    # refresh hashes for the current version
  python3 scripts/release.py --version 0.3.0    # start a new version
  python3 scripts/release.py --check            # fail if the manifest is stale

Run it after changing any shipped file. Earlier hashes are kept, so the
updater recognises unmodified copies of every earlier version. Publishing a release (tag + GitHub Release) is a
separate, manual step for the maintainer.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from update import MANIFEST, DEFAULT_REPOSITORY, UpdateError, digest, parse_version, safe_path, version_text

ROOT = Path(__file__).resolve().parents[1]
REQUIRES_PYTHON = "3.11"  # Keep in step with common.MIN_PYTHON.


def git(root, *args, binary=False):
    result = subprocess.run(["git", *args], cwd=str(root), capture_output=True)
    if result.returncode:
        raise UpdateError("git {} failed: {}".format(" ".join(args), result.stderr.decode(errors="replace").strip()))
    return result.stdout if binary else result.stdout.decode("utf-8")


def shipped(root):
    """Tracked and new (not ignored) files that belong to the tool."""
    listed = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    modes = {}
    for line in git(root, "ls-files", "-s", "-z").split("\0"):
        if line:
            meta, name = line.split("\t", 1)
            modes[name] = meta.split()[0]
    files = {}
    for name in sorted(set(filter(None, listed.split("\0")))):
        try:
            safe_path(name)
        except UpdateError:
            continue  # problems/, plans/, STYLE.md and the manifest itself are not tool files.
        path = Path(root) / name
        if not path.is_file() or path.is_symlink():
            continue
        executable = modes.get(name) == "100755" if name in modes else os.access(str(path), os.X_OK)
        files[name] = {"sha256": digest(path.read_bytes()), "executable": executable}
    return files


def build(root, old, version=None, previous_ref=None):
    old = old or {"version": "0.0.0", "files": {}, "removed": {}}
    version = version_text(parse_version(version or old["version"]))
    removed = {k: list(v) for k, v in old.get("removed", {}).items()}
    files = {}
    for name, entry in shipped(root).items():
        before = old["files"].get(name, {})
        # Every hash this repository has shipped stays recognisable as unmodified.
        previous = list(before.get("previous", [])) + removed.pop(name, [])
        if before.get("sha256"):
            previous.append(before["sha256"])
        entry["previous"] = sorted(set(previous) - {entry["sha256"]})
        files[name] = entry
    for name, before in old["files"].items():
        if name not in files:
            hashes = set(removed.get(name, [])) | set(before.get("previous", [])) | {before["sha256"]}
            removed[name] = sorted(hashes)
    if previous_ref:
        for name in git(root, "ls-tree", "-r", "-z", "--name-only", previous_ref).split("\0"):
            try:
                safe_path(name)
            except UpdateError:
                continue
            old_hash = digest(git(root, "show", "{}:{}".format(previous_ref, name), binary=True))
            if name in files:
                if old_hash != files[name]["sha256"]:
                    files[name]["previous"] = sorted(set(files[name]["previous"]) | {old_hash})
            else:
                removed[name] = sorted(set(removed.get(name, [])) | {old_hash})
    return {"name": "coding-practice-tracker", "version": version, "requires_python": REQUIRES_PYTHON,
            "repository": old.get("repository", DEFAULT_REPOSITORY),
            "files": files, "removed": dict(sorted(removed.items()))}


def render(manifest):
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def main(argv=None, root=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", help="New version number, such as 0.3.0")
    parser.add_argument("--previous-ref", help="Also accept the files at this Git ref as unmodified")
    parser.add_argument("--check", action="store_true", help="Exit 1 if the manifest is out of date")
    args = parser.parse_args(argv)
    root = Path(root or ROOT)
    path = root / MANIFEST
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    text = render(build(root, old, args.version, args.previous_ref))
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if args.check:
        if text != current:
            print("{} is out of date. Run: python3 scripts/release.py".format(MANIFEST), file=sys.stderr)
            return 1
        print("{} is up to date.".format(MANIFEST))
        return 0
    if text != current:
        path.write_text(text, encoding="utf-8", newline="\n")
    manifest = json.loads(text)
    print("{} {}: {} files, {} removed paths.".format(MANIFEST, manifest["version"],
                                                      len(manifest["files"]), len(manifest["removed"])))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (UpdateError, OSError, ValueError) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        sys.exit(1)
