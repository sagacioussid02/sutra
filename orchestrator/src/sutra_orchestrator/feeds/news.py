"""Headlines for a topic from Google News RSS. Everything in them is untrusted text."""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .http import Fetch

NEWS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
MAX_HEADLINES = 3
TITLE_CHARS = 110
_TAGS = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Headline:
    title: str
    source: str


def _clean(text: str) -> str:
    return " ".join(_TAGS.sub(" ", text or "").split())


def parse(xml_text: str) -> list[Headline]:
    """Up to three headlines, newest first as the feed gives them. Defensive: bad XML gives nothing."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out: list[Headline] = []
    seen: set[str] = set()
    for item in root.findall("./channel/item"):
        source = _clean(item.findtext("source") or "")
        title = _clean(item.findtext("title") or "")
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3].rstrip()
        key = title.lower()
        if len(title) < 8 or key in seen:
            continue
        seen.add(key)
        out.append(Headline(title[:TITLE_CHARS], source[:40]))
        if len(out) >= MAX_HEADLINES:
            break
    return out


async def headlines(topic: str, fetch: Fetch) -> list[Headline]:
    body = await fetch(NEWS.format(q=urllib.parse.quote(f"{topic} when:1d")))
    return parse(body) if body else []


def summary(topic: str, items: list[Headline]) -> str:
    return f"Top stories on {topic}: " + "; ".join(f"{h.title} ({h.source})" if h.source else h.title for h in items)
