"""Smoke-test the LLM providers through LiteLLM."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from litellm import completion

load_dotenv()

GEMINI_MODELS = [
    "gemini/gemini-3.5-flash-lite",
    "gemini/gemini-3.8-flash",
    "gemini/gemini-flash-lite-latest",
    "gemini/gemini-flash-latest",
]

GROQ_MODELS = [
    "groq/openai/gpt-oss-20b",
    "groq/openai/gpt-oss-120b",
    "groq/qwen/qwen3.8-27b",
]

PROMPT = 'Return exactly this JSON and nothing else: {"ok": true}'

for model in GEMINI_MODELS:
    try:
        response = completion(
            model=model,
            messages=[{"role": "user", "content": PROMPT}],
            temperature=0,
            max_tokens=100,
            response_format={"type": "json_object"},
            timeout=60,
        )
        content = response.choices[0].message.content
        usage = getattr(response, "usage", None)
        print(f"OK   {model:40s} | {content!r} | usage={usage}")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL {model:40s} | {type(exc).__name__}: {str(exc)[:240]}")

for model in GROQ_MODELS:
    try:
        response = completion(
            model=model,
            messages=[{"role": "user", "content": PROMPT}],
            temperature=0,
            max_tokens=200,
            timeout=60,
        )
        content = response.choices[0].message.content
        usage = getattr(response, "usage", None)
        print(f"OK   {model:40s} | {content!r} | usage={usage}")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL {model:40s} | {type(exc).__name__}: {str(exc)[:240]}")
