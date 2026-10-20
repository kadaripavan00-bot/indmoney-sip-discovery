"""Apple App Store review collector using the public RSS feed."""

from __future__ import annotations

import time
from datetime import datetime

import requests

from .base import RawDocument

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
}


class AppStoreCollector:
    def __init__(self, country: str = "in", pages: int = 5) -> None:
        self.country = country
        self.pages = pages
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _fetch_page(self, app_id: str, page: int) -> list[dict]:
        url = (
            f"https://itunes.apple.com/{self.country}/rss/customerreviews/"
            f"page={page}/id={app_id}/sortby=mostrecent/json"
        )
        for attempt in range(3):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                entries = response.json().get("feed", {}).get("entry", [])
                if isinstance(entries, dict):
                    entries = [entries]
                return entries
            except Exception as exc:  # noqa: BLE001
                if attempt == 2:
                    print(f"[app_store] failed {app_id} page {page}: {exc}")
                time.sleep(2 ** attempt)
        return []

    def collect(self, app_id: str, app_name: str) -> list[RawDocument]:
        documents: list[RawDocument] = []
        for page in range(1, self.pages + 1):
            entries = self._fetch_page(app_id, page)
            if not entries:
                break

            for entry in entries:
                if "im:rating" not in entry:
                    continue

                text = entry.get("content", {}).get("label", "")
                if not text:
                    continue

                published_raw = entry.get("updated", {}).get("label")
                published = None
                if published_raw:
                    try:
                        published = datetime.fromisoformat(
                            published_raw.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                    except ValueError:
                        published = None

                documents.append(
                    RawDocument(
                        external_id=entry.get("id", {}).get("label"),
                        url=entry.get("link", {}).get("attributes", {}).get("href"),
                        author=entry.get("author", {}).get("name", {}).get("label"),
                        published_at=published,
                        text=text,
                        language="en",
                        meta={
                            "source": "app_store",
                            "app_id": app_id,
                            "app_name": app_name,
                            "score": entry.get("im:rating", {}).get("label"),
                            "title": entry.get("title", {}).get("label"),
                        },
                    )
                )
            time.sleep(1)
        return documents
