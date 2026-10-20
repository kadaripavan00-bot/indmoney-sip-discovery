"""Codebook access, synonym normalization, and validation."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from .config import settings

SYNONYMS: dict[str, dict[str, str]] = {
    "triggers": {
        "app_issue": "app_friction",
        "app_bug": "app_friction",
        "app_problem": "app_friction",
        "ui_issue": "app_friction",
        "ux_issue": "app_friction",
        "notification": "notification_fatigue",
        "notifications": "notification_fatigue",
        "spam": "notification_fatigue",
        "too_many_notifications": "notification_fatigue",
        "market_crash": "market_drawdown",
        "market_fall": "market_drawdown",
        "market_correction": "market_drawdown",
        "crash": "market_drawdown",
        "loss": "negative_returns",
        "losses": "negative_returns",
        "negative_return": "negative_returns",
        "low_returns": "negative_returns",
        "poor_returns": "negative_returns",
        "flat_returns": "negative_returns",
        "payment_failed": "payment_failure",
        "debit_failed": "payment_failure",
        "autopay_failed": "payment_failure",
        "payment_declined": "payment_failure",
        "mandate_failed": "mandate_issue",
        "mandate_problem": "mandate_issue",
        "mandate_rejected": "mandate_issue",
        "bank_problem": "bank_issue",
        "bank_failure": "bank_issue",
        "salary_delayed": "salary_delay",
        "late_salary": "salary_delay",
        "job_loss": "job_change",
        "lost_job": "job_change",
        "job_switch": "job_change",
        "income_loss": "income_volatility",
        "irregular_income": "income_volatility",
        "freelance_income": "income_volatility",
        "medical_expense": "emergency_expense",
        "family_expense": "emergency_expense",
        "emergency": "emergency_expense",
        "need_cash": "liquidity_need",
        "cash_need": "liquidity_need",
        "liquidity": "liquidity_need",
        "doubt": "goal_doubt",
        "goal_confusion": "goal_doubt",
        "goal_reached": "goal_achieved",
        "marriage": "life_event",
        "relocation": "life_event",
        "child": "life_event",
        "education": "life_event",
        "fraud": "trust_shock",
        "scam": "trust_shock",
        "hidden_charge": "trust_shock",
        "mis_selling": "trust_shock",
        "news": "news_event",
        "market_news": "news_event",
        "youtube_advice": "finfluencer_advice",
        "influencer": "finfluencer_advice",
        "finfluencer": "finfluencer_advice",
        "family_advice": "friend_family_advice",
        "friend_advice": "friend_family_advice",
        "comparison": "product_comparison",
        "compared": "product_comparison",
        "support_issue": "support_failure",
        "customer_support": "support_failure",
        "poor_support": "support_failure",
        "tax_saving": "tax",
        "bonus": "bonus_or_raise",
        "raise": "bonus_or_raise",
        "increment": "bonus_or_raise",
    },
    "behaviors": {
        "stop_sip": "stopped_sip",
        "cancel_sip": "stopped_sip",
        "cancelled_sip": "stopped_sip",
        "stopped": "stopped_sip",
        "pause_sip": "paused_sip",
        "paused": "paused_sip",
        "pause": "paused_sip",
        "resume_sip": "restarted_sip",
        "restart_sip": "restarted_sip",
        "resumed": "restarted_sip",
        "restarted": "restarted_sip",
        "reduce_sip": "decreased_sip",
        "reduced": "decreased_sip",
        "decrease_sip": "decreased_sip",
        "increase_sip": "increased_sip",
        "increased": "increased_sip",
        "top_up": "increased_sip",
        "start_sip": "started_sip",
        "started": "started_sip",
        "begin_sip": "started_sip",
        "switch": "switched_product",
        "switched": "switched_product",
        "move_to_another_app": "switched_product",
        "withdraw": "withdrew",
        "redeem": "withdrew",
        "redeemed": "withdrew",
        "check_daily": "checked_frequently",
        "check_often": "checked_frequently",
        "frequent_checking": "checked_frequently",
        "check_monthly": "checked_rarely",
        "rarely_check": "checked_rarely",
        "avoid_app": "avoided_app",
        "stopped_opening_app": "avoided_app",
        "ask_help": "sought_help",
        "asked_for_help": "sought_help",
        "complain": "complained",
        "negative_review": "complained",
        "recommend": "recommended",
        "no_action": "did_nothing",
    },
    "emotions": {
        "annoyance": "frustration",
        "annoyed": "frustration",
        "irritation": "frustration",
        "irritated": "frustration",
        "worried": "anxiety",
        "worry": "anxiety",
        "nervous": "anxiety",
        "stress": "anxiety",
        "stressed": "anxiety",
        "scared": "fear",
        "afraid": "fear",
        "ashamed": "shame",
        "embarrassed": "embarrassment",
        "confused": "confusion",
        "frustrated": "frustration",
        "angry": "anger",
        "mad": "anger",
        "distrustful": "distrust",
        "suspicious": "distrust",
        "disappointed": "disappointment",
        "indifferent": "apathy",
        "uninterested": "apathy",
        "regretful": "regret",
        "relieved": "relief",
        "proud": "pride",
        "confident": "confidence",
        "okay": "neutral",
        "fine": "neutral",
    },
    "expectations": {
        "guaranteed": "guaranteed_returns",
        "assured_returns": "guaranteed_returns",
        "steady_growth": "linear_growth",
        "linear": "linear_growth",
        "line_goes_up": "linear_growth",
        "safe": "fd_like_safety",
        "safety": "fd_like_safety",
        "fd_safety": "fd_like_safety",
        "quick": "quick_returns",
        "fast_returns": "quick_returns",
        "inflation": "beat_inflation",
        "wealth": "build_wealth",
        "long_term_wealth": "build_wealth",
        "goal": "goal_progress",
        "goal_tracking": "goal_progress",
        "learn": "learn_investing",
        "learning": "learn_investing",
        "tax": "tax_saving",
        "discipline": "discipline",
        "forced_saving": "discipline",
    },
    "help_seeking": {
        "friend": "friend_family",
        "friends": "friend_family",
        "family": "friend_family",
        "colleague": "friend_family",
        "yt": "youtube",
        "google": "google_search",
        "search": "google_search",
        "support": "customer_support",
        "customer_care": "customer_support",
        "ca": "ca_advisor",
        "advisor": "ca_advisor",
        "financial_advisor": "ca_advisor",
        "help_center": "app_help",
        "instagram": "social_media",
        "twitter": "social_media",
        "social": "social_media",
        "no_one": "none",
    },
    "outcomes": {
        "continue": "continues",
        "continuing": "continues",
        "still_investing": "continues",
        "pause": "paused",
        "stop": "stopped",
        "cancelled": "stopped",
        "return": "returned",
        "restarted": "returned",
        "reduce": "reduced",
        "increase": "increased",
    },
    "segment:income_stability": {
        "stable": "salaried",
        "unstable": "variable",
        "freelancer": "gig",
        "self_employed": "business",
    },
    "segment:source_of_money": {
        "salary": "own_income",
        "parents": "family",
        "parent": "family",
    },
    "segment:influence": {
        "friend": "friend_family",
        "family": "friend_family",
        "advisor": "ca_advisor",
        "instagram": "social_media",
    },
}


@lru_cache(maxsize=1)
def codebook() -> dict[str, Any]:
    return settings().get("codebook", {})


def allowed_values(field: str) -> set[str]:
    values = codebook().get(field, [])
    return set(values) if isinstance(values, list) else set()


def _normalize_value(value: Any, preserve_hyphen: bool = False) -> str:
    normalized = str(value).strip().lower().replace(" ", "_")
    if not preserve_hyphen:
        normalized = normalized.replace("-", "_")
    return normalized


def _normalize_list(field: str, values: Any) -> tuple[list[str], list[Any]]:
    if values is None:
        return [], []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return [], [values]

    valid = allowed_values(field)
    synonyms = SYNONYMS.get(field, {})
    cleaned: list[str] = []
    dropped: list[Any] = []
    for value in values:
        normalized = _normalize_value(value)
        if normalized in valid:
            if normalized not in cleaned:
                cleaned.append(normalized)
        elif normalized in synonyms:
            mapped = synonyms[normalized]
            if mapped not in cleaned:
                cleaned.append(mapped)
        else:
            dropped.append(value)
    return cleaned, dropped


def normalize_signal_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Coerce labels to the codebook, dropping only invalid labels.

    Returns the cleaned payload and a list of human-readable warnings. A bad
    label never discards the whole signal; it is either mapped or dropped.
    """
    cb = codebook()
    warnings: list[str] = []
    normalized = dict(payload)

    stage = _normalize_value(normalized.get("journey_stage", "unknown"))
    if stage not in cb.get("journey_stages", []):
        warnings.append(f"journey_stage {stage!r} -> unknown")
        stage = "unknown"
    normalized["journey_stage"] = stage

    for field in ("triggers", "behaviors", "emotions", "expectations", "help_seeking"):
        cleaned, dropped = _normalize_list(field, normalized.get(field))
        if dropped:
            warnings.append(f"{field} dropped: {dropped}")
        normalized[field] = cleaned

    outcome = _normalize_value(normalized.get("outcome", "unknown"))
    if outcome not in cb.get("outcomes", []):
        mapped = SYNONYMS.get("outcomes", {}).get(outcome)
        if mapped:
            warnings.append(f"outcome {outcome!r} -> {mapped}")
            outcome = mapped
        else:
            warnings.append(f"outcome {outcome!r} -> unknown")
            outcome = "unknown"
    normalized["outcome"] = outcome

    segment = normalized.get("segment_cues") or {}
    if not isinstance(segment, dict):
        segment = {}
    cleaned_segment: dict[str, str] = {}
    for key, value in segment.items():
        valid = set(cb.get("segments", {}).get(key, []))
        if not valid:
            continue
        normalized_value = _normalize_value(value, preserve_hyphen=(key == "age_band"))
        if normalized_value in valid:
            cleaned_segment[key] = normalized_value
        else:
            mapped = SYNONYMS.get(f"segment:{key}", {}).get(normalized_value)
            if mapped:
                cleaned_segment[key] = mapped
            else:
                warnings.append(f"segment {key} {normalized_value!r} -> unknown")
                cleaned_segment[key] = "unknown"
    normalized["segment_cues"] = cleaned_segment

    confidence = _normalize_value(normalized.get("confidence", "medium"))
    if confidence not in cb.get("confidence", []):
        warnings.append(f"confidence {confidence!r} -> medium")
        confidence = "medium"
    normalized["confidence"] = confidence

    return normalized, warnings


