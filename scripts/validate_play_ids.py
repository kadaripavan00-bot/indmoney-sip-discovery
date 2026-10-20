"""Validate candidate Google Play package IDs for the target apps."""

from __future__ import annotations

import time

from google_play_scraper import app

CANDIDATES = [
    "in.indwealth",
    "com.indmoney.app",
    "com.nextbillion.groww",
    "com.zerodha.coin",
    "com.kuvera.android",
    "in.kuvera.android",
    "com.kuvera.app",
    "com.etmoney.app",
    "com.smartspends",
    "com.paytmmoney",
]

for app_id in CANDIDATES:
    try:
        info = app(app_id, lang="en", country="in")
        print(f"OK   {app_id:28s} | {info.get('title')} | {info.get('developer')}")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL {app_id:28s} | {type(exc).__name__}: {exc}")
    time.sleep(0.5)
