"""Registry of practice sites. Add a site by adding a Provider subclass here."""

from .base import Context, Provider, comparable_url
from .leetcode import LeetCode, manual_identity, plain_text
from .sites import (CodeSignal, GeeksforGeeks, Hack2Hire, HackerRank, LintCode, Manual,
                    NeetCode, OnePoint3Acres, Other)
from common import ArchiveError

# Detection order: specific sites first, "other" accepts any HTTPS URL.
PROVIDERS = [LeetCode(), Hack2Hire(), LintCode(), NeetCode(), HackerRank(), CodeSignal(),
             GeeksforGeeks(), OnePoint3Acres(), Other(), Manual()]
BY_NAME = {p.name: p for p in PROVIDERS}


def names():
    return tuple(BY_NAME)


def get(name):
    try:
        return BY_NAME[name]
    except KeyError:
        raise ArchiveError("Unknown platform: {}".format(name)) from None


def label(name):
    provider = BY_NAME.get(name)
    return provider.label if provider else name


def detect(value):
    """Choose a provider from what the user pasted, or None if ambiguous."""
    value = (value or "").strip()
    for provider in PROVIDERS:
        if provider.matches(value):
            return provider
    if BY_NAME["leetcode"].accepts_shorthand(value):
        return BY_NAME["leetcode"]
    return None


def public():
    return [p.public() for p in PROVIDERS]


__all__ = ["Context", "Provider", "PROVIDERS", "comparable_url", "detect", "get", "label",
           "manual_identity", "names", "plain_text", "public"]
