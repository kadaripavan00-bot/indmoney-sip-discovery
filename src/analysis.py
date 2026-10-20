"""Analysis layer: current signals, themes, prevalence, and opportunities.

The extractor produces grounded signal rows. This module turns them into the
tables used by the dashboard, evidence log, case write-up, deck, and PRD.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Iterable

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_session
from .models import Document, Opportunity, Signal, Theme, ThemeSignal
from .utils.text import is_relevant as is_keyword_relevant
from .utils.text import is_strictly_relevant

LAPSE_OUTCOMES = {"stopped", "paused", "reduced", "withdrew"}
CONTINUE_OUTCOMES = {"continues", "increased", "returned"}
OUTCOME_PRIORITY = [
    "stopped",
    "paused",
    "reduced",
    "withdrew",
    "returned",
    "increased",
    "continues",
    "unknown",
]
CONFIDENCE_SCORE = {"high": 1.0, "medium": 0.66, "low": 0.33, None: 0.5}


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item]
        except json.JSONDecodeError:
            pass
        return [value] if value else []
    return []


def _has(row: dict[str, Any], field: str, codes: Iterable[str]) -> bool:
    return bool(set(_as_list(row.get(field))) & set(codes))


def _quote_has(row: dict[str, Any], words: Iterable[str]) -> bool:
    quote = (row.get("quote") or "").lower()
    return any(word in quote for word in words)


def _outcome_rank(outcome: str | None) -> int:
    try:
        return OUTCOME_PRIORITY.index(outcome or "unknown")
    except ValueError:
        return len(OUTCOME_PRIORITY)


def _primary_outcome(outcomes: Iterable[str | None]) -> str:
    clean = [outcome for outcome in outcomes if outcome and outcome != "unknown"]
    if not clean:
        return "unknown"
    return sorted(clean, key=_outcome_rank)[0]


# ---------------------------------------------------------------------------
# Theme definitions
# ---------------------------------------------------------------------------

THEMES: list[dict[str, Any]] = [
    {
        "slug": "forced_pause",
        "name": "Paused by the system, not the investor",
        "definition": (
            "The SIP or fund was paused, suspended, or closed by an AMC, platform, "
            "or regulator. The investor did not choose to stop."
        ),
        "priority": 1,
        "solvability": 0.85,
        "effort": 0.35,
        "matcher": lambda row: _has(row, "triggers", {"product_suspension"}),
        "interventions": [
            "Proactive notice with the reason, expected duration, and what happens to the instalment.",
            "A clear alternative route or fund option, without recommending a specific fund.",
            "Auto-resume when the restriction lifts, with a confirmation and no penalty.",
        ],
    },
    {
        "slug": "cancellation_friction",
        "name": "Can't stop or fix it",
        "definition": (
            "The investor tried to cancel, pause, or repair a SIP and the app, mandate, "
            "or support flow did not work as expected."
        ),
        "priority": 2,
        "solvability": 0.9,
        "effort": 0.3,
        "matcher": lambda row: (
            (
                _has(row, "triggers", {"app_friction", "support_failure", "trust_shock"})
                and _quote_has(
                    row,
                    [
                        "cancel",
                        "stop",
                        "pause",
                        "withdraw",
                        "still active",
                        "not stopped",
                        "deducted",
                    ],
                )
            )
            or (
                _has(row, "behaviors", {"stopped_sip", "paused_sip"})
                and _quote_has(
                    row,
                    [
                        "cancel",
                        "still active",
                        "not stopped",
                        "money got deducted",
                        "amount got deducted",
                    ],
                )
            )
        ),
        "interventions": [
            "A pause option beside cancel, with a clear effective date and one-tap resume.",
            "A cancellation status tracker: requested, effective, refunded, closed.",
            "A support escalation path with a named owner and a response-time promise.",
        ],
    },
    {
        "slug": "mandate_friction",
        "name": "Failed debits and mandate breakage",
        "definition": (
            "A debit, UPI Autopay, NACH mandate, bank link, or bank-side block failed "
            "or required repair."
        ),
        "priority": 3,
        "solvability": 0.9,
        "effort": 0.4,
        "matcher": lambda row: _has(
            row, "triggers", {"payment_failure", "mandate_issue", "bank_issue"}
        ),
        "interventions": [
            "A pre-debit health check that flags a weak mandate, low balance, or bank issue.",
            "A three-day pre-debit alert with a one-tap repair or top-up path.",
            "Auto-retry with a plain-language reason and a fallback payment method.",
        ],
    },
    {
        "slug": "cashflow_shock",
        "name": "Cash-flow shocks and competing commitments",
        "definition": (
            "A salary delay, job change, income volatility, emergency expense, "
            "liquidity need, or life event made the SIP unaffordable."
        ),
        "priority": 4,
        "solvability": 0.8,
        "effort": 0.45,
        "matcher": lambda row: _has(
            row,
            "triggers",
            {
                "salary_delay",
                "job_change",
                "income_volatility",
                "emergency_expense",
                "liquidity_need",
                "life_event",
            },
        ),
        "interventions": [
            "A 1-3 month pause with automatic resume, instead of a permanent stop.",
            "A step-down amount that preserves the habit through a temporary squeeze.",
            "Salary-cycle alignment, an emergency-fund nudge, and a job-loss grace window.",
        ],
    },
    {
        "slug": "market_panic",
        "name": "Market noise and loss aversion",
        "definition": (
            "A market fall, negative returns, news, or advice from a creator or "
            "friend triggered anxiety, checking, or a stop."
        ),
        "priority": 5,
        "solvability": 0.75,
        "effort": 0.5,
        "matcher": lambda row: (
            _has(
                row,
                "triggers",
                {
                    "market_drawdown",
                    "negative_returns",
                    "news_event",
                    "finfluencer_advice",
                    "friend_family_advice",
                },
            )
            or _has(row, "emotions", {"anxiety", "fear", "panic"})
        ),
        "interventions": [
            "A drawdown explainer that shows goal progress, not only the return number.",
            "A 'what happens if you stop' calculator, framed as a trade-off, not a threat.",
            "An opt-in human call or community story for investors who are panicking.",
        ],
    },
    {
        "slug": "expectation_gap",
        "name": "Returns didn't match the promise",
        "definition": (
            "The investor expected linear, guaranteed, or market-beating returns and "
            "was disappointed by the first statement, a flat year, or a loss."
        ),
        "priority": 6,
        "solvability": 0.8,
        "effort": 0.35,
        "matcher": lambda row: (
            _has(
                row,
                "expectations",
                {"linear_growth", "guaranteed_returns", "beat_inflation", "build_wealth"},
            )
            and _has(
                row,
                "triggers",
                {"first_statement", "negative_returns", "market_drawdown"},
            )
        )
        or _has(row, "triggers", {"first_statement"})
        or (
            _has(row, "emotions", {"disappointment", "regret"})
            and _has(row, "triggers", {"negative_returns", "first_statement"})
        ),
        "interventions": [
            "Expectation-setting at onboarding: a range of outcomes, time horizon, and risk.",
            "A first-statement explainer that separates XIRR, absolute return, and market noise.",
            "A 'why your portfolio is down' checklist that ends with a clear next step.",
        ],
    },
    {
        "slug": "goal_competition",
        "name": "Which fund, which goal?",
        "definition": (
            "The investor is unsure whether the SIP still fits the goal, is comparing "
            "products, or is redirecting money to another goal."
        ),
        "priority": 7,
        "solvability": 0.75,
        "effort": 0.45,
        "matcher": lambda row: _has(
            row,
            "triggers",
            {"goal_doubt", "goal_achieved", "product_comparison", "tax"},
        )
        or _has(
            row,
            "expectations",
            {"tax_saving", "buy_house", "child_education", "retirement", "emergency_fund"},
        ),
        "interventions": [
            "One goal per SIP, with a goal-progress view and a plain-language fit check.",
            "House, wedding, education, and retirement planners that show the trade-off.",
            "A pause-and-resume path for short-term goals, instead of stopping the habit.",
        ],
    },
    {
        "slug": "product_confusion",
        "name": "I don't know what I bought",
        "definition": (
            "The investor is confused about direct vs regular, NAV, fund category, "
            "or which product is actually being debited."
        ),
        "priority": 8,
        "solvability": 0.8,
        "effort": 0.35,
        "matcher": lambda row: _has(row, "emotions", {"confusion"})
        and _quote_has(
            row,
            [
                "direct",
                "regular",
                "nav",
                "which fund",
                "which scheme",
                "category",
                "expense ratio",
            ],
        ),
        "interventions": [
            "A 'what am I invested in' statement with direct/regular and expense-ratio clarity.",
            "A plain-language fund comparison that does not recommend a specific fund.",
            "A human callback or glossary for first-time investors.",
        ],
    },
    {
        "slug": "habit_decay",
        "name": "Out of sight, out of mind",
        "definition": (
            "The investor forgot, avoided the app, or stopped paying attention; the "
            "SIP lapsed quietly rather than through a single dramatic event."
        ),
        "priority": 9,
        "solvability": 0.7,
        "effort": 0.3,
        "matcher": lambda row: _has(row, "triggers", {"notification_fatigue"})
        or _has(row, "behaviors", {"avoided_app"})
        or _quote_has(
            row,
            ["forgot", "didn't notice", "did not notice", "out of sight", "stopped checking"],
        ),
        "interventions": [
            "A monthly goal-progress recap, not a market-noise feed.",
            "A two-missed-debit re-engagement sequence with a one-tap repair.",
            "A low-effort 'SIP health score' that makes the next action obvious.",
        ],
    },
    {
        "slug": "positive_continuation",
        "name": "What keeps SIPs alive",
        "definition": (
            "The investor continued, increased, restarted, or returned to the SIP, "
            "often through a drawdown, a cash-flow squeeze, or a life event."
        ),
        "priority": 99,
        "solvability": 0.65,
        "effort": 0.3,
        "matcher": lambda row: _has(row, "outcome", set()) or (
            (row.get("outcome") in CONTINUE_OUTCOMES)
            or _has(row, "behaviors", {"increased_sip", "restarted_sip", "started_sip"})
        )
        and not (row.get("outcome") in LAPSE_OUTCOMES),
        "interventions": [
            "Celebrate goal progress and streak milestones without FOMO or urgency.",
            "A 'you stayed invested through...' recap that reinforces the identity, not the return.",
            "Community stories and human encouragement at the moments that usually trigger a stop.",
        ],
    },
    {
        "slug": "other_unclassified",
        "name": "Other / unclassified",
        "definition": "A grounded signal that does not fit the current theme map.",
        "priority": 100,
        "solvability": 0.4,
        "effort": 0.5,
        "matcher": lambda row: True,
        "interventions": ["Review manually before acting."],
    },
]


def _match_themes(row: dict[str, Any]) -> list[str]:
    matches: list[str] = []
    for theme in THEMES:
        if theme["slug"] == "other_unclassified":
            continue
        try:
            if theme["matcher"](row):
                matches.append(theme["slug"])
        except Exception:
            continue
    return matches


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_current_signals(session: Session) -> list[dict[str, Any]]:
    """Load signals from the latest extraction run for each document."""
    documents = session.scalars(select(Document).order_by(Document.id)).all()
    signals = session.scalars(select(Signal).order_by(Signal.id)).all()
    doc_by_id = {document.id: document for document in documents}

    latest_signal_run: dict[int, int] = {}
    for signal in signals:
        if signal.run_id is None:
            continue
        latest_signal_run[signal.document_id] = max(
            latest_signal_run.get(signal.document_id, 0), signal.run_id
        )

    rows: list[dict[str, Any]] = []
    for signal in signals:
        document = doc_by_id.get(signal.document_id)
        if document is None:
            continue
        if (signal.raw or {}).get("reground_status") == "dropped":
            continue
        expected_run = (document.meta or {}).get("extract_run_id")
        if expected_run is None:
            expected_run = latest_signal_run.get(document.id)
        if signal.run_id != expected_run:
            continue

        segment = signal.segment or {}
        row = {
            "signal_id": signal.id,
            "run_id": signal.run_id,
            "document_id": signal.document_id,
            "source": document.source.name if document.source else "unknown",
            "source_kind": document.source.kind if document.source else "unknown",
            "url": document.url,
            "published_at": document.published_at,
            "document_text": document.raw_text or "",
            "quote": signal.quote or "",
            "quote_start": signal.quote_start,
            "quote_end": signal.quote_end,
            "journey_stage": signal.journey_stage or "unknown",
            "outcome": signal.outcome or "unknown",
            "confidence": signal.confidence or "medium",
            "triggers": _as_list(signal.triggers),
            "behaviors": _as_list(signal.behaviors),
            "emotions": _as_list(signal.emotions),
            "expectations": _as_list(signal.expectations),
            "help_seeking": _as_list(signal.help_seeking),
            "income_stability": segment.get("income_stability", "unknown"),
            "age_band": segment.get("age_band", "unknown"),
            "source_of_money": segment.get("source_of_money", "unknown"),
            "influence": segment.get("influence", "unknown"),
            "ticket_size": segment.get("ticket_size", "unknown"),
            "goal_type": segment.get("goal_type", "unknown"),
            "grounding_warnings": (signal.raw or {}).get("grounding_warnings") or [],
            "derived": [
                warning
                for warning in ((signal.raw or {}).get("grounding_warnings") or [])
                if str(warning).startswith("derived:")
            ],
            "model": (signal.raw or {}).get("model"),
            "provider": (signal.raw or {}).get("provider"),
            "segment_quote": (signal.raw or {}).get("segment_quote"),
        }
        row["themes"] = _match_themes(row)
        row["primary_theme"] = _primary_theme(row["themes"])
        row["is_lapse"] = row["outcome"] in LAPSE_OUTCOMES
        row["is_continue"] = row["outcome"] in CONTINUE_OUTCOMES
        rows.append(row)
    return rows


def _primary_theme(themes: list[str]) -> str:
    if not themes:
        return "other_unclassified"
    priority = {theme["slug"]: theme["priority"] for theme in THEMES}
    return sorted(themes, key=lambda slug: priority.get(slug, 999))[0]


def load_document_frame(session: Session) -> pd.DataFrame:
    documents = session.scalars(select(Document).order_by(Document.id)).all()
    rows = []
    for document in documents:
        meta = document.meta or {}
        deep_coded = bool(meta.get("extract_run_id"))
        keyword_relevant = meta.get("keyword_relevant")
        if keyword_relevant is None:
            keyword_relevant = is_keyword_relevant(document.raw_text or "")
        strict_relevant = is_strictly_relevant(document.raw_text or "")
        rows.append(
            {
                "document_id": document.id,
                "source": document.source.name if document.source else "unknown",
                "source_kind": document.source.kind if document.source else "unknown",
                "url": document.url,
                "published_at": document.published_at,
                "language": document.language,
                "text_len": len(document.raw_text or ""),
                "document_text": (document.raw_text or "")[:2500],
                "deep_coded": deep_coded,
                "model_relevant": deep_coded and bool(document.is_relevant),
                "keyword_relevant": bool(keyword_relevant),
                "strict_relevant": bool(strict_relevant),
                "extract_run_id": meta.get("extract_run_id"),
                "extract_prompt_version": meta.get("extract_prompt_version"),
            }
        )
    return pd.DataFrame(rows)


def signals_frame(session: Session | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (signals, documents) frames from the current extraction."""
    if session is not None:
        rows = load_current_signals(session)
        documents = load_document_frame(session)
    else:
        with get_session() as own_session:
            rows = load_current_signals(own_session)
            documents = load_document_frame(own_session)
    signals = pd.DataFrame(rows)
    if signals.empty:
        signals = pd.DataFrame(
            columns=[
                "signal_id",
                "document_id",
                "source",
                "source_kind",
                "quote",
                "outcome",
                "journey_stage",
                "confidence",
                "triggers",
                "behaviors",
                "emotions",
                "expectations",
                "help_seeking",
                "income_stability",
                "age_band",
                "source_of_money",
                "influence",
                "ticket_size",
                "goal_type",
                "themes",
                "primary_theme",
                "is_lapse",
                "is_continue",
            ]
        )
    return signals, documents


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


