"""Provider interface: how one practice site identifies a problem."""

import re
from urllib.parse import parse_qsl, urlencode, urlparse

from common import ArchiveError, short_hash, slugify

TRACKING = re.compile(r"^(utm_\w*|ref|referrer|source|from|spm|fbclid|gclid|share\w*|_ga|si)$", re.I)
TITLE_LIMIT = 200


class Context:
    """Late-bound services a provider may use (patched in tests)."""

    def __init__(self, root, fetch=None, catalogue=None, local=None):
        self.root = root
        self.fetch = fetch
        self.catalogue = catalogue or (lambda: [])
        self.local = local or (lambda platform, pattern: None)


def check_title(title):
    title = (title or "").strip()
    if len(title.splitlines()) > 1 or len(title) > TITLE_LIMIT:
        raise ArchiveError("Problem title must be one line of at most {} characters.".format(TITLE_LIMIT))
    return title


def check_display_id(value):
    value = (value or "").strip()
    if value and not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", value):
        raise ArchiveError("Display number may only contain letters, digits, '.', '_' and '-'.")
    return value


def comparable_url(url):
    """Equality key for URLs: scheme/www/trailing-slash insensitive."""
    if not url:
        return ""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    query = "?" + parsed.query if parsed.query else ""
    return host + parsed.path.rstrip("/") + query


class Provider:
    name = ""
    label = ""
    hosts = ()
    url = "required"          # "required" | "none"
    title = "required"        # "required" for new problems | "auto" (looked up)
    display_id = "optional"   # "optional" | "none"
    statement = "manual"      # "manual" (pasted Markdown) | "fetch" (retrieved when possible)
    placeholder = "https://…"
    help = "Paste the exact problem URL, its title, and the statement in Markdown."
    keep_query = None         # None keeps non-tracking parameters; a tuple keeps only those keys.
    id_pattern = None         # Regex with one group that extracts a display number from the URL path.

    # --- URL handling -------------------------------------------------
    def host_matches(self, host):
        host = (host or "").lower()
        return any(host == h or host.endswith("." + h) for h in self.hosts)

    def matches(self, value):
        parsed = urlparse((value or "").strip())
        return parsed.scheme in ("http", "https") and bool(self.hosts) and self.host_matches(parsed.hostname)

    def keep(self, key):
        if self.keep_query is not None:
            return key in self.keep_query
        return not TRACKING.match(key)

    def canonical_host(self, host):
        return host

    def canonical_url(self, value):
        value = (value or "").strip()
        if len(value) > 2000:
            raise ArchiveError("The problem URL is too long.")
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ArchiveError("Enter the exact HTTPS {} problem URL.".format(self.label))
        if self.hosts and not self.host_matches(parsed.hostname):
            raise ArchiveError("Use a {} URL ({}).".format(self.label, ", ".join(self.hosts)))
        path = re.sub(r"/{2,}", "/", parsed.path).rstrip("/")
        if not path:
            raise ArchiveError("This URL does not identify a problem page.")
        query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if self.keep(k)]
        host = self.canonical_host(parsed.hostname.lower())
        url = "https://" + host + (":{}".format(parsed.port) if parsed.port else "") + path
        if query:
            url += "?" + urlencode(query)
        return url

    def url_slug(self, url):
        segments = [s for s in urlparse(url).path.split("/") if s]
        return segments[-1] if segments else ""

    def display_id_from_url(self, url):
        if not self.id_pattern:
            return ""
        match = re.search(self.id_pattern, urlparse(url).path)
        return match.group(1) if match else ""

    def companies_from_url(self, url):
        return []

    def group_of(self, problem):
        """Problems sharing a group (e.g. Part 1/2/3) are linked as related."""
        return None

    # --- Identity -----------------------------------------------------
    def new_key(self, title, slug, url):
        return slugify(title or slug) + "-" + short_hash(url)

    def resolve(self, ctx, value, title="", display_id=""):
        url = self.canonical_url(value)
        title = check_title(title)
        ident = check_display_id(display_id) or self.display_id_from_url(url)
        slug = self.url_slug(url)
        fallback = re.sub(r"[-_]+", " ", slug).strip().title() or self.label + " problem"
        return {"platform": self.name, "key": self.new_key(title, slug, url), "id": ident,
                "slug": slug, "title": title or fallback, "url": url,
                "companies": self.companies_from_url(url), "tags": [], "related": []}

    def same_problem(self, existing, problem):
        return bool(problem.get("url")) and comparable_url(existing.get("url")) == comparable_url(problem["url"])

    def heading_prefix(self, problem):
        return ""

    def fetch_statement(self, ctx, problem):
        """Return (statement, provenance) or None. Most sites use pasted Markdown."""
        return None

    def public(self):
        return {"name": self.name, "label": self.label, "hosts": list(self.hosts), "url": self.url,
                "title": self.title, "display_id": self.display_id, "statement": self.statement,
                "placeholder": self.placeholder, "help": self.help}
