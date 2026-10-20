"""Find Play Store package IDs by parsing the public search page."""

from __future__ import annotations

import re
import time

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
}

for term in ["INDmoney", "Kuvera", "Paytm Money"]:
    print(f"\n=== {term} ===")
    try:
        response = requests.get(
            "https://play.google.com/store/search",
            params={"q": term, "c": "apps", "hl": "en_IN", "gl": "IN"},
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        ids = []
        for match in re.findall(r"/store/apps/details\?id=([a-zA-Z0-9_.]+)", response.text):
            if match not in ids:
                ids.append(match)
        for app_id in ids[:8]:
            print("  ", app_id)
    except Exception as exc:  # noqa: BLE001
        print("  error:", type(exc).__name__, exc)
    time.sleep(2)
