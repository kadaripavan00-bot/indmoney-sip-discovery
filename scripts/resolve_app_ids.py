"""Resolve App Store and Play Store IDs for INDmoney and competitor apps."""

from __future__ import annotations

import requests
from google_play_scraper import search

TERMS = ["INDmoney", "Groww", "Zerodha Coin", "Kuvera", "ET Money", "Paytm Money"]


def itunes(term: str) -> list[tuple]:
    response = requests.get(
        "https://itunes.apple.com/search",
        params={"term": term, "country": "in", "entity": "software", "limit": 5},
        timeout=30,
    )
    response.raise_for_status()
    return [
        (item.get("trackName"), item.get("trackId"), item.get("bundleId"))
        for item in response.json().get("results", [])
    ]


def play(term: str) -> list[tuple]:
    try:
        return [
            (item.get("appId"), item.get("title"))
            for item in search(term, lang="en", country="in", n_hits=5)
        ]
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", str(exc))]


for term in TERMS:
    print(f"\n=== {term} ===")
    try:
        print("App Store:")
        for row in itunes(term):
            print("  ", row)
    except Exception as exc:  # noqa: BLE001
        print("  App Store error:", exc)
    print("Play Store:")
    for row in play(term):
        print("  ", row)
