"""List available Gemini and Groq models without printing API keys."""

from __future__ import annotations

import os

import requests
from dotenv import load_dotenv

load_dotenv()


def list_gemini() -> None:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("Gemini: key missing")
        return
    response = requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        headers={"x-goog-api-key": key},
        timeout=30,
    )
    response.raise_for_status()
    print("Gemini models:")
    for model in response.json().get("models", []):
        methods = model.get("supportedGenerationMethods", [])
        if "generateContent" in methods or "embedContent" in methods:
            print(f"  {model.get('name')} | {methods}")


def list_groq() -> None:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        print("Groq: key missing")
        return
    response = requests.get(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {key}"},
        timeout=30,
    )
    response.raise_for_status()
    print("\nGroq models:")
    for model in response.json().get("data", []):
        print(f"  {model.get('id')}")


if __name__ == "__main__":
    list_gemini()
    list_groq()
