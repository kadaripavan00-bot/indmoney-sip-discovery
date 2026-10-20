"""Text normalization, hashing, and relevance helpers."""

from __future__ import annotations

import hashlib
import re

from bs4 import BeautifulSoup

WHITESPACE_RE = re.compile(r"\s+")
DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

RELEVANCE_KEYWORDS = [
    "sip",
    "mutual fund",
    "nav",
    "xirr",
    "folio",
    "mandate",
    "auto debit",
    "autopay",
    "instalment",
    "installment",
    "portfolio",
    "invest",
    "indmoney",
    "groww",
    "coin",
    "kuvera",
    "et money",
    "paytm money",
]

STRICT_RELEVANCE_PATTERNS = [
    r"\bsips?\b",
    r"mutual fund",
    r"\bnav\b",
    r"\bxirr\b",
    r"\bfolio\b",
    r"\bmandate\b",
    r"auto debit",
    r"\bautopay\b",
    r"\binstal?ment\b",
    r"systematic investment",
]


def normalize_text(text: str) -> str:
    if not text:
        return ""
    soup = BeautifulSoup(text, "lxml")
    cleaned = soup.get_text(" ", strip=True)
    cleaned = cleaned.replace("\u200b", " ").replace("\xa0", " ")
    return WHITESPACE_RE.sub(" ", cleaned).strip()


def content_hash(text: str) -> str:
    normalized = normalize_text(text).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def hash_author(source: str, author: str) -> str:
    return hashlib.sha256(f"{source}:{author}".encode("utf-8")).hexdigest()


def detect_language(text: str) -> str:
    if DEVANAGARI_RE.search(text):
        return "hi"
    return "en"


def is_relevant(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in RELEVANCE_KEYWORDS)


def is_strictly_relevant(text: str) -> bool:
    """A narrower candidate filter for SIP / mutual-fund extraction."""
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in STRICT_RELEVANCE_PATTERNS)
