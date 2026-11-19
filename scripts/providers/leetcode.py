"""LeetCode: numbers, slugs and URLs; statements fetched when possible."""

from html.parser import HTMLParser
import json
import re
from urllib.parse import urlparse

from common import ArchiveError, atomic_write
from .base import Provider, check_title

HOSTS = ("leetcode.com", "www.leetcode.com", "leetcode.cn")
GRAPHQL = """query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) { questionFrontendId title titleSlug content }
}"""


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if tag in ("p", "li", "br", "div", "h1", "h2", "h3") and not self.skip:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def plain_text(html):
    parser = PlainText()
    parser.feed(html)
    return re.sub(r"[ \t]+", " ", "".join(parser.parts)).strip()


def identity(entry, host="leetcode.com"):
    entry = dict(entry)
    entry.setdefault("companies", [])
    entry.setdefault("tags", [])
    entry.setdefault("related", [])
    entry.update(platform="leetcode", url="https://{}/problems/{}/".format(host, entry["slug"]))
    entry["key"] = "{:04d}-{}".format(int(entry["id"]), entry["slug"])
    return entry


def manual_identity(url, ident, title):
    parsed = urlparse(url or "")
    match = re.match(r"^/problems/([a-z0-9-]+)(?:/|$)", parsed.path)
    if not (ident and str(ident).isdigit() and (title or "").strip() and match
            and parsed.scheme == "https" and parsed.hostname in HOSTS):
        raise ArchiveError("Manual identity needs a LeetCode URL, numeric display ID, and title.")
    host = "leetcode.cn" if parsed.hostname == "leetcode.cn" else "leetcode.com"
    return identity({"id": str(int(ident)), "slug": match[1], "title": check_title(title)}, host)


class LeetCode(Provider):
    name = "leetcode"
    label = "LeetCode"
    hosts = ("leetcode.com", "leetcode.cn")
    title = "auto"
    display_id = "fallback"
    statement = "fetch"
    placeholder = "0001, two-sum, or https://leetcode.com/problems/two-sum/"
    help = "Enter a display number, title slug, or problem URL. The title and statement are looked up."

    def matches(self, value):
        parsed = urlparse((value or "").strip())
        return parsed.scheme in ("http", "https") and parsed.hostname in HOSTS

    def accepts_shorthand(self, value):
        value = (value or "").strip()
        return value.isdigit() or bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", value))

    def heading_prefix(self, problem):
        return problem["id"].zfill(4) + ". " if problem.get("id") else ""

    def same_problem(self, existing, problem):
        return existing.get("key") == problem.get("key")

    def resolve(self, ctx, value, title="", display_id=""):
        value = (value or "").strip()
        host = "leetcode.com"
        if value.startswith("https://") or value.startswith("http://"):
            parsed = urlparse(value)
            if parsed.scheme != "https" or parsed.hostname not in HOSTS:
                raise ArchiveError("Use a leetcode.com or leetcode.cn problem URL.")
            match = re.match(r"^/problems/([a-z0-9-]+)(?:/|$)", parsed.path)
            if not match:
                raise ArchiveError("The URL must point to /problems/<slug>/.")
            value = match.group(1)
            host = "leetcode.cn" if parsed.hostname == "leetcode.cn" else host
        known = ctx.catalogue()
        if value.isdigit():
            ident = str(int(value))
            entry = next((p for p in known if p["id"] == ident), None)
            if not entry:
                local = ctx.local(self.name, "{:04d}-*".format(int(ident)))
                if local:
                    return local
            if not entry:
                try:
                    data = json.loads(ctx.fetch("https://{}/api/problems/all/".format(host)))
                    entries = [{"id": str(p["stat"]["frontend_question_id"]),
                                "slug": p["stat"]["question__title_slug"],
                                "title": p["stat"]["question__title"]}
                               for p in data["stat_status_pairs"]]
                    atomic_write(ctx.root / ".cache/leetcode-catalogue.json", json.dumps(entries))
                    entry = next((p for p in entries if p["id"] == ident), None)
                except (ArchiveError, KeyError, ValueError, TypeError):
                    pass
            if not entry:
                raise ArchiveError("Could not resolve this number. Paste its problem URL instead.")
        else:
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
                raise ArchiveError("Enter a problem number, URL, or lowercase title slug.")
            entry = next((p for p in known if p["slug"] == value), None)
            if not entry:
                # Reuse a locally archived identity even when the catalogue is unavailable.
                local = ctx.local(self.name, "*-" + value)
                if local:
                    return local
                try:
                    question = json.loads(ctx.fetch("https://{}/graphql/".format(host), {
                        "query": GRAPHQL, "variables": {"titleSlug": value}}))["data"]["question"]
                    entry = {"id": str(question["questionFrontendId"]), "slug": value,
                             "title": question["title"],
                             "statement": plain_text(question["content"] or ""),
                             "provenance": "Retrieved from the source platform."}
                except (ArchiveError, KeyError, ValueError, TypeError):
                    raise ArchiveError("Could not resolve this URL. Enter its display number and title.")
        return identity({k: v for k, v in entry.items() if k not in ("url", "key", "platform")}, host)

    def fetch_statement(self, ctx, problem):
        host = urlparse(problem["url"]).hostname
        question = json.loads(ctx.fetch("https://{}/graphql/".format(host), {
            "query": GRAPHQL, "variables": {"titleSlug": problem["slug"]}}))["data"]["question"]
        if str(question["questionFrontendId"]) != problem["id"]:
            raise ArchiveError("Source returned a different problem number.")
        return plain_text(question["content"] or ""), "Retrieved from the source platform."
