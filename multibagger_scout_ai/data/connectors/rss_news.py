"""Public RSS news search. Headlines are NOT verified evidence; they are tagged accordingly downstream."""
import urllib.parse
from datetime import timezone
from email.utils import parsedate_to_datetime

import requests
from defusedxml import ElementTree as ET  # safe against XML entity attacks

from config import settings
from data.connectors.base import ProviderError


class RssNewsConnector:
    name = "rss_news"

    def fetch(self, query: str) -> list:
        url = settings.NEWS_FEED_TEMPLATE.format(query=urllib.parse.quote_plus(query))
        try:
            resp = requests.get(url, timeout=settings.HTTP_TIMEOUT, headers={"User-Agent": "MultibaggerScoutAI/0.1"})
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as exc:
            raise ProviderError(f"news feed failed: {exc}") from exc
        items = []
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            if not title:
                continue
            published = None
            raw = it.findtext("pubDate")
            if raw:
                try:
                    published = parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
                except (TypeError, ValueError):
                    published = None
            src = it.find("source")
            items.append({"headline": title, "url": (it.findtext("link") or "").strip(),
                          "published_at": published, "source": (src.text if src is not None else None)})
            if len(items) >= settings.NEWS_MAX_ITEMS:
                break
        return items
