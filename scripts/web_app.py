#!/usr/bin/env python3
"""Local browser entry point for the coding practice journal."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
from urllib.parse import parse_qs, urlparse
import webbrowser

import archive
import migrate
import providers
import records
import report
import update
from common import ArchiveError, ai_settings, clean_list, require_python, today

ROOT = archive.ROOT
WEB = ROOT / "web"
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
                ".ico": "image/x-icon", ".woff2": "font/woff2"}
TERMINAL = ("ready", "partial", "failed", "conflict")
RESTART_CODE = 75  # The supervisor starts the service again after this exit status.
LAYOUT_CHANGES = ("rename", "add problem.json", "move cached statement")


class WebError(Exception):
    def __init__(self, message, status=400, **extra):
        super().__init__(message)
        self.status = status
        self.extra = extra


def recall_block(text):
    start, end = records.marker("recall", "start"), records.marker("recall", "end")
    if text.count(start) != 1 or text.count(end) != 1:
        raise WebError("The README recall markers are missing or have been changed.")
    return text.split(start, 1)[1].split(end, 1)[0]


def recall_fields(text):
    block = recall_block(text)
    revision = hashlib.sha256(block.encode()).hexdigest()
    match = re.search(r"(?ms)^### 中文\s*\n(.*?)^### English\s*\n(.*)\Z", block)
    if match:
        return {"zh": match[1].strip(), "en": match[2].strip(), "revision": revision}
    # Legacy English-only and pending records remain editable without a model call.
    bullets = re.search(r"(?m)^- ", block)
    return {"zh": "", "en": block[bullets.start():].strip() if bullets else "", "revision": revision}


def text_field(data, key, required=False, limit=100000):
    value = data.get(key, "")
    if value is None:
        value = ""
    if not isinstance(value, str) or len(value) > limit:
        raise WebError("Invalid or oversized field: " + key)
    if required and not value.strip():
        raise WebError("Please fill in " + key.replace("_", " ") + ".")
    return value


def list_field(data, key):
    try:
        return clean_list(data.get(key) or [])
    except ArchiveError as exc:
        raise WebError("{}: {}".format(key.capitalize(), exc))


class PracticeApp:
    def __init__(self, root=ROOT, model=None, timeout=120, auto_check=False, fetch=update.curl, effort=None):
        self.root = Path(root).resolve()
        self.model, self.effort = ai_settings(self.root, model, effort)
        self.timeout = timeout
        self.token = secrets.token_urlsafe(32)
        self.boot = secrets.token_hex(8)
        self.jobs = {}
        self.mutex = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="practice")
        self.auto_check = auto_check
        self.fetch = fetch
        self.update_lock = threading.Lock()
        self.installed = None   # Result of an update installed by this process.
        self.restart = None     # Set by main() when a supervisor can restart the service.

    def close(self):
        self.pool.shutdown(wait=True)

    # --- Reading -------------------------------------------------------
    def folder(self, key):
        match = re.fullmatch(r"([a-z0-9]+)/([A-Za-z0-9_-]+)", key) if isinstance(key, str) else None
        if not match or match[1] not in providers.names():
            raise WebError("Choose a valid archived problem.")
        base = (self.root / "problems").resolve()
        folder = (base / key).resolve()
        try:
            folder.relative_to(base)
        except ValueError:
            raise WebError("The problem must belong to this repository.")
        if not folder.is_dir() or (folder / "README.md").resolve().parent != folder:
            raise WebError("The problem README was not found.", 404)
        return folder

    def related(self, keys, own):
        result = []
        for key in keys:
            try:
                folder = self.folder(key)
                other = archive.load_problem(self.root, folder)
            except (WebError, ArchiveError):
                continue
            if key != own:
                result.append({"key": key, "title": other["title"], "platform": other["platform"],
                               "platform_label": providers.label(other["platform"])})
        return result

    def problem(self, key):
        folder = self.folder(key)
        identity = archive.load_problem(self.root, folder)
        text = (folder / "README.md").read_text(encoding="utf-8")
        history = records.practices(folder, text)
        if not history:
            raise WebError("No archived practice was found.", 404)
        latest = history[-1]
        full = records.block_content(text, "statement")
        summary = records.block_content(text, "problem")
        provider = providers.get(identity["platform"])
        return {"key": key, "title": identity["title"], "id": identity.get("id", ""),
                "source": identity.get("url", ""), "platform": identity["platform"],
                "platform_label": provider.label, "statement_mode": provider.statement,
                "companies": identity.get("companies", []), "tags": identity.get("tags", []),
                "related": self.related(identity.get("related", []), key),
                "created": identity.get("created", "") or history[0]["date"],
                "statement": full or summary, "full_statement": full, "summary": summary,
                "statement_revision": records.statement_revision(text),
                "meta_revision": records.meta_revision(folder),
                "filename": latest["filename"], "status": latest["status"],
                "difficulty": latest["difficulty"],
                "code": (folder / latest["filename"]).read_text(encoding="utf-8"),
                "practices": history,
                "readme_path": str((folder / "README.md").relative_to(self.root).as_posix()),
                "recall": recall_fields(text),
                "notes": text.split("## Practice notes", 1)[1].strip() if "## Practice notes" in text else ""}

    def listing(self, query=""):
        query = query.strip().casefold()
        result = []
        for folder, entries in report.practices(self.root):
            try:
                identity = archive.load_problem(self.root, folder)
            except ArchiveError:
                continue
            if query:
                files = [folder / "README.md", *records.practice_files(folder)]
                searchable = [identity["title"], folder.name, identity.get("id", ""),
                              providers.label(identity["platform"]),
                              " ".join(identity.get("companies", [])), " ".join(identity.get("tags", []))]
                searchable.extend(path.read_text(encoding="utf-8") for path in files
                                  if path.resolve().parent == folder.resolve())
                if not any(query in text.casefold() for text in searchable):
                    continue
            date, _, status, _, difficulty = entries[-1]
            result.append({"key": folder.relative_to(self.root / "problems").as_posix(),
                           "title": identity["title"], "id": identity.get("id", ""),
                           "platform": identity["platform"],
                           "platform_label": providers.label(identity["platform"]),
                           "companies": identity.get("companies", []), "tags": identity.get("tags", []),
                           "date": date, "first_date": entries[0][0], "status": status,
                           "difficulty": difficulty, "count": len(entries)})
        return sorted(result, key=lambda x: (x["date"], x["key"]), reverse=True)

    def report(self):
        data = report.data(self.root)
        titles = {p["key"]: p for p in self.listing()}
        for group in ("review", "easiest"):
            for item in data[group]:
                info = titles.get(item["key"], {})
                item.update(title=info.get("title", item["key"]), platform=info.get("platform", ""),
                            platform_label=info.get("platform_label", ""),
                            companies=info.get("companies", []))
        data["platform_labels"] = {name: providers.label(name) for name in data["platforms"]}
        data["today"] = today()
        return data

    def platforms(self):
        return {"platforms": providers.public()}

    def resolve(self, data):
        platform = data.get("platform") or "auto"
        if platform != "auto" and platform not in providers.names():
            raise WebError("Choose a platform.")
        value = text_field(data, "problem", False, 2000).strip()
        title = text_field(data, "title", False, 300).strip()
        display_id = text_field(data, "display_id", False, 60).strip()
        try:
            provider = archive.detect_platform(value, platform)
            if provider.name == "leetcode" and display_id and title:
                problem = archive.manual_identity(value, display_id, title)
            else:
                if provider.url != "none" and not value:
                    raise WebError("Paste the problem URL.")
                problem = provider.resolve(archive.context(self.root), value, title=title, display_id=display_id)
        except ArchiveError as exc:
            needs = (platform in ("auto", "leetcode") and value.startswith("https://")
                     and providers.get("leetcode").matches(value))
            raise WebError(str(exc), needs_identity=needs)
        existing = records.find_existing(self.root, problem)
        folder = None
        if existing:
            folder = self.root / "problems" / existing["platform"] / existing["key"]
        target = existing or problem
        has_statement = bool(folder and records.block_content(
            (folder / "README.md").read_text(encoding="utf-8"), "statement"))
        return {"platform": provider.name, "platform_label": provider.label,
                "title": target["title"], "id": target.get("id", ""), "url": target.get("url", ""),
                "key": target["platform"] + "/" + target["key"], "exists": bool(existing),
                "count": len(records.practice_files(folder)) if folder else 0,
                "companies": target.get("companies", []),
                "needs_title": provider.title == "required" and not existing and not title,
                "statement_mode": provider.statement, "has_statement": has_statement}

    # --- Updates -------------------------------------------------------
    def active_jobs(self):
        with self.mutex:
            return any(job["state"] not in TERMINAL for job in self.jobs.values())

    def migration(self):
        """Folders that still use the record layout from before problem.json."""
        if self.installed:
            return []  # The running code is older than the files; restart first.
        try:
            with archive.archive_lock(self.root):
                items = migrate.plan(self.root)
        except (ArchiveError, OSError, ValueError):
            return []
        pending = []
        for item in items:
            changes, _ = migrate.describe(item)
            if any(change.startswith(LAYOUT_CHANGES) for change in changes):
                pending.append({"key": item["platform"] + "/" + item["old_key"], "changes": changes})
        return pending

    def update_status(self):
        try:
            info = update.cached_status(self.root)
        except update.UpdateError as exc:
            info = {"current": None, "latest": None, "available": False, "error": str(exc)}
        if self.installed:
            info["available"] = False
        info.update(auto_check=self.auto_check, can_restart=self.restart is not None,
                    installed=self.installed, migration=self.migration())
        return info

    def check_updates(self, force=True):
        with self.update_lock:
            try:
                update.check(self.root, force=force, fetch=self.fetch)
            except update.UpdateError as exc:
                raise WebError(str(exc))
        return self.update_status()

    def install_update(self):
        if self.active_jobs():
            raise WebError("Wait for the current archive to finish before updating.", 409)
        with self.update_lock:
            if self.installed:
                raise WebError("An update is already installed. Restart the app to use it.", 409)
            try:
                info = update.check(self.root, fetch=self.fetch)
                if not info["available"]:
                    raise WebError("No newer release is available.", 409)
                prepared = update.prepare(self.root, info["latest"], self.fetch)
                if prepared["summary"]["conflicts"]:
                    raise WebError(update.conflict_message(prepared["summary"]["conflicts"]), 409)
                self.installed = update.install(self.root, prepared["manifest"], prepared["raw"],
                                                prepared["files"])
            except update.UpdateError as exc:
                raise WebError("The update was not installed: " + str(exc), 502)
        return self.update_status()

    def apply_migration(self):
        if self.installed:
            raise WebError("Restart the app to finish the update before upgrading records.", 409)
        if self.active_jobs():
            raise WebError("Wait for the current archive to finish before upgrading records.", 409)
        with archive.archive_lock(self.root):
            items = migrate.plan(self.root)
            pending = sum(1 for item in items if migrate.describe(item)[0])
            migrate.apply(self.root, items)
        result = self.update_status()
        result["migrated"] = pending
        return result

    def request_restart(self):
        if self.restart is None:
            raise WebError("Stop web.command (Ctrl-C) and start it again to use the update.", 409)
        if self.active_jobs():
            raise WebError("Wait for the current archive to finish before restarting.", 409)
        threading.Timer(0.2, self.restart).start()
        return {"restarting": True, "boot": self.boot}

    # --- Writing -------------------------------------------------------
    def save_recall(self, data):
        key = text_field(data, "key", True, 300)
        revision = text_field(data, "revision", True, 100)
        zh = text_field(data, "zh", True, 24000).strip()
        en = text_field(data, "en", True, 24000).strip()
        for content in (zh, en):
            if "<!-- practice:" in content or re.search(r"(?m)^### (?:中文|English)\s*$", content):
                raise WebError("Keep the language headings and README markers outside the editor text.")
        folder = self.folder(key)
        with archive.archive_lock(self.root):
            path = folder / "README.md"
            text = path.read_text(encoding="utf-8")
            if recall_fields(text)["revision"] != revision:
                raise WebError("This recall changed in another tab or process. Reload the saved version before replacing it.", 409)
            block = recall_block(text)
            heading = re.search(r"(?m)^### 中文\s*$", block)
            if heading:
                prefix = block[:heading.start()].strip()
            else:
                latest = records.practice_files(folder)[-1]
                prefix = "Based on [{}]({}).".format(latest.name, latest.name)
            prefix = prefix.replace("AI-generated from", "Based on")
            if "Edited in the local practice app." not in prefix:
                prefix += "\n\nEdited in the local practice app."
            replacement = prefix + "\n\n### 中文\n\n" + zh + "\n\n### English\n\n" + en
            archive.atomic_write(path, records.replace_block(text, "recall", replacement))
        return self.problem(key)

    def save_statement(self, data):
        key = text_field(data, "key", True, 300)
        revision = text_field(data, "revision", True, 100)
        statement = text_field(data, "statement", False, 100000)
        folder = self.folder(key)
        with archive.archive_lock(self.root):
            path = folder / "README.md"
            text = path.read_text(encoding="utf-8")
            if records.statement_revision(text) != revision:
                raise WebError("The statement changed in another tab or process. Reload before saving.", 409)
            try:
                archive.atomic_write(path, records.set_statement(text, statement))
            except ArchiveError as exc:
                raise WebError(str(exc))
        return self.problem(key)

    def save_meta(self, data):
        key = text_field(data, "key", True, 300)
        revision = text_field(data, "revision", True, 100)
        folder = self.folder(key)
        with archive.archive_lock(self.root):
            if records.meta_revision(folder) != revision:
                raise WebError("This problem's details changed in another tab or process. Reload before saving.", 409)
            problem = archive.load_problem(self.root, folder)
            readme = folder / "README.md"
            text = readme.read_text(encoding="utf-8")
            if "title" in data:
                title = text_field(data, "title", True, 200).strip()
                if len(title.splitlines()) != 1:
                    raise WebError("Problem title must be on one line.")
                problem["title"] = title
                text = records.set_heading(text, problem)
            if "id" in data and problem["platform"] != "leetcode":
                try:
                    problem["id"] = providers.base.check_display_id(text_field(data, "id", False, 60))
                except ArchiveError as exc:
                    raise WebError(str(exc))
                text = records.set_heading(text, problem)
            for field in ("companies", "tags"):
                if field in data:
                    problem[field] = list_field(data, field)
            changes = []
            if "related" in data:
                wanted = data["related"]
                if not isinstance(wanted, list) or len(wanted) > 50:
                    raise WebError("Related problems must be a list.")
                wanted = {k for k in wanted if k != key}
                for other in wanted:
                    self.folder(other)
                old = set(problem.get("related", []))
                problem["related"] = sorted(wanted)
                changes = [(k, True) for k in wanted - old] + [(k, False) for k in old - wanted]
            archive.atomic_write(readme, text)
            records.write_meta(folder, problem)
            for other_key, add in changes:
                try:
                    other_folder = self.folder(other_key)
                except WebError:
                    continue
                other = archive.load_problem(self.root, other_folder)
                linked = set(other.get("related", []))
                linked = linked | {key} if add else linked - {key}
                other["related"] = sorted(linked)
                records.write_meta(other_folder, other)
        return self.problem(key)

    def submit(self, data, action="archive"):
        request_id = text_field(data, "request_id", True, 100)
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request_id):
            raise WebError("Invalid request identifier. Reload the page and try again.")
        if action == "archive":
            if data.get("key"):
                self.folder(text_field(data, "key", True, 300))
            else:
                platform = data.get("platform") or "auto"
                if platform != "auto" and platform not in providers.names():
                    raise WebError("Choose a platform.")
                text_field(data, "problem", platform != "manual", 2000)
            code = text_field(data, "code", True, 500000)
            if data.get("status") not in archive.STATUSES.values():
                raise WebError("Choose how you completed this practice.")
            if type(data.get("difficulty")) is not int or not 1 <= data["difficulty"] <= 5:
                raise WebError("Choose a personal difficulty from 1 to 5.")
            try:
                archive.ast.parse(code)
            except (SyntaxError, ValueError) as exc:
                raise WebError("Please check the Python code: " + str(exc))
            for field in ("notes", "statement", "display_id", "title"):
                text_field(data, field)
            list_field(data, "companies")
        else:
            self.folder(text_field(data, "key", True, 300))
            text_field(data, "statement")
        fingerprint = hashlib.sha256((action + json.dumps(data, sort_keys=True)).encode()).hexdigest()
        with self.mutex:
            if request_id in self.jobs:
                old = self.jobs[request_id]
                if old["fingerprint"] != fingerprint:
                    raise WebError("This request identifier was already used for a different practice.", 409)
                return {k: v for k, v in old.items() if k != "fingerprint"}
            if sum(j["state"] not in TERMINAL for j in self.jobs.values()) >= 8:
                raise WebError("Please wait for the current archives to finish.", 429)
            # Retain recent finished jobs for reconnecting tabs, with bounded memory.
            while len(self.jobs) >= 200:
                removable = next((k for k, v in self.jobs.items() if v["state"] in TERMINAL), None)
                if removable is None:
                    break
                del self.jobs[removable]
            self.jobs[request_id] = {"id": request_id, "fingerprint": fingerprint,
                                     "state": "queued", "message": "Preparing your practice…"}
        self.pool.submit(self._work, request_id, dict(data), action)
        return self.job(request_id)

    def job(self, ident):
        with self.mutex:
            if ident not in self.jobs:
                raise WebError("This task is no longer available. Select your saved problem from the sidebar.", 404)
            return {k: v for k, v in self.jobs[ident].items() if k != "fingerprint"}

    def _set(self, ident, **fields):
        with self.mutex:
            self.jobs[ident].update(fields)

    def _identity(self, data):
        if data.get("key"):
            return archive.load_problem(self.root, self.folder(data["key"])), ""
        title = (data.get("title") or "").strip()
        display_id = (data.get("display_id") or "").strip()
        provider = archive.detect_platform(data.get("problem", ""), data.get("platform") or "auto")
        if provider.name == "leetcode" and (display_id or title):
            return archive.manual_identity(data["problem"], display_id, title), ""
        problem = archive.resolve_problem(self.root, provider.name, data.get("problem", ""),
                                          title=title, display_id=display_id)
        if provider.name != "leetcode" and not title and records.find_existing(self.root, problem) is None:
            raise ArchiveError("Enter the problem title shown on the page.")
        return problem, title if provider.name != "leetcode" else ""

    def _work(self, ident, data, action):
        saved = False
        try:
            statement = (data.get("statement") or "").strip()
            if action == "archive":
                self._set(ident, state="resolving", message="Finding the problem…")
                problem, title = self._identity(data)
                with archive.archive_lock(self.root):
                    code = archive.save_practice(self.root, problem, data["code"], data["status"],
                                                 data.get("notes", ""), today(), data["difficulty"],
                                                 title=title, statement=statement,
                                                 companies=clean_list(data.get("companies") or []))
                    problem = archive.load_problem(self.root, code.parent)
            else:
                folder = self.folder(data["key"])
                problem = archive.load_problem(self.root, folder)
                code = records.practice_files(folder)[-1]
                if statement:
                    with archive.archive_lock(self.root):
                        archive.save_statement(self.root, problem, statement)
            saved = True
            key = code.parent.relative_to(self.root / "problems").as_posix()
            self._set(ident, state="saved", key=key, message="Code and notes saved. Preparing Quick recall…")
            with archive.archive_lock(self.root):
                before = (code.parent / "README.md").read_text(encoding="utf-8")
                initial_revision = recall_fields(before)["revision"]
            if action == "archive" and not archive.needs_summary(before):
                self._set(ident, state="ready", message="Practice saved. Your existing Quick recall is ready to edit.")
                return
            source = archive.source_for(self.root, problem, statement or None)
            self._set(ident, state="generating", message="Practice saved. Writing Chinese and English recall…")
            summary = archive.generate_summary(problem, source, code.read_text(encoding="utf-8"),
                                                data.get("notes", ""), self.model, self.timeout, self.effort)
            with archive.archive_lock(self.root):
                current = (code.parent / "README.md").read_text(encoding="utf-8")
                if recall_fields(current)["revision"] != initial_revision:
                    self._set(ident, state="conflict", message="Your saved recall changed while this draft was generating. Your edits were kept; review this new draft before saving.",
                              draft={"zh": "\n".join("- " + x for x in summary["quick_recall"]["zh"]),
                                     "en": "\n".join("- " + x for x in summary["quick_recall"]["en"])})
                    return
                archive.apply_summary(code, source, summary)
            message = "Practice and bilingual recall saved. You can edit the recall below."
            if not source.get("statement"):
                message = "Practice and recall saved. Problem facts are still pending; add the statement and regenerate."
            self._set(ident, state="ready", message=message)
        except Exception as exc:
            self._set(ident, state="partial" if saved else "failed", message=(
                "Your practice is saved. Recall could not be generated: " if saved else "Nothing archived: ") + str(exc)[-900:])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    @property
    def app(self):
        return self.server.app

    def send_body(self, status, body, content_type="application/json; charset=utf-8"):
        payload = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def send_error_body(self, exc):
        body = {"error": str(exc)}
        body.update(getattr(exc, "extra", {}) or {})
        self.send_body(getattr(exc, "status", 400), body)

    def allowed(self, mutation=False):
        host = "127.0.0.1:" + str(self.server.server_port)
        if self.headers.get("Host") != host:
            raise WebError("Use the local URL printed by web.command.", 403)
        if mutation and self.headers.get("Origin") != "http://" + host:
            raise WebError("Open the local practice page to make changes.", 403)

    def api_auth(self):
        if not secrets.compare_digest(self.headers.get("X-Practice-Token", ""), self.app.token):
            raise WebError("Reload the local page to reconnect.", 403)

    def static(self, path):
        name = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
        if not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*\.[a-z0-9]+", name):
            return False
        web = WEB.resolve()
        target = (web / name).resolve()
        try:
            target.relative_to(web)
        except ValueError:
            return False
        kind = STATIC_TYPES.get(target.suffix)
        if not kind or not target.is_file():
            return False
        body = target.read_bytes()
        if name == "index.html":
            body = body.replace(b"__PRACTICE_TOKEN__", self.app.token.encode())
        self.send_body(200, body, kind)
        return True

    def do_GET(self):
        try:
            self.allowed()
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                self.send_body(200, {"ok": True, "boot": self.app.boot})
                return
            if parsed.path == "/favicon.ico":
                self.send_body(204, b"", "image/x-icon")
                return
            if not parsed.path.startswith("/api/"):
                if not self.static(parsed.path):
                    raise WebError("Page not found.", 404)
                return
            self.api_auth()
            query = parse_qs(parsed.query)
            routes = {
                "/api/problems": lambda: {"problems": self.app.listing(query.get("q", [""])[0])},
                "/api/problem": lambda: self.app.problem(query.get("key", [""])[0]),
                "/api/job": lambda: self.app.job(query.get("id", [""])[0]),
                "/api/platforms": self.app.platforms,
                "/api/report": self.app.report,
                "/api/update": self.app.update_status,
            }
            if parsed.path not in routes:
                raise WebError("Page not found.", 404)
            self.send_body(200, routes[parsed.path]())
        except WebError as exc:
            self.send_error_body(exc)
        except (OSError, ValueError, ArchiveError) as exc:
            self.send_body(400, {"error": str(exc)})

    def do_POST(self):
        try:
            self.allowed(mutation=True)
            self.api_auth()
            if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                raise WebError("Expected a JSON form submission.", 415)
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 2000000:
                raise WebError("The form is too large or empty.", 413)
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise WebError("Expected form fields.")
            routes = {
                "/api/archive": (202, lambda: self.app.submit(data)),
                "/api/generate": (202, lambda: self.app.submit(data, "generate")),
                "/api/recall": (200, lambda: self.app.save_recall(data)),
                "/api/statement": (200, lambda: self.app.save_statement(data)),
                "/api/meta": (200, lambda: self.app.save_meta(data)),
                "/api/resolve": (200, lambda: self.app.resolve(data)),
                "/api/update/check": (200, self.app.check_updates),
                "/api/update/install": (200, self.app.install_update),
                "/api/migrate": (200, self.app.apply_migration),
                "/api/restart": (202, self.app.request_restart),
            }
            if self.path not in routes:
                raise WebError("Page not found.", 404)
            status, handler = routes[self.path]
            self.send_body(status, handler())
        except WebError as exc:
            self.send_error_body(exc)
        except (OSError, ValueError, ArchiveError, update.UpdateError) as exc:
            self.send_body(400, {"error": str(exc)})


def make_server(app, port=8765):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.app = app
    server.daemon_threads = True
    return server


def supervise(argv):
    """Run the service in a child process and start it again after an update."""
    args = list(argv)
    env = dict(os.environ, PRACTICE_SUPERVISED="1")
    while True:
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), *args], env=env)
        while True:
            try:
                code = child.wait()
                break
            except KeyboardInterrupt:
                continue  # The child received Ctrl-C too and finishes active archives first.
        if code != RESTART_CODE:
            return code
        print("Restarting with the updated tool…", flush=True)
        if "--no-browser" not in args:
            args.append("--no-browser")


def auto_check_enabled(flag):
    value = os.environ.get("PRACTICE_NO_UPDATE_CHECK", "").strip().lower()
    return not flag and value not in ("1", "true", "yes", "on")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-update-check", action="store_true",
                        help="Do not check GitHub for a newer release (manual checks still work)")
    parser.add_argument("--model", help="Codex model (default: settings.json, PRACTICE_MODEL, or gpt-6-luna)")
    parser.add_argument("--effort", help="Reasoning effort such as low, medium or high (default: settings.json, "
                                         "PRACTICE_EFFORT, or the Codex CLI default)")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("Port must be between 0 and 65535.")
    supervised = os.environ.get("PRACTICE_SUPERVISED") == "1"
    if not supervised and args.port:
        sys.exit(supervise(sys.argv[1:]))
    try:
        app = PracticeApp(model=args.model, effort=args.effort, auto_check=auto_check_enabled(args.no_update_check))
    except ArchiveError as exc:
        parser.exit(1, "Could not start the local app: {}\n".format(exc))
    try:
        server = make_server(app, args.port)
    except OSError as exc:
        parser.exit(1, "Could not start the local app: {}. Try --port 8766.\n".format(exc))
    exit_code = [0]
    if supervised:
        def restart():
            exit_code[0] = RESTART_CODE
            server.shutdown()
        app.restart = restart
    url = "http://127.0.0.1:{}/".format(server.server_port)
    print("Coding Practice Tracker is ready: " + url, flush=True)
    print("Quick recall model: " + archive.describe_model(app.model, app.effort), flush=True)
    print("Keep this window open. Press Ctrl-C to stop.", flush=True)
    if app.auto_check:
        def background_check():
            try:
                app.check_updates(force=False)
            except WebError:
                pass  # The page shows the recorded error; nothing to do here.
        threading.Thread(target=background_check, daemon=True).start()
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nFinishing any active archive before closing…", flush=True)
    finally:
        server.server_close()
        app.close()
    sys.exit(exit_code[0])


if __name__ == "__main__":
    require_python()
    main()
