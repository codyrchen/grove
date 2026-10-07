"""Ole Miss news headlines from RSS or Atom feeds.

The feed list is in NEWS_FEEDS (space-separated URLs) so it can change without a deploy.
"""

import html
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

DEFAULT_FEEDS = "https://news.olemiss.edu/feed/"
MAX_ITEMS = 8
USER_AGENT = "Grove/0.1 (Ole Miss student dashboard)"

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}
IMG_SRC = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.I)
TAG = re.compile(r"<[^>]+>")


def feeds() -> list[str]:
    return os.environ.get("NEWS_FEEDS", DEFAULT_FEEDS).split()


def clean(text: str | None, limit: int = 200) -> str:
    text = html.unescape(TAG.sub(" ", text or ""))
    text = " ".join(text.split())
    # WordPress excerpts end with "The post X appeared first on Y."
    text = re.sub(r"\s*The post .* appeared first on .*$", "", text)
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def parse_date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)  # RSS: "Tue, 06 Oct 2026 14:00:00 +0000"
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))  # Atom
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _image(item: ET.Element, body: str) -> str | None:
    for path in ("media:content", "media:thumbnail"):
        node = item.find(path, NS)
        if node is not None and node.get("url"):
            return node.get("url")
    enc = item.find("enclosure")
    if enc is not None and (enc.get("type") or "").startswith("image/"):
        return enc.get("url")
    m = IMG_SRC.search(body or "")
    return html.unescape(m.group(1)) if m else None


def _safe_url(url: str | None) -> str | None:
    url = (url or "").strip()
    return url if url.startswith(("https://", "http://")) else None


def parse(xml_text: str | bytes) -> list[dict]:
    root = ET.fromstring(xml_text)
    items = []
    if root.tag == f"{{{NS['atom']}}}feed":
        for e in root.findall("atom:entry", NS):
            link = e.find("atom:link[@rel='alternate']", NS)
            if link is None:
                link = e.find("atom:link", NS)
            body = e.findtext("atom:content", "", NS) or e.findtext("atom:summary", "", NS)
            items.append({
                "title": clean(e.findtext("atom:title", "", NS), 160),
                "url": _safe_url(link.get("href") if link is not None else None),
                "date": parse_date(e.findtext("atom:published", None, NS)
                                   or e.findtext("atom:updated", None, NS)),
                "summary": clean(e.findtext("atom:summary", "", NS) or body),
                "image": _safe_url(_image(e, body)),
            })
    else:
        for it in root.iter("item"):
            body = it.findtext("content:encoded", "", NS)
            items.append({
                "title": clean(it.findtext("title"), 160),
                "url": _safe_url(it.findtext("link")),
                "date": parse_date(it.findtext("pubDate")),
                "summary": clean(it.findtext("description") or body),
                "image": _safe_url(_image(it, body or it.findtext("description", ""))),
            })
    return [i for i in items if i["title"] and i["url"]]


def fetch() -> dict:
    items, errors = [], []
    for url in feeds():
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            items.extend(parse(r.content))
        except Exception as e:  # one bad feed shouldn't hide the others
            errors.append(f"{url}: {e}")
    if not items:
        raise RuntimeError("no news items; " + "; ".join(errors))
    seen, unique = set(), []
    for i in sorted(items, key=lambda i: i["date"] or "", reverse=True):
        if i["url"] not in seen:
            seen.add(i["url"])
            unique.append(i)
    return {"items": unique[:MAX_ITEMS]}
