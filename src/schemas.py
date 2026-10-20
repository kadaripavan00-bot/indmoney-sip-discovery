"""Pydantic schemas for LLM structured outputs."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SegmentCues(BaseModel):
    model_config = ConfigDict(extra="ignore")

    income_stability: str = "unknown"
    age_band: str = "unknown"
    source_of_money: str = "unknown"
    influence: str = "unknown"
    ticket_size: str = "unknown"
    goal_type: str = "unknown"


class SignalExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    journey_stage: str = "unknown"
    triggers: list[str] = Field(default_factory=list)
    behaviors: list[str] = Field(default_factory=list)
    emotions: list[str] = Field(default_factory=list)
    expectations: list[str] = Field(default_factory=list)
    help_seeking: list[str] = Field(default_factory=list)
    outcome: str = "unknown"
    segment_cues: SegmentCues = Field(default_factory=SegmentCues)
    segment_quote: str | None = None
    quote: str = ""
    confidence: str = "medium"
    notes: str | None = None


class BatchSignalExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    signals: list[SignalExtraction] = Field(default_factory=list)


class DocumentExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_id: int
    relevant: bool = False
    signals: list[SignalExtraction] = Field(default_factory=list)

    @field_validator("doc_id", mode="before")
    @classmethod
    def parse_doc_id(cls, value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("doc_id must be an integer")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            match = re.search(r"\d+", value)
            if match:
                return int(match.group())
        raise ValueError(f"invalid doc_id: {value!r}")


class BatchDocumentExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    results: list[DocumentExtraction] = Field(default_factory=list)


class ThemeLabel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    definition: str
    signal_ids: list[int] = Field(default_factory=list)
    confidence: str = "medium"


class ThemeBatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    themes: list[ThemeLabel] = Field(default_factory=list)


def signal_to_dict(signal: SignalExtraction) -> dict[str, Any]:
    return signal.model_dump()
