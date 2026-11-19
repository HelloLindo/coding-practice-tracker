"""Sites whose statements are pasted as Markdown (no page scraping)."""

import re
from urllib.parse import urlparse

from common import ArchiveError, short_hash, slugify
from .base import Provider, check_display_id, check_title

COMPANY_NAMES = {
    "airbnb": "Airbnb", "amazon": "Amazon", "apple": "Apple", "bytedance": "ByteDance",
    "coinbase": "Coinbase", "databricks": "Databricks", "doordash": "DoorDash", "google": "Google",
    "instacart": "Instacart", "linkedin": "LinkedIn", "meta": "Meta", "microsoft": "Microsoft",
    "netflix": "Netflix", "openai": "OpenAI", "pinterest": "Pinterest", "robinhood": "Robinhood",
    "snowflake": "Snowflake", "stripe": "Stripe", "tiktok": "TikTok", "uber": "Uber",
}


def company_name(slug):
    slug = slug.strip().lower()
    return COMPANY_NAMES.get(slug) or " ".join(w.capitalize() for w in re.split(r"[-_]+", slug) if w)


class Hack2Hire(Provider):
    name = "hack2hire"
    label = "Hack2Hire"
    hosts = ("hack2hire.com",)
    keep_query = ("questionId",)  # The same practice path can serve multiple questions.
    placeholder = "https://www.hack2hire.com/question-bank/companies/…/practice"

    def canonical_host(self, host):
        return "www.hack2hire.com"

    def canonical_url(self, value):
        url = super().canonical_url(value)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.url_slug(url)):
            raise ArchiveError("This URL does not identify a question.")
        return url

    def companies_from_url(self, url):
        match = re.search(r"/companies/([A-Za-z0-9_-]+)/", urlparse(url).path)
        return [company_name(match.group(1))] if match else []

    def group_of(self, problem):
        """Part 1/2/3 of one question share a path and differ by questionId."""
        path = urlparse(problem.get("url", "")).path
        return path if "/coding-questions/" in path else None

    def new_key(self, title, slug, url):
        # Without a title this reproduces the original practice-<hash> folder names.
        return slugify(title or slug.lower()) + "-" + short_hash(url)


class LintCode(Provider):
    name = "lintcode"
    label = "LintCode"
    hosts = ("lintcode.com",)
    id_pattern = r"/problem/(\d+)"
    keep_query = ()
    placeholder = "https://www.lintcode.com/problem/663/"


class NeetCode(Provider):
    name = "neetcode"
    label = "NeetCode"
    hosts = ("neetcode.io",)
    keep_query = ()
    placeholder = "https://neetcode.io/problems/…"


class HackerRank(Provider):
    name = "hackerrank"
    label = "HackerRank"
    hosts = ("hackerrank.com",)
    keep_query = ()
    placeholder = "https://www.hackerrank.com/challenges/…/problem"

    def url_slug(self, url):
        match = re.search(r"/challenges/([^/]+)", urlparse(url).path)
        return match.group(1) if match else super().url_slug(url)


class CodeSignal(Provider):
    name = "codesignal"
    label = "CodeSignal"
    hosts = ("codesignal.com",)
    placeholder = "https://app.codesignal.com/…"


class GeeksforGeeks(Provider):
    name = "geeksforgeeks"
    label = "GeeksforGeeks"
    hosts = ("geeksforgeeks.org",)
    keep_query = ()
    placeholder = "https://www.geeksforgeeks.org/problems/…"


class OnePoint3Acres(Provider):
    name = "1point3acres"
    label = "1Point3Acres"
    hosts = ("1point3acres.com", "1point3acres.cn")
    placeholder = "https://www.1point3acres.com/bbs/thread-…"
    help = "Paste the post URL, a title for this question, and the question in Markdown."


class Other(Provider):
    """Any other HTTPS page; detected last."""
    name = "other"
    label = "Other website"
    hosts = ()
    placeholder = "https://example.com/problem/…"

    def matches(self, value):
        return urlparse((value or "").strip()).scheme in ("http", "https")


class Manual(Provider):
    """Interview questions or write-ups without a link."""
    name = "manual"
    label = "No link"
    url = "none"
    placeholder = ""
    help = "For a question without a page: give it a title and paste the statement in Markdown."

    def matches(self, value):
        return False

    def resolve(self, ctx, value, title="", display_id=""):
        title = check_title(title) or check_title(value)
        if not title:
            raise ArchiveError("Enter a title for this problem.")
        return {"platform": self.name, "key": self.new_key(title, "", self.norm(title)),
                "id": check_display_id(display_id), "slug": "", "title": title, "url": "",
                "companies": [], "tags": [], "related": []}

    def new_key(self, title, slug, url):
        return slugify(title) + "-" + short_hash("manual:" + self.norm(title))

    @staticmethod
    def norm(title):
        return " ".join(title.casefold().split())

    def same_problem(self, existing, problem):
        return self.norm(existing.get("title", "")) == self.norm(problem.get("title", ""))