def _explode_count(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty or column not in frame:
        return pd.Series(dtype=int)
    exploded = frame[column].explode()
    exploded = exploded[exploded.notna()]
    return exploded.value_counts()


def _share(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _confidence_mean(series: pd.Series) -> float:
    return float(series.map(lambda value: CONFIDENCE_SCORE.get(value, 0.5)).mean()) if len(series) else 0.0


def _top_values(series: pd.Series, limit: int = 3) -> list[tuple[str, int]]:
    counts = Counter(
        value
        for value in series
        if value and value != "unknown" and not (isinstance(value, float) and math.isnan(value))
    )
    return counts.most_common(limit)


def theme_summary(signals: pd.DataFrame, documents: pd.DataFrame) -> pd.DataFrame:
    deep_coded = int(documents["deep_coded"].sum()) if not documents.empty else 0
    signal_docs = signals["document_id"].nunique() if not signals.empty else 0
    total_signals = len(signals)
    known_outcome_signals = int(
        signals["outcome"].isin(LAPSE_OUTCOMES | CONTINUE_OUTCOMES).sum()
    ) if not signals.empty else 0
    baseline_lapse = _share(
        int(signals["outcome"].isin(LAPSE_OUTCOMES).sum()) if not signals.empty else 0,
        known_outcome_signals,
    )

    rows = []
    for theme in THEMES:
        slug = theme["slug"]
        subset = signals[signals["themes"].apply(lambda values: slug in values)] if not signals.empty else signals
        theme_signals = len(subset)
        theme_docs = subset["document_id"].nunique() if not subset.empty else 0
        lapse_signals = int(subset["outcome"].isin(LAPSE_OUTCOMES).sum()) if not subset.empty else 0
        continue_signals = int(subset["outcome"].isin(CONTINUE_OUTCOMES).sum()) if not subset.empty else 0
        known = lapse_signals + continue_signals
        outcome_known = known > 0
        # If no signal has a resolved outcome, do not report 0% as if it were
        # evidence of safety. Use the baseline as a neutral placeholder and flag
        # the theme so the deck can show "n/a (unresolved)".
        lapse_rate = _share(lapse_signals, known) if outcome_known else baseline_lapse
        lift = (lapse_rate / baseline_lapse) if baseline_lapse and outcome_known else 1.0
        confidence = _confidence_mean(subset["confidence"]) if not subset.empty else 0.0
        evidence_strength = min(1.0, theme_docs / 30.0) * confidence
        sources = _top_values(subset["source"]) if not subset.empty else []
        stages = _top_values(subset["journey_stage"]) if not subset.empty else []
        kind = (
            "protective"
            if slug == "positive_continuation"
            else ("other" if slug == "other_unclassified" else "problem")
        )
        rows.append(
            {
                "slug": slug,
                "name": theme["name"],
                "kind": kind,
                "definition": theme["definition"],
                "signals": theme_signals,
                "documents": theme_docs,
                "share_signals": _share(theme_signals, total_signals),
                "share_signal_docs": _share(theme_docs, signal_docs),
                "share_deep_coded_docs": _share(theme_docs, deep_coded),
                "lapse_signals": lapse_signals,
                "continue_signals": continue_signals,
                "known_outcome_signals": known,
                "outcome_known": outcome_known,
                "lapse_rate": lapse_rate,
                "baseline_lapse_rate": baseline_lapse,
                "lift": lift,
                "avg_confidence": confidence,
                "evidence_strength": evidence_strength,
                "solvability": theme["solvability"],
                "effort": theme["effort"],
                "priority": theme["priority"],
                "sources": sources,
                "stages": stages,
                "interventions": theme["interventions"],
            }
        )
    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary

    max_reach = max(summary["share_signal_docs"].max(), 1e-9)
    max_lift = max(summary["lift"].max(), 1.0)
    summary["reach_norm"] = summary["share_signal_docs"] / max_reach
    summary["severity_norm"] = (summary["lift"].clip(lower=0, upper=max_lift) - 1.0).clip(lower=0) / max(
        max_lift - 1.0, 1e-9
    )
    # Unresolved-outcome themes get a modest friction prior rather than a zero.
    # They are still flagged so the deck can show "n/a (unresolved)".
    summary["severity_for_score"] = summary["severity_norm"].where(
        summary["outcome_known"], 0.35
    )
    summary["score_note"] = summary["outcome_known"].map(
        {True: "empirical lapse lift", False: "unresolved outcome; friction prior"}
    )
    summary["opportunity_score"] = (
        100.0
        * (
            0.35 * summary["reach_norm"]
            + 0.30 * summary["severity_for_score"]
            + 0.20 * summary["evidence_strength"]
            + 0.15 * summary["solvability"]
        )
        * (1.0 - 0.25 * summary["effort"])
    ).round(1)
    summary = summary.sort_values(
        ["opportunity_score", "documents"], ascending=[False, False]
    ).reset_index(drop=True)
    summary["rank"] = summary.index + 1
    summary["lapse_display"] = summary.apply(
        lambda row: f"{row['lapse_rate']:.0%}" if row["outcome_known"] else "n/a",
        axis=1,
    )
    summary["lift_display"] = summary.apply(
        lambda row: (
            "n/a (protective)"
            if row["kind"] == "protective"
            else (f"{row['lift']:.2f}x" if row["outcome_known"] else "n/a")
        ),
        axis=1,
    )
    return summary


def code_frequency(signals: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for field in ("triggers", "behaviors", "emotions", "expectations", "help_seeking", "outcome", "journey_stage"):
        if field in ("outcome", "journey_stage"):
            counts = signals[field].value_counts() if field in signals else pd.Series(dtype=int)
        else:
            counts = _explode_count(signals, field)
        for code, count in counts.items():
            if code in ("unknown", "", None):
                continue
            rows.append({"field": field, "code": code, "count": int(count)})
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result = result.sort_values(["field", "count"], ascending=[True, False]).reset_index(drop=True)
    return result


def segment_summary(signals: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for field in (
        "age_band",
        "income_stability",
        "source_of_money",
        "influence",
        "ticket_size",
        "goal_type",
    ):
        if field not in signals:
            continue
        for value, count in signals[field].value_counts().items():
            if value in ("unknown", "", None):
                continue
            subset = signals[signals[field] == value]
            known = subset["outcome"].isin(LAPSE_OUTCOMES | CONTINUE_OUTCOMES)
            lapse = subset["outcome"].isin(LAPSE_OUTCOMES)
            rate = _share(int(lapse.sum()), int(known.sum()))
            rows.append(
                {
                    "segment_field": field,
                    "segment_value": value,
                    "signals": int(count),
                    "share_signals": _share(count, len(signals)),
                    "lapse_rate": rate,
                    "lapse_display": f"{rate:.0%}" if known.sum() else "n/a",
                    "known_outcomes": int(known.sum()),
                }
            )
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.sort_values(["segment_field", "signals"], ascending=[True, False]).reset_index(drop=True)


def source_summary(signals: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return pd.DataFrame()
    rows = []
    for source, subset in signals.groupby("source"):
        known = subset["outcome"].isin(LAPSE_OUTCOMES | CONTINUE_OUTCOMES)
        lapse = subset["outcome"].isin(LAPSE_OUTCOMES)
        rate = _share(int(lapse.sum()), int(known.sum()))
        rows.append(
            {
                "source": source,
                "signals": len(subset),
                "documents": subset["document_id"].nunique(),
                "lapse_rate": rate,
                "lapse_display": f"{rate:.0%}" if known.sum() else "n/a",
                "known_outcomes": int(known.sum()),
                "top_theme": subset["primary_theme"].value_counts().idxmax()
                if not subset.empty
                else "unknown",
            }
        )
    return pd.DataFrame(rows).sort_values("signals", ascending=False).reset_index(drop=True)


def stage_summary(signals: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return pd.DataFrame()
    rows = []
    for stage, subset in signals.groupby("journey_stage"):
        if stage == "unknown":
            continue
        known = subset["outcome"].isin(LAPSE_OUTCOMES | CONTINUE_OUTCOMES)
        lapse = subset["outcome"].isin(LAPSE_OUTCOMES)
        rate = _share(int(lapse.sum()), int(known.sum()))
        rows.append(
            {
                "journey_stage": stage,
                "signals": len(subset),
                "documents": subset["document_id"].nunique(),
                "lapse_rate": rate,
                "lapse_display": f"{rate:.0%}" if known.sum() else "n/a",
                "known_outcomes": int(known.sum()),
                "top_theme": subset["primary_theme"].value_counts().idxmax()
                if not subset.empty
                else "unknown",
            }
        )
    return pd.DataFrame(rows).sort_values("signals", ascending=False).reset_index(drop=True)


def example_quotes(signals: pd.DataFrame, slug: str, limit: int = 3) -> list[dict[str, Any]]:
    subset = signals[signals["themes"].apply(lambda values: slug in values)] if not signals.empty else signals
    if subset.empty:
        return []
    subset = subset.copy()
    subset["_confidence"] = subset["confidence"].map(lambda value: CONFIDENCE_SCORE.get(value, 0.5))
    subset = subset.sort_values(["_confidence", "signal_id"], ascending=[False, True])
    examples = []
    for _, row in subset.head(limit).iterrows():
        examples.append(
            {
                "signal_id": int(row["signal_id"]),
                "document_id": int(row["document_id"]),
                "source": row["source"],
                "url": row.get("url"),
                "quote": row["quote"],
                "outcome": row["outcome"],
                "journey_stage": row["journey_stage"],
                "themes": row["themes"],
                "confidence": row["confidence"],
            }
        )
    return examples


def document_outcomes(signals: pd.DataFrame, documents: pd.DataFrame) -> pd.DataFrame:
    if signals.empty or documents.empty:
        return documents.assign(document_outcome="unknown")
    outcomes = (
        signals.groupby("document_id")["outcome"]
        .apply(lambda values: _primary_outcome(values.tolist()))
        .rename("document_outcome")
    )
    return documents.merge(outcomes, left_on="document_id", right_index=True, how="left").fillna(
        {"document_outcome": "unknown"}
    )


# ---------------------------------------------------------------------------
# Persistence and exports
# ---------------------------------------------------------------------------


def save_theme_outputs(
    signals: pd.DataFrame,
    documents: pd.DataFrame,
    summary: pd.DataFrame,
    session: Session,
) -> None:
    """Persist themes, theme-signal links, and opportunities."""
    theme_ids: dict[str, int] = {}
    for theme in THEMES:
        existing = session.scalar(select(Theme).where(Theme.slug == theme["slug"]))
        if existing is None:
            existing = Theme(
                name=theme["name"],
                slug=theme["slug"],
                definition=theme["definition"],
            )
            session.add(existing)
            session.flush()
        theme_ids[theme["slug"]] = existing.id

    existing_links = {
        (link.theme_id, link.signal_id)
        for link in session.scalars(select(ThemeSignal)).all()
    }
    for _, row in signals.iterrows():
        for slug in row["themes"]:
            theme_id = theme_ids.get(slug)
            if theme_id is None:
                continue
            key = (theme_id, int(row["signal_id"]))
            if key in existing_links:
                continue
            session.add(
                ThemeSignal(
                    theme_id=theme_id,
                    signal_id=int(row["signal_id"]),
                    confidence=CONFIDENCE_SCORE.get(row["confidence"], 0.5),
                )
            )
            existing_links.add(key)

    for _, row in summary.iterrows():
        existing = session.scalar(select(Opportunity).where(Opportunity.name == row["name"]))
        if existing is None:
            existing = Opportunity(name=row["name"])
            session.add(existing)
        existing.description = row["definition"]
        existing.theme_ids = [theme_ids.get(row["slug"])] if theme_ids.get(row["slug"]) else None
        existing.reach = float(row["share_signal_docs"])
        existing.severity = float(row["lapse_rate"])
        existing.evidence_strength = float(row["evidence_strength"])
        existing.expected_lift = float(row["opportunity_score"] / 100.0)
        existing.effort = float(row["effort"])
        existing.score = float(row["opportunity_score"])
        existing.metric_bridge = {
            "signals": int(row["signals"]),
            "documents": int(row["documents"]),
            "lift": float(row["lift"]),
            "baseline_lapse_rate": float(row["baseline_lapse_rate"]),
            "interventions": row["interventions"],
        }
        existing.guardrail_pass = True
    session.commit()


def export_analysis(
    output_dir: str | "Path",
    signals: pd.DataFrame,
    documents: pd.DataFrame,
    summary: pd.DataFrame,
    codes: pd.DataFrame,
    segments: pd.DataFrame,
    sources: pd.DataFrame,
    stages: pd.DataFrame,
) -> None:
    from pathlib import Path

    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    signals.to_csv(path / "signals.csv", index=False, encoding="utf-8-sig")
    documents.to_csv(path / "documents.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(path / "themes.csv", index=False, encoding="utf-8-sig")
    codes.to_csv(path / "code_frequency.csv", index=False, encoding="utf-8-sig")
    segments.to_csv(path / "segments.csv", index=False, encoding="utf-8-sig")
    sources.to_csv(path / "sources.csv", index=False, encoding="utf-8-sig")
    stages.to_csv(path / "stages.csv", index=False, encoding="utf-8-sig")

    examples = {
        row["slug"]: example_quotes(signals, row["slug"], limit=5)
        for _, row in summary.iterrows()
    }
    (path / "theme_examples.json").write_text(
        json.dumps(examples, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "totals": {
            "documents": int(len(documents)),
            "deep_coded_documents": int(documents["deep_coded"].sum())
            if "deep_coded" in documents
            else 0,
            "relevant_documents": int(documents["model_relevant"].sum())
            if "model_relevant" in documents
            else 0,
            "signals": int(len(signals)),
            "documents_with_signals": int(signals["document_id"].nunique())
            if not signals.empty
            else 0,
        },
        "themes": summary.to_dict(orient="records"),
        "sources": sources.to_dict(orient="records"),
        "stages": stages.to_dict(orient="records"),
    }
    (path / "analysis_summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
