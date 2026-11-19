#!/usr/bin/env python3
"""Check for and install Coding Practice Tracker updates (standard library only).

Only the tool files listed in tracker-manifest.json are replaced. Practice
records (problems/), plans/, STYLE.md, settings.json, .cache/ and .git/ are
never touched,
and tool files you changed yourself are kept. Nothing is committed or pushed.

  python3 scripts/update.py --check   # report whether a newer release exists
  python3 scripts/update.py           # list the changes, then ask to install
  python3 scripts/update.py --yes     # install without asking

Releases come from the GitHub repository named in tracker-manifest.json. The
script is self-contained, so a copy that predates the updater can download
this one file into scripts/ and run it.
"""

import argparse
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "tracker-manifest.json"
DEFAULT_REPOSITORY = "HelloLindo/coding-practice-tracker"
# User-owned paths. The updater refuses to write below them whatever a manifest says.
PROTECTED = ("problems", "plans", "style.md", "settings.json", ".cache", ".git")
CHECK_CACHE = ".cache/update-check.json"
CHECK_INTERVAL = 24 * 3600
RETRY_INTERVAL = 3600
REPOSITORY_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}")
VERSION_RE = re.compile(r"v?(\d{1,4})\.(\d{1,4})\.(\d{1,4})")
HASH_RE = re.compile(r"[0-9a-f]{64}")
MAX_DOWNLOAD = 50 * 1000 * 1000
CODE_DIRS = ("scripts/", "web/", "tests/")
CODE_SUFFIXES = (".py", ".js", ".html", ".css", ".cmd", ".command")


class UpdateError(Exception):
    pass


