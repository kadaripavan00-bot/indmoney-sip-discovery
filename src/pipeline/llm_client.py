"""Provider-agnostic LLM client with fallback, pacing, and JSON parsing."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import litellm
from litellm import completion

from ..config import get_secret, settings

litellm.drop_params = True
litellm.suppress_debug_info = True


def parse_json_response(content: str) -> dict[str, Any]:
    """Parse a JSON object from a model response, tolerating code fences."""
    if not content or not content.strip():
        raise ValueError("empty model response")
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if isinstance(data, list):
        return {"results": data}
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object, got {type(data).__name__}")
    return data


@dataclass
class LLMResult:
    data: dict[str, Any]
    provider: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    attempts: int = 1
    raw_content: str = ""


class LLMClient:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or settings().get("models", {})
        self.providers = self.config.get("providers", {})
        self.routing = self.config.get("routing", {})
        self.extraction = self.config.get("extraction", {})
        self.min_intervals = self.extraction.get("min_interval_seconds", {})
        self._last_call: dict[str, float] = {}
        self.usage_totals: dict[str, dict[str, dict[str, int]]] = {}
        self.errors: list[dict[str, Any]] = []

    def _candidates(self, role: str) -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []
        for provider in self.routing.get(role, []):
            provider_cfg = self.providers.get(provider, {})
            model = provider_cfg.get("models", {}).get(role)
            if not model:
                continue
            key_env = provider_cfg.get("api_key_env")
            if key_env and not get_secret(key_env):
                continue
            candidates.append((provider, model))
        return candidates

    def _wait(self, provider: str) -> None:
        interval = float(self.min_intervals.get(provider, 0) or 0)
        if interval <= 0:
            return
        elapsed = time.monotonic() - self._last_call.get(provider, 0.0)
        if elapsed < interval:
            time.sleep(interval - elapsed)

    def _mark_call(self, provider: str) -> None:
        self._last_call[provider] = time.monotonic()

    def _track_usage(self, provider: str, model: str, usage: dict[str, Any]) -> None:
        bucket = self.usage_totals.setdefault(provider, {}).setdefault(
            model,
            {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )
        bucket["calls"] += 1
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, (int, float)):
                bucket[key] += int(value)

    def _record_error(self, provider: str, model: str, exc: Exception, attempt: int) -> None:
        self.errors.append(
            {
                "provider": provider,
                "model": model,
                "attempt": attempt,
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
            }
        )

    def complete_json(
        self,
        messages: list[dict[str, str]],
        role: str = "bulk",
        max_tokens: int | None = None,
        retries: int = 2,
        timeout: int = 120,
    ) -> LLMResult:
        """Call the first available provider that returns valid JSON."""
        candidates = self._candidates(role)
        if not candidates:
            raise RuntimeError(f"No provider configured with a key for role={role}")

        last_error: Exception | None = None
        for provider, model in candidates:
            for attempt in range(retries + 1):
                self._wait(provider)
                try:
                    response = completion(
                        model=model,
                        messages=messages,
                        temperature=float(self.extraction.get("temperature", 0)),
                        max_tokens=max_tokens or int(self.extraction.get("max_tokens", 2400)),
                        timeout=timeout,
                    )
                    self._mark_call(provider)
                    content = response.choices[0].message.content or ""
                    usage_obj = getattr(response, "usage", None)
                    usage = usage_obj.model_dump() if hasattr(usage_obj, "model_dump") else {}
                    data = parse_json_response(content)
                    self._track_usage(provider, model, usage)
                    return LLMResult(
                        data=data,
                        provider=provider,
                        model=model,
                        usage=usage,
                        attempts=attempt + 1,
                        raw_content=content,
                    )
                except Exception as exc:  # noqa: BLE001
                    self._mark_call(provider)
                    self._record_error(provider, model, exc, attempt + 1)
                    last_error = exc
                    # Back off more for rate limits, less for parse errors.
                    message = str(exc).lower()
                    if "rate" in message or "429" in message or "quota" in message:
                        time.sleep(min(20 * (attempt + 1), 60))
                    elif "timeout" in message or "timed out" in message:
                        time.sleep(min(5 * (attempt + 1), 20))
                    else:
                        time.sleep(min(2**attempt, 8))

        raise RuntimeError(f"All LLM providers failed for role={role}: {last_error}")
