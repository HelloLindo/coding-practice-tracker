"""Shared helpers for the coding practice tools (standard library only).

Everything here works on macOS, Linux and Windows with a plain Python 3.11+
installation: no third-party packages and no tzdata download are required.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata

MIN_PYTHON = (3, 11)


def require_python():
    """Stop with a clear message on an unsupported interpreter."""
    if sys.version_info[:2] < MIN_PYTHON:
        raise SystemExit("Coding Practice Tracker needs Python {}.{} or newer; this is Python {}.{}. "
                         "Install a current Python from https://www.python.org/downloads/ and run it again."
                         .format(*MIN_PYTHON, *sys.version_info[:2]))


class ArchiveError(Exception):
    pass


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                     dir=str(path.parent), delete=False) as tmp:
        tmp.write(text)
        name = tmp.name
    try:
        os.replace(name, str(path))
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_json(path, default):
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ArchiveError("Cannot read {}: {}".format(path, exc)) from exc


@contextmanager
def file_lock(path):
    """Exclusive inter-process lock: fcntl on macOS/Linux, msvcrt on Windows."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "a+") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    continue  # LK_LOCK gives up after ~10 seconds; keep waiting.
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


def _nth_sunday(year, month, n):
    first = datetime(year, month, 1)
    return first + timedelta(days=(6 - first.weekday()) % 7, weeks=n - 1)


def pacific_now():
    """Current America/Los_Angeles time, even where the tz database is missing.

    Windows Python has no bundled tz database unless the tzdata package is
    installed, so fall back to the US rules (second Sunday of March to the
    first Sunday of November, switching at 02:00 local time).
    """
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Los_Angeles"))
    except (ImportError, LookupError, ValueError, OSError):
        utc = datetime.now(timezone.utc)
        naive = utc.replace(tzinfo=None)
        start = _nth_sunday(naive.year, 3, 2).replace(hour=10)  # 02:00 PST
        end = _nth_sunday(naive.year, 11, 1).replace(hour=9)    # 02:00 PDT
        offset = -7 if start <= naive < end else -8
        return utc.astimezone(timezone(timedelta(hours=offset)))


def today():
    return pacific_now().strftime("%Y%m%d")


def slugify(text, limit=60):
    """ASCII folder-name slug; non-Latin titles fall back to 'problem'."""
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:limit].rstrip("-") or "problem"


def short_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def clean_list(values, limit=20, item_limit=60):
    """Normalize user-entered companies or tags: trimmed, unique, bounded."""
    if isinstance(values, str):
        values = values.split(",")
    if not isinstance(values, (list, tuple)):
        raise ArchiveError("Expected a list of names.")
    result, seen = [], set()
    for value in values:
        if not isinstance(value, str):
            raise ArchiveError("Names must be text.")
        value = " ".join(value.split())
        if not value:
            continue
        if len(value) > item_limit or "\n" in value:
            raise ArchiveError("Each name must be one short line.")
        if value.casefold() not in seen:
            seen.add(value.casefold())
            result.append(value)
    if len(result) > limit:
        raise ArchiveError("Too many names; keep at most {}.".format(limit))
    return result