# --- Manifest ------------------------------------------------------------------
def digest(data):
    """Content hash that ignores CRLF/LF differences from Git checkouts."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def parse_version(text):
    match = VERSION_RE.fullmatch(str(text or "").strip())
    if not match:
        raise UpdateError("Invalid version: {!r}".format(text))
    return tuple(int(part) for part in match.groups())


def version_text(version):
    return ".".join(str(part) for part in version)


def safe_path(name):
    """Return the repository-relative POSIX path the updater may write, or raise."""
    if (not isinstance(name, str) or not name or len(name) > 300 or "\\" in name
            or "\0" in name or ":" in name):
        raise UpdateError("Unsafe path in manifest: {!r}".format(name))
    path = PurePosixPath(name)
    if (path.is_absolute() or path.as_posix() != name
            or any(part in ("", ".", "..") for part in path.parts)
            or path.parts[0].casefold() in PROTECTED or name == MANIFEST):
        raise UpdateError("Unsafe path in manifest: {!r}".format(name))
    return name


def _hashes(value, where):
    if not isinstance(value, list) or not all(isinstance(h, str) and HASH_RE.fullmatch(h) for h in value):
        raise UpdateError("Invalid hashes for {} in the manifest.".format(where))
    return value


def validate_manifest(data):
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        raise UpdateError("The manifest is not a tracker manifest.")
    parse_version(data.get("version"))
    repository = data.get("repository", DEFAULT_REPOSITORY)
    if not isinstance(repository, str) or not REPOSITORY_RE.fullmatch(repository):
        raise UpdateError("Invalid repository in the manifest: {!r}".format(repository))
    for name, entry in data["files"].items():
        safe_path(name)
        if not isinstance(entry, dict) or not HASH_RE.fullmatch(str(entry.get("sha256", ""))):
            raise UpdateError("Invalid manifest entry: {}".format(name))
        _hashes(entry.get("previous", []), name)
    requires = data.get("requires_python", "3.0")
    if not isinstance(requires, str) or not re.fullmatch(r"3\.\d{1,2}", requires):
        raise UpdateError("Invalid requires_python in the manifest: {!r}".format(requires))
    removed = data.get("removed", {})
    if not isinstance(removed, dict):
        raise UpdateError("Invalid removed list in the manifest.")
    for name, hashes in removed.items():
        safe_path(name)
        _hashes(hashes, name)
    return data


def local_manifest(root):
    path = Path(root) / MANIFEST
    if not path.is_file():
        return None
    try:
        return validate_manifest(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise UpdateError("Cannot read {}: {}".format(MANIFEST, exc)) from exc


def current_version(root):
    """Installed version, or None for a copy that predates the manifest."""
    manifest = local_manifest(root)
    return manifest["version"] if manifest else None


def repository_of(root):
    manifest = local_manifest(root)
    return manifest.get("repository", DEFAULT_REPOSITORY) if manifest else DEFAULT_REPOSITORY


# --- Network -------------------------------------------------------------------
def curl(url, timeout=60):
    """Fetch an HTTPS URL with the system curl; TLS verification is never disabled."""
    exe = shutil.which("curl")
    if not exe:
        raise UpdateError("curl is unavailable, so updates cannot be downloaded.")
    cmd = [exe, "--fail", "--silent", "--show-error", "--location", "--max-redirs", "5",
           "--max-time", str(timeout), "--max-filesize", str(MAX_DOWNLOAD),
           "--proto", "=https", "--proto-redir", "=https",
           "--user-agent", "coding-practice-tracker-updater", url]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError("Update request failed: {}".format(exc)) from exc
    if result.returncode:
        message = result.stderr.decode("utf-8", "replace").strip()[-300:]
        raise UpdateError(message or "Update request failed.")
    return result.stdout


def latest_release(repository, fetch=curl):
    url = "https://api.github.com/repos/{}/releases/latest".format(repository)
    try:
        data = json.loads(fetch(url, 20).decode("utf-8"))
    except UpdateError as exc:
        if "404" in str(exc):
            raise UpdateError("{} has not published a release yet.".format(repository)) from exc
        raise
    except ValueError as exc:
        raise UpdateError("GitHub returned an unreadable release.") from exc
    tag = data.get("tag_name") if isinstance(data, dict) else None
    if not isinstance(tag, str) or not re.fullmatch(r"v\d{1,4}\.\d{1,4}\.\d{1,4}", tag):
        raise UpdateError("The latest release has no vX.Y.Z tag.")
    page = data.get("html_url") or ""
    if not page.startswith("https://github.com/"):
        page = "https://github.com/{}/releases/tag/{}".format(repository, tag)
    return {"tag": tag, "version": version_text(parse_version(tag)), "url": page,
            "name": str(data.get("name") or tag)[:200], "notes": str(data.get("body") or "")[:4000],
            "published_at": str(data.get("published_at") or "")}


def download(repository, tag, fetch=curl):
    return fetch("https://codeload.github.com/{}/tar.gz/refs/tags/{}".format(repository, tag), 120)


# --- Update check (cached) -----------------------------------------------------
def _read_cache(root):
    try:
        data = json.loads((Path(root) / CHECK_CACHE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_cache(root, data):
    path = Path(root) / CHECK_CACHE
    try:
        atomic_write_bytes(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode())
    except OSError:
        pass  # The check still works without the cache.


def status(root, latest=None, checked_at=None, error=None):
    current = current_version(root)
    available = False
    if latest:
        available = current is None or parse_version(latest["version"]) > parse_version(current)
    return {"current": current, "repository": repository_of(root), "latest": latest,
            "available": available, "checked_at": checked_at, "error": error}


def check(root, force=False, fetch=curl, now=None):
    """Latest-release status, from a once-a-day cache unless force is set."""
    now = time.time() if now is None else now
    repository = repository_of(root)
    cached = _read_cache(root)
    # A failed check is retried after an hour rather than a day.
    interval = RETRY_INTERVAL if cached.get("error") else CHECK_INTERVAL
    fresh = (cached.get("repository") == repository
             and isinstance(cached.get("checked_at"), (int, float))
             and 0 <= now - cached["checked_at"] < interval)
    if fresh and not force:
        return status(root, cached.get("latest"), cached["checked_at"], cached.get("error"))
    latest, error = None, None
    try:
        latest = latest_release(repository, fetch)
    except UpdateError as exc:
        error = str(exc)
        latest = cached.get("latest") if cached.get("repository") == repository else None
    _write_cache(root, {"repository": repository, "checked_at": now, "latest": latest, "error": error})
    return status(root, latest, now, error)


def cached_status(root):
    """Status from the cache only; never touches the network."""
    cached = _read_cache(root)
    if cached.get("repository") != repository_of(root):
        return status(root)
    return status(root, cached.get("latest"), cached.get("checked_at"), cached.get("error"))


# --- Release contents ----------------------------------------------------------
def read_release(archive):
    """Read a GitHub tag tarball in memory. Nothing is extracted to disk."""
    try:
        tar = tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz")
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise UpdateError("The downloaded release is not a valid archive.") from exc
    with tar:
        members = {}
        for member in tar.getmembers():
            parts = member.name.split("/", 1)
            if member.isfile() and len(parts) == 2 and parts[1]:
                members[parts[1]] = member

        def read(name):
            handle = tar.extractfile(members[name])
            return handle.read() if handle else b""

        if MANIFEST not in members:
            raise UpdateError("The release does not contain {}.".format(MANIFEST))
        raw = read(MANIFEST)
        try:
            manifest = validate_manifest(json.loads(raw.decode("utf-8")))
        except ValueError as exc:
            raise UpdateError("The release manifest is unreadable.") from exc
        files = {}
        for name, entry in manifest["files"].items():
            if name not in members:
                raise UpdateError("The release is missing {}.".format(name))
            data = read(name)
            if digest(data) != entry["sha256"]:
                raise UpdateError("{} does not match the release manifest.".format(name))
            files[name] = data
    return manifest, raw, files


def known_hashes(name, new, old):
    known = set()
    for manifest in (new, old):
        if not manifest:
            continue
        entry = manifest["files"].get(name)
        if entry:
            known.add(entry["sha256"])
            known.update(entry.get("previous", []))
        known.update(manifest.get("removed", {}).get(name, []))
    return known


def local_hash(root, name):
    path = Path(root) / name
    if path.is_symlink() or (path.exists() and not path.is_file()):
        return "other"
    if not path.exists():
        return None
    return digest(path.read_bytes())


def plan(root, new, old=None):
    """Per-file actions: add, update, delete, same, keep (changed locally)."""
    actions = []
    names = set(new["files"]) | set(new.get("removed", {}))
    if old:
        names |= set(old["files"]) | set(old.get("removed", {}))
    for name in sorted(names):
        try:
            safe_path(name)
        except UpdateError:
            continue  # Never act on an unsafe name from an older local manifest.
        current = local_hash(root, name)
        known = known_hashes(name, new, old)
        entry = new["files"].get(name)
        if entry:
            if current is None:
                action = "add"
            elif current == entry["sha256"]:
                action = "same"
            elif current in known:
                action = "update"
            else:
                action = "keep"
        elif current is None or current == "other":
            continue
        elif current in known:
            action = "delete"
        else:
            action = "keep"
        if action != "same":
            actions.append({"path": name, "action": action, "removed_upstream": entry is None})
    return actions


def is_code(name):
    """Files the tool runs. Keeping an edited one beside updated ones can mix versions."""
    return name.startswith(CODE_DIRS) or name.endswith(CODE_SUFFIXES)


def conflicts(actions):
    return [a["path"] for a in actions
            if a["action"] == "keep" and not a["removed_upstream"] and is_code(a["path"])]


def summarize(actions):
    counts = {"add": 0, "update": 0, "delete": 0, "keep": 0}
    for item in actions:
        counts[item["action"]] += 1
    return {"counts": counts, "kept": [a["path"] for a in actions if a["action"] == "keep"],
            "conflicts": conflicts(actions)}


def conflict_message(names):
    return ("You changed {} tool code file(s): {}. Keeping them beside updated files could break the tool. "
            "Run `python3 scripts/update.py --replace-modified` to back up your versions under "
            ".cache/update/ and install the release versions, or undo those changes first."
            .format(len(names), ", ".join(names)))


# --- Writing -------------------------------------------------------------------
def atomic_write_bytes(path, data, executable=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
        if os.name != "nt":
            os.chmod(temp, 0o755 if executable else 0o644)
        os.replace(temp, str(path))
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def _lock(root):
    """The archive lock, so an update never interleaves with an archive."""
    try:
        sys.path.insert(0, str(Path(root) / "scripts"))
        from common import file_lock  # noqa: PLC0415  (absent in pre-updater copies)
    except ImportError:
        file_lock = None
    finally:
        sys.path.pop(0)
    path = Path(root) / ".cache" / "archive.lock"
    if file_lock:
        with file_lock(path):
            yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "a+", encoding="utf-8") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _remove_empty_parents(root, path):
    root = Path(root).resolve()
    parent = path.parent
    while parent.resolve() != root:
        try:
            parent.rmdir()
        except OSError:
            return
        parent = parent.parent


def install(root, new, raw, files, replace_modified=False):
    """Apply a release under the archive lock and return what happened.

    Edited tool code files stop the update unless replace_modified is set; then
    the user's versions are backed up under .cache/update/<version>/yours/.
    Other edited files (README, AGENTS.md, docs) are kept as they are.
    """
    root = Path(root)
    with _lock(root):
        old = local_manifest(root)
        actions = plan(root, new, old)
        replaced = conflicts(actions)
        if replaced and not replace_modified:
            raise UpdateError(conflict_message(replaced))
        stash = root / ".cache" / "update" / new["version"]
        for item in actions:
            name, action = item["path"], item["action"]
            target = root / name
            entry = new["files"].get(name, {})
            if name in replaced:
                atomic_write_bytes(stash / "yours" / name, target.read_bytes())
                atomic_write_bytes(target, files[name], entry.get("executable", False))
                item["action"] = "update"
            elif action in ("add", "update"):
                atomic_write_bytes(target, files[name], entry.get("executable", False))
            elif action == "delete":
                target.unlink()
                _remove_empty_parents(root, target)
            elif action == "keep" and name in files:
                # Keep the user's version; leave the release copy for comparison.
                atomic_write_bytes(stash / name, files[name])
        atomic_write_bytes(root / MANIFEST, raw)
        try:
            (root / CHECK_CACHE).unlink()
        except OSError:
            pass
    result = summarize(actions)
    result.update(version=new["version"], previous=old["version"] if old else None, replaced=replaced,
                  stash=(stash.relative_to(root).as_posix() if result["kept"] or replaced else None))
    return result


def check_python(manifest, running=None):
    """Refuse a release that the interpreter running the tool cannot start."""
    running = tuple((running or sys.version_info)[:2])
    needed = tuple(int(part) for part in manifest.get("requires_python", "3.0").split("."))
    if running < needed:
        raise UpdateError("Version {} needs Python {}.{} or newer, but this is Python {}.{}. Install a current "
                          "Python from https://www.python.org/downloads/, then run the update with it."
                          .format(manifest["version"], needed[0], needed[1], running[0], running[1]))


def prepare(root, release=None, fetch=curl):
    """Download the latest (or given) release and plan it without writing."""
    repository = repository_of(root)
    release = release or latest_release(repository, fetch)
    new, raw, files = read_release(download(repository, release["tag"], fetch))
    if version_text(parse_version(new["version"])) != release["version"]:
        raise UpdateError("Release {} contains manifest version {}.".format(release["tag"], new["version"]))
    check_python(new)
    actions = plan(root, new, local_manifest(root))
    return {"release": release, "manifest": new, "raw": raw, "files": files,
            "actions": actions, "summary": summarize(actions)}


# --- Command line --------------------------------------------------------------
def describe(summary):
    c = summary["counts"]
    lines = ["  {} updated, {} added, {} removed".format(c["update"], c["add"], c["delete"])]
    kept = [name for name in summary["kept"] if name not in summary.get("conflicts", [])]
    if kept:
        lines.append("  Kept because you changed them (the release copy goes to .cache/update/):")
        lines.extend("    " + name for name in kept)
    if summary.get("conflicts"):
        lines.append("  Tool code you changed (needs --replace-modified; your versions are backed up):")
        lines.extend("    " + name for name in summary["conflicts"])
    return "\n".join(lines)


def main(argv=None, root=None, fetch=curl):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="Only report whether an update exists")
    parser.add_argument("--yes", action="store_true", help="Install without asking")
    parser.add_argument("--replace-modified", action="store_true",
                        help="Back up tool code files you changed and install the release versions")
    parser.add_argument("--root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = Path(root or args.root or ROOT).resolve()
    if not (root / "scripts").is_dir():
        raise UpdateError("{} does not look like a Coding Practice Tracker folder.".format(root))
    info = check(root, force=True, fetch=fetch)
    current = info["current"] or "unknown (before the updater)"
    if info["error"]:
        raise UpdateError(info["error"])
    latest = info["latest"]
    if not info["available"]:
        print("Coding Practice Tracker {} is up to date.".format(current))
        return 0
    print("Coding Practice Tracker {} is available (installed: {}).".format(latest["version"], current))
    print("Release notes: " + latest["url"])
    if args.check:
        return 0
    prepared = prepare(root, latest, fetch)
    print(describe(prepared["summary"]))
    if prepared["summary"]["conflicts"] and not args.replace_modified:
        print("\nNothing changed. " + conflict_message(prepared["summary"]["conflicts"]))
        return 1
    if not args.yes:
        if not sys.stdin.isatty():
            print("Re-run with --yes to install.")
            return 0
        if input("Install {}? [y/N] ".format(latest["version"])).strip().lower() not in ("y", "yes"):
            print("Nothing changed.")
            return 0
    result = install(root, prepared["manifest"], prepared["raw"], prepared["files"], args.replace_modified)
    print("Installed {}.".format(result["version"]))
    if result["replaced"]:
        print("Your previous versions of {} are in {}/yours/.".format(", ".join(result["replaced"]), result["stash"]))
    if result["stash"] and len(result["kept"]):
        print("Compare your kept files with the copies in {}.".format(result["stash"]))
    migrate = root / "scripts" / "migrate.py"
    if migrate.is_file():
        print("\nChecking whether saved problems need the new record layout (dry run):", flush=True)
        subprocess.run([sys.executable, str(migrate)], cwd=str(root))
    print("\nRestart web.command if it is running. Review with `git status`, then commit the update.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (UpdateError, OSError, ValueError) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
