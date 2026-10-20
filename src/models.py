"""SQLAlchemy models for the discovery engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(50))
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    documents: Mapped[list["Document"]] = relationship(back_populates="source")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    author_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    dedupe_group: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_relevant: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    source: Mapped[Source] = relationship(back_populates="documents")
    signals: Mapped[list["Signal"]] = relationship(back_populates="document")

    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_document_source_external"),
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_type: Mapped[str] = mapped_column(String(50), index=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    signals: Mapped[list["Signal"]] = relationship(back_populates="run")


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True, index=True)
    journey_stage: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    triggers: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    behaviors: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    emotions: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    expectations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    help_seeking: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    segment: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    quote_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    document: Mapped[Document] = relationship(back_populates="signals")
    run: Mapped[Run | None] = relationship(back_populates="signals")


class Theme(Base):
    __tablename__ = "themes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("themes.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ThemeSignal(Base):
    __tablename__ = "theme_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    theme_id: Mapped[int] = mapped_column(ForeignKey("themes.id"), index=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id"), index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (UniqueConstraint("theme_id", "signal_id", name="uq_theme_signal"),)


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    theme_ids: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    reach: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_lift: Mapped[float | None] = mapped_column(Float, nullable=True)
    effort: Mapped[float | None] = mapped_column(Float, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    metric_bridge: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    guardrail_pass: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    insight_id: Mapped[str] = mapped_column(String(50), index=True)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id"), nullable=True)
    quote: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class GoldSet(Base):
    __tablename__ = "gold_set"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    human_labels: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    coder_labels: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    agreement: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    metric: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
