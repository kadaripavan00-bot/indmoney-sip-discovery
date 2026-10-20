"""Inspect forum search pages to design the collectors."""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def inspect_tradingqna() -> None:
    print("=== TradingQ&A ===")
    response = requests.get("https://tradingqna.com/search?q=SIP", headers=HEADERS, timeout=30)
    print("status:", response.status_code, "bytes:", len(response.text))
    soup = BeautifulSoup(response.text, "lxml")
    print("title:", soup.title.string if soup.title else None)
    links = soup.find_all("a", href=True)
    print("links:", len(links))
    for anchor in links[:30]:
        text = anchor.get_text(" ", strip=True)
        if text:
            print("  ", text[:90], "|", anchor["href"][:120])


def inspect_valuepickr() -> None:
    print("\n=== ValuePickr ===")
    response = requests.get(
        "https://forum.valuepickr.com/search.json",
        params={"q": "SIP mutual fund"},
        headers=HEADERS,
        timeout=30,
    )
    print("status:", response.status_code)
    data = response.json()
    print("keys:", list(data.keys()))
    print("posts:", len(data.get("posts", [])), "topics:", len(data.get("topics", [])))
    if data.get("posts"):
        post = data["posts"][0]
        print("post keys:", list(post.keys()))
        print("sample:", {k: post.get(k) for k in ("id", "topic_id", "post_number", "username", "blurb")})


if __name__ == "__main__":
    inspect_tradingqna()
    inspect_valuepickr()