def validate_signal_payload(payload: dict[str, Any]) -> list[str]:
    """Return a list of validation errors for a signal payload."""
    errors: list[str] = []
    cb = codebook()

    stage = payload.get("journey_stage", "unknown")
    if stage not in cb.get("journey_stages", []):
        errors.append(f"invalid journey_stage: {stage}")

    for field in ("triggers", "behaviors", "emotions", "expectations", "help_seeking"):
        values = payload.get(field) or []
        if not isinstance(values, list):
            errors.append(f"{field} must be a list")
            continue
        valid = set(cb.get(field, []))
        for value in values:
            if value not in valid:
                errors.append(f"invalid {field}: {value}")

    outcome = payload.get("outcome", "unknown")
    if outcome not in cb.get("outcomes", []):
        errors.append(f"invalid outcome: {outcome}")

    segment = payload.get("segment_cues") or payload.get("segment") or {}
    if isinstance(segment, dict):
        segments = cb.get("segments", {})
        for key, value in segment.items():
            valid = set(segments.get(key, []))
            if valid and value not in valid:
                errors.append(f"invalid segment {key}: {value}")

    confidence = payload.get("confidence", "medium")
    if confidence not in cb.get("confidence", []):
        errors.append(f"invalid confidence: {confidence}")

    return errors
