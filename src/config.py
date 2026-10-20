"""Configuration loading for the discovery engine."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _load_yaml(name: str) -> dict[str, Any]:
    path = PROJECT_ROOT / "config" / name
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


@lru_cache(maxsize=1)
def settings() -> dict[str, Any]:
    default_db = PROJECT_ROOT / "data" / "indmoney.db"
    database_url = os.getenv("DATABASE_URL", f"sqlite:///{default_db.as_posix()}")
    return {
        "project_root": PROJECT_ROOT,
        "database_url": database_url,
        "sources": _load_yaml("sources.yaml"),
        "models": _load_yaml("models.yaml"),
        "codebook": _load_yaml("codebook.yaml"),
    }


def get_secret(name: str) -> str | None:
    value = os.getenv(name)
    return value.strip() if value else None
