"""YouTube comment collector using yt-dlp."""

from __future__ import annotations

import time
from datetime import datetime

import yt_dlp

from .base import RawDocument


class YouTubeCollector:
    def __init__(self, max_videos: int = 2, max_comments: int = 300) -> None:
        self.max_videos = max_videos
        self.max_comments = max_comments

    def _search(self, query: str) -> list[dict]:
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
            "noplaylist": True,
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(
                    f"ytsearch{self.max_videos}:{query}",
                    download=False,
                )
            return info.get("entries", []) if info else []
        except Exception as exc:  # noqa: BLE001
            print(f"[youtube] search failed q={query}: {exc}")
            return []

    def _comments(self, video_url: str) -> dict:
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "getcomments": True,
            "max_comments": self.max_comments,
            "extract_flat": False,
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                return ydl.extract_info(video_url, download=False) or {}
        except Exception as exc:  # noqa: BLE001
            print(f"[youtube] comments failed {video_url}: {exc}")
            return {}

    def collect(self, query: str) -> list[RawDocument]:
        documents: list[RawDocument] = []
        for entry in self._search(query):
            video_id = entry.get("id")
            if not video_id:
                continue

            video_url = f"https://www.youtube.com/watch?v={video_id}"
            info = self._comments(video_url)
            comments = info.get("comments") or []

            for index, comment in enumerate(comments[: self.max_comments]):
                text = (comment.get("text") or "").strip()
                if not text:
                    continue

                timestamp = comment.get("timestamp")
                published = datetime.utcfromtimestamp(timestamp) if timestamp else None
                documents.append(
                    RawDocument(
                        external_id=comment.get("id") or f"{video_id}:{index}",
                        url=video_url,
                        author=comment.get("author"),
                        published_at=published,
                        text=text,
                        language="en",
                        meta={
                            "source": "youtube",
                            "video_id": video_id,
                            "video_title": info.get("title"),
                            "query": query,
                            "like_count": comment.get("like_count"),
                        },
                    )
                )
            time.sleep(2)
        return documents
