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
import threading
from urllib.parse import parse_qs, urlparse
import webbrowser

import archive
import report

ROOT = archive.ROOT


class WebError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def recall_block(text):
    start, end = archive.marker("recall", "start"), archive.marker("recall", "end")
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
    if not isinstance(value, str) or len(value) > limit:
        raise WebError("Invalid or oversized field: " + key)
    if required and not value.strip():
        raise WebError("Please fill in " + key.replace("_", " ") + ".")
    return value


class PracticeApp:
    def __init__(self, root=ROOT, model=None, timeout=120):
        self.root = Path(root).resolve()
        self.model = model or os.environ.get("PRACTICE_MODEL", "gpt-6-luna")
        self.timeout = timeout
        self.token = secrets.token_urlsafe(32)
        self.jobs = {}
        self.mutex = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="practice")

    def close(self):
        self.pool.shutdown(wait=True)

    def folder(self, key):
        if not isinstance(key, str) or not re.fullmatch(r"(?:leetcode|hack2hire)/[A-Za-z0-9_-]+", key):
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

    def problem(self, key):
        folder = self.folder(key)
        identity = archive.load_problem(self.root, folder)
        text = (folder / "README.md").read_text(encoding="utf-8")
        codes = archive.practice_files(folder)
        if not codes or codes[-1].resolve().parent != folder:
            raise WebError("No archived practice was found.", 404)
        latest = codes[-1]
        content = latest.read_text(encoding="utf-8")
        status = re.search(r"(?m)^# Practice: (independent|improved|learned)$", content)
        difficulty = re.search(r"\A# Practice: [a-z]+\n# Difficulty: ([1-5])\n", content)
        return {"key": key, "title": identity["title"], "source": identity["url"],
                "platform": identity["platform"], "filename": latest.name,
                "readme_path": str((folder / "README.md").relative_to(self.root)),
                "status": status[1] if status else "unknown",
                "difficulty": int(difficulty[1]) if difficulty else None,
                "code": content, "recall": recall_fields(text),
                "notes": text.split("## Practice notes", 1)[1].strip() if "## Practice notes" in text else ""}

    def listing(self):
        result = []
        for folder, entries in report.practices(self.root):
            identity = archive.load_problem(self.root, folder)
            date, _, status, _, difficulty = entries[-1]
            result.append({"key": folder.relative_to(self.root / "problems").as_posix(),
                           "title": identity["title"], "platform": identity["platform"],
                           "date": date, "status": status, "difficulty": difficulty,
                           "count": len(entries)})
        return sorted(result, key=lambda x: x["date"], reverse=True)

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
                latest = archive.practice_files(folder)[-1]
                prefix = "Based on [{}]({}).".format(latest.name, latest.name)
            prefix = prefix.replace("AI-generated from", "Based on")
            if "Edited in the local practice app." not in prefix:
                prefix += "\n\nEdited in the local practice app."
            replacement = prefix + "\n\n### 中文\n\n" + zh + "\n\n### English\n\n" + en
            archive.atomic_write(path, archive.replace_block(text, "recall", replacement))
        return self.problem(key)

    def submit(self, data, action="archive"):
        request_id = text_field(data, "request_id", True, 100)
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request_id):
            raise WebError("Invalid request identifier. Reload the page and try again.")
        if action == "archive":
            if data.get("platform") not in ("leetcode", "hack2hire"):
                raise WebError("Choose a platform.")
            text_field(data, "problem", True, 2000)
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
            if sum(j["state"] not in ("ready", "partial", "failed", "conflict") for j in self.jobs.values()) >= 8:
                raise WebError("Please wait for the current archives to finish.", 429)
            # Retain recent finished jobs for reconnecting tabs, with bounded memory.
            while len(self.jobs) >= 200:
                removable = next((k for k, v in self.jobs.items() if v["state"] in ("ready", "partial", "failed", "conflict")), None)
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

    def _work(self, ident, data, action):
        saved = False
        try:
            if action == "archive":
                self._set(ident, state="resolving", message="Finding the problem…")
                if data.get("display_id") or data.get("title"):
                    if data["platform"] != "leetcode":
                        raise WebError("The manual number and title fields are for LeetCode.")
                    problem = archive.manual_identity(data["problem"], data.get("display_id", ""), data.get("title", ""))
                else:
                    problem = archive.resolve_problem(self.root, data["platform"], data["problem"])
                with archive.archive_lock(self.root):
                    from datetime import datetime
                    date = datetime.now(archive.ZoneInfo("America/Los_Angeles")).strftime("%Y%m%d")
                    code = archive.save_practice(self.root, problem, data["code"], data["status"],
                                                 data.get("notes", ""), date, data["difficulty"])
            else:
                folder = self.folder(data["key"])
                problem = archive.load_problem(self.root, folder)
                code = archive.practice_files(folder)[-1]
            saved = True
            key = code.parent.relative_to(self.root / "problems").as_posix()
            self._set(ident, state="saved", key=key, message="Code and notes saved. Preparing Quick recall…")
            with archive.archive_lock(self.root):
                before = (code.parent / "README.md").read_text(encoding="utf-8")
                initial_revision = recall_fields(before)["revision"]
            if action == "archive" and "AI summary pending." not in before and "Source summary pending." not in before:
                self._set(ident, state="ready", message="Practice saved. Your existing Quick recall is ready to edit.")
                return
            source = archive.source_for(self.root, problem, data.get("statement") or None)
            self._set(ident, state="generating", message="Practice saved. Writing Chinese and English recall…")
            summary = archive.generate_summary(problem, source, code.read_text(encoding="utf-8"),
                                                data.get("notes", ""), self.model, self.timeout)
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
                message = "Practice and recall saved. Problem facts are still pending; add source text when regenerating."
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

    def allowed(self, mutation=False):
        host = "127.0.0.1:" + str(self.server.server_port)
        if self.headers.get("Host") != host:
            raise WebError("Use the local URL printed by web.command.", 403)
        if mutation and self.headers.get("Origin") != "http://" + host:
            raise WebError("Open the local practice page to make changes.", 403)

    def api_auth(self):
        if not secrets.compare_digest(self.headers.get("X-Practice-Token", ""), self.app.token):
            raise WebError("Reload the local page to reconnect.", 403)

    def do_GET(self):
        try:
            self.allowed()
            parsed = urlparse(self.path)
            static = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/style.css": ("style.css", "text/css; charset=utf-8")}
            if parsed.path in static:
                name, kind = static[parsed.path]
                body = (ROOT / "web" / name).read_bytes()
                if name == "index.html":
                    body = body.replace(b"__PRACTICE_TOKEN__", self.app.token.encode())
                self.send_body(200, body, kind)
                return
            if parsed.path == "/api/health":
                self.send_body(200, {"ok": True})
                return
            if parsed.path == "/favicon.ico":
                self.send_body(204, b"", "image/x-icon")
                return
            self.api_auth()
            query = parse_qs(parsed.query)
            if parsed.path == "/api/problems":
                self.send_body(200, {"problems": self.app.listing()})
            elif parsed.path == "/api/problem":
                self.send_body(200, self.app.problem(query.get("key", [""])[0]))
            elif parsed.path == "/api/job":
                self.send_body(200, self.app.job(query.get("id", [""])[0]))
            else:
                raise WebError("Page not found.", 404)
        except WebError as exc:
            self.send_body(exc.status, {"error": str(exc)})
        except (OSError, ValueError, archive.ArchiveError) as exc:
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
            if self.path == "/api/archive":
                self.send_body(202, self.app.submit(data))
            elif self.path == "/api/generate":
                self.send_body(202, self.app.submit(data, "generate"))
            elif self.path == "/api/recall":
                self.send_body(200, self.app.save_recall(data))
            else:
                raise WebError("Page not found.", 404)
        except WebError as exc:
            self.send_body(exc.status, {"error": str(exc)})
        except (OSError, ValueError, archive.ArchiveError) as exc:
            self.send_body(400, {"error": str(exc)})


def make_server(app, port=8765):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.app = app
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--model", default=os.environ.get("PRACTICE_MODEL", "gpt-6-luna"))
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("Port must be between 0 and 65535.")
    app = PracticeApp(model=args.model)
    try:
        server = make_server(app, args.port)
    except OSError as exc:
        parser.exit(1, "Could not start the local app: {}. Try --port 8766.\n".format(exc))
    url = "http://127.0.0.1:{}/".format(server.server_port)
    print("Coding practice is ready: " + url, flush=True)
    print("Keep this terminal open. Press Ctrl-C to stop.", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nFinishing any active archive before closing…", flush=True)
    finally:
        server.server_close()
        app.close()


if __name__ == "__main__":
    main()
