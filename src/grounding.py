"""Deterministic grounding: keep only codes supported by the quoted span.

The LLM reads the whole document, but the evidence is the quote. This module
checks that each non-unknown code has lexical support inside the quote. It
drops unsupported codes instead of rejecting the whole signal, then reports
whether the remaining signal is meaningful.
"""

from __future__ import annotations

import re
from typing import Any

SIP_CONTEXT = [
    "sip",
    "mutual fund",
    "mutual funds",
    "mf",
    "nav",
    "folio",
    "mandate",
    "auto debit",
    "autopay",
    "instalment",
    "installment",
    "systematic investment",
]

SIP_SPECIFIC_BEHAVIORS = {
    "started_sip",
    "increased_sip",
    "decreased_sip",
    "paused_sip",
    "stopped_sip",
    "restarted_sip",
    "switched_product",
    "withdrew",
}

# These behaviours must be anchored to the word "sip" in the same sentence.
# A mutual-fund allocation change is not necessarily a SIP change.
SIP_ONLY_BEHAVIORS = {
    "started_sip",
    "increased_sip",
    "decreased_sip",
    "paused_sip",
    "stopped_sip",
    "restarted_sip",
}

ATTEMPT_PHRASES = [
    "requested to",
    "trying to",
    "tried to",
    "planning to",
    "want to",
    "wants to",
    "thinking of",
    "considering",
    "asked to",
    "attempted to",
    "about to",
    "plan to",
    "wish to",
    "if i",
]

# Third-party actions are the most common false positive in public posts.
# The author can mention a friend without the friend's SIP being the author's.
THIRD_PERSON_PATTERNS = [
    r"\b(?:i|we)\s+(?:helped|help|advised|asked|told|convinced|suggested\s+to)\s+(?:a|an|my|our)?\s*(?:friend|colleague|brother|sister|father|mother|wife|husband|son|daughter|client|cousin|relative)\b",
    r"\b(?:my|our)\s+(?:friend|colleague|brother|sister|father|mother|wife|husband|son|daughter|client|cousin|relative)\s+(?:stopped|paused|cancelled|canceled|started|invested|withdrew|redeemed|increased|decreased)\b",
    r"\b(?:he|she|they)\s+(?:stopped|paused|cancelled|canceled|started|invested|withdrew|redeemed|increased|decreased)\b",
    r"\b(?:his|her|their)\s+sip\b",
]

NEGATION_PATTERNS = {
    "started_sip": r"\b(?:never|not|didn't|did not|haven't|have not)\s+(?:start|started|begin|began)\b",
    "stopped_sip": r"\b(?:never|not|didn't|did not|haven't|have not|wasn't|was not|isn't|is not)\s+(?:stop|stopped|cancel|cancelled|canceled|discontinue|discontinued|close|closed)\b",
    "paused_sip": r"\b(?:never|not|didn't|did not|haven't|have not)\s+(?:pause|paused|hold|held|skip|skipped)\b",
    "decreased_sip": r"\b(?:never|not|didn't|did not|haven't|have not)\s+(?:decrease|decreased|reduce|reduced|lower|lowered|cut)\b",
    "withdrew": r"\b(?:never|not|didn't|did not|haven't|have not)\s+(?:withdraw|withdrew|redeem|redeemed|sell|sold)\b",
    "restarted_sip": r"\b(?:never|not|didn't|did not|haven't|have not)\s+(?:restart|restarted|resume|resumed)\b",
    "increased_sip": r"\b(?:never|not|didn't|did not|haven't|have not)\s+(?:increase|increased|raise|raised|step\s+up)\b",
}

TEMPORARY_PAUSE_RE = re.compile(
    r"\b(?:stopped|paused|pause|stop)\b.{0,40}\bfor\s+"
    r"(?:\d+|one|two|three|four|five|six|few|couple)\s*"
    r"(?:month|months|week|weeks|year|years)\b",
    re.IGNORECASE,
)
RESTART_RE = re.compile(
    r"\b(?:restart|restarted|resum|resumed|started\s+again|starting\s+again)\b",
    re.IGNORECASE,
)

SUPPORT: dict[str, dict[str, list[str]]] = {
    "journey_stages": {
        "pre_start": ["planning", "thinking", "considering", "want to start", "before i start", "tried to start", "yet to start"],
        "m0_setup": ["kyc", "mandate", "first instalment", "first installment", "account", "setup", "set up", "started", "start"],
        "m1_first_statement": ["first statement", "first month", "first portfolio", "first time"],
        "m3_early": ["2 month", "two month", "3 month", "three month", "4 month", "four month"],
        "m6_mid": ["5 month", "five month", "6 month", "six month", "7 month", "seven month", "8 month", "eight month"],
        "m9_late": [
            "9 month", "nine month", "10 month", "ten month", "11 month", "eleven month",
            "12 month", "twelve month", "1 year", "one year", "2 year", "two year",
            "3 year", "three year", "4 year", "four year",
        ],
        "post_lapse": ["stopped", "paused", "after stopping", "lapsed", "cancelled"],
    },
    "triggers": {
        "market_drawdown": ["market", "crash", "correction", "fall", "down", "flat period", "covid", "volatile", "volatility", "bad market", "market is really bad", "market bad"],
        "negative_returns": ["loss", "negative", "down", "returns", "xirr", "flat", "red", "not growing", "low return", "flat period"],
        "first_statement": ["statement", "first month", "first portfolio"],
        "payment_failure": ["failed", "failure", "declined", "not deducted", "missed", "bounce", "not credited"],
        "mandate_issue": ["mandate", "auto debit", "autopay", "nach"],
        "bank_issue": ["bank", "account blocked", "bank server"],
        "salary_delay": ["salary", "income delayed", "late salary"],
        "job_change": ["job", "lost job", "switched job", "layoff"],
        "income_volatility": ["freelance", "gig", "irregular income", "variable income"],
        "emergency_expense": ["emergency", "medical", "hospital", "expense"],
        "liquidity_need": ["need cash", "liquidity", "withdraw", "cash need"],
        "goal_doubt": ["doubt", "not sure", "confus", "goal"],
        "goal_achieved": ["goal achieved", "reached goal", "target reached"],
        "life_event": ["marriage", "child", "relocation", "education", "new house", "house fund", "home loan", "buying a house", "wedding"],
        "trust_shock": ["fraud", "scam", "cheat", "hidden charge", "mis-sell", "trust"],
        "news_event": ["news", "market news"],
        "finfluencer_advice": ["youtube advice", "yt advice", "influencer", "finfluencer", "creator", "recommended on youtube", "saw on youtube", "youtube video"],
        "friend_family_advice": ["friend told", "family told", "friend suggested", "family suggested", "colleague", "parents"],
        "product_comparison": ["compare", "comparison", "better than", "vs", "versus", "fd", "fixed deposit", "another app"],
        "app_friction": ["app", "ui", "bug", "error", "page", "feature", "confus", "difficult", "not working", "slow", "not credited", "cancellation request", "still active"],
        "product_suspension": ["paused due to", "rule about foreign investment", "regulatory", "amc paused", "fund suspended", "scheme suspended", "stopped accepting", "foreign investment limit", "sebi", "rbi", "discontinued"],
        "support_failure": ["support", "customer care", "no response", "not responding", "helpline"],
        "notification_fatigue": ["notification", "alert", "spam", "message"],
        "tax": ["tax", "80c", "elss"],
        "bonus_or_raise": ["bonus", "raise", "increment"],
    },
    "behaviors": {
        "started_sip": ["start", "begin", "first sip", "opened", "set up"],
        "increased_sip": ["increas", "rais", "step up", "top up", "top-up"],
        "decreased_sip": ["decreas", "reduc", "lower", "cut"],
        "paused_sip": ["paus", "hold", "skip", "skipped"],
        "stopped_sip": ["stop", "stopped", "cancel", "cancelled", "discontinued", "closed"],
        "restarted_sip": ["restart", "resum", "started again"],
        "switched_product": ["switch", "switched", "mov", "transfer"],
        "withdrew": ["withdraw", "withdrew", "redeem", "redeemed", "sell", "sold"],
        "checked_frequently": ["check", "checked", "daily", "every day", "frequently", "often", "monitor"],
        "checked_rarely": ["rarely", "monthly", "occasionally", "not check"],
        "avoided_app": ["avoid", "stopped opening", "scared to open", "didn't open"],
        "sought_help": ["help", "asked", "advice", "guidance", "support", "clarification", "alternative", "workaround"],
        "complained": ["complain", "complaint", "worst", "bad", "poor", "rubbish", "pathetic"],
        "recommended": ["recommend", "suggest", "advise"],
        "did_nothing": ["did nothing", "no action", "didn't do anything"],
    },
    "emotions": {
        "anxiety": ["anxious", "worr", "nervous", "stress", "scared", "fear", "tension", "panic", "darr", "couldn't stand", "can't stand", "hard time convincing"],
        "fear": ["fear", "scared", "afraid", "darr", "panic"],
        "shame": ["shame", "ashamed", "embarrassed", "stupid", "fool", "guilty"],
        "embarrassment": ["embarrassed", "embarrassment", "stupid", "fool"],
        "confusion": ["confus", "unsure", "not sure", "didn't understand", "don't understand", "samajh", "which means"],
        "frustration": ["frustrat", "annoy", "irritat", "fed up", "pareshan"],
        "anger": ["angry", "anger", "mad", "gussa"],
        "distrust": ["distrust", "suspicious", "trust issue", "scam", "fraud", "cheat"],
        "disappointment": ["disappoint", "let down", "sad", "dukh"],
        "apathy": ["don't care", "indifferent", "whatever", "no interest"],
        "regret": ["regret", "wish i", "should have"],
        "relief": ["relief", "relieved", "thank god", "glad"],
        "pride": ["proud", "pride"],
        "confidence": ["confident", "confidence", "trust"],
        "neutral": ["okay", "fine", "neutral"],
    },
    "expectations": {
        "guaranteed_returns": ["guarantee", "guaranteed", "assured", "no loss", "cannot lose"],
        "linear_growth": ["steady", "linear", "line", "always grow", "up only", "consistent"],
        "fd_like_safety": ["fd", "fixed deposit", "safe", "safety", "capital protection"],
        "quick_returns": ["quick", "fast", "soon", "within months", "short term"],
        "beat_inflation": ["inflation"],
        "build_wealth": ["wealth", "rich", "long term", "corpus", "crore"],
        "goal_progress": ["goal", "target", "progress"],
        "learn_investing": ["learn", "learning", "understand", "educational"],
        "tax_saving": ["tax", "80c", "elss"],
        "discipline": ["discipline", "forced saving", "habit", "regular saving"],
    },
    "help_seeking": {
        "friend_family": ["friend", "family", "colleague", "parents"],
        "youtube": ["youtube", "yt"],
        "reddit": ["reddit"],
        "google_search": ["google", "search"],
        "customer_support": ["support", "customer care", "helpline"],
        "bank": ["bank"],
        "ca_advisor": ["ca", "advisor", "financial advisor"],
        "app_help": ["help center", "app help", "faq"],
        "social_media": ["instagram", "twitter", "social media"],
        "none": ["no one", "nobody", "none"],
    },
    "outcomes": {
        "continues": [
            "continu",
            "continues",
            "still",
            "ongoing",
            "not stopped",
            "never stopped",
            "didn't stop",
            "did not stop",
            "haven't stopped",
            "have not stopped",
            "keeping",
            "keep",
            "running",
        ],
        "paused": ["paus", "temporarily"],
        "stopped": ["stop", "stopped", "cancel", "cancelled", "discontinued", "closed"],
        "returned": ["return", "returned", "resum", "restart", "restarted", "again"],
        "reduced": ["reduc", "reduced", "lower", "decreas"],
        "increased": ["increas", "increased", "rais", "raised"],
    },
    "segments": {
        "income_stability": {
            "salaried": ["salaried", "salary", "job", "employed", "corporate"],
            "variable": ["variable income", "irregular income", "commission"],
            "gig": ["freelance", "gig", "contract"],
            "student": ["student", "college"],
            "business": ["business", "self-employed", "self employed", "entrepreneur"],
            "retired": ["retired", "retirement"],
        },
        "source_of_money": {
            "own_income": ["salary", "my income", "earned", "i earn"],
            "family": ["parents", "family", "father", "mother"],
            "bonus": ["bonus"],
            "savings": ["savings", "saved"],
            "loan": ["loan", "borrowed"],
        },
        "influence": {
            "self": ["i decided", "i chose", "myself", "my own"],
            "friend_family": ["friend", "family", "colleague", "parents"],
            "youtube": ["youtube", "yt"],
            "employer": ["employer", "company"],
            "ca_advisor": ["ca", "advisor", "financial advisor"],
            "social_media": ["instagram", "twitter", "social media"],
        },
        "goal_type": {
            "named_goal": ["goal", "target"],
            "wealth": ["wealth", "rich", "corpus", "crore"],
            "tax": ["tax", "80c", "elss"],
            "retirement": ["retirement", "retire"],
            "education": ["education", "college", "school"],
            "emergency": ["emergency", "rainy day"],
        },
    },
}

FIRST_PERSON_RE = re.compile(r"\b(i|i'm|i’m|my|me|we|our|us|myself)\b")

PAYMENT_MECHANISM_STOP = [
    "auto debit stopped",
    "auto-debit stopped",
    "autopay stopped",
    "mandate stopped",
    "nach stopped",
    "auto debit is not working",
    "auto-debit is not working",
    "mandate failed",
    "mandate failure",
    "mandate rejected",
    "mandate expired",
    "mandate cancelled",
    "mandate canceled",
    "mandate is not active",
    "mandate not active",
    "mandate got cancelled",
    "mandate got canceled",
    "auto debit failed",
    "auto-debit failed",
    "autopay failed",
    "auto pay failed",
    "nach failed",
    "debit failed",
    "payment failed",
    "bank declined",
    "bank blocked",
    "insufficient funds",
    "insufficient balance",
    "upi autopay failed",
    "upi mandate failed",
]

AGE_RANGES = {
    "18-24": (18, 24),
    "25-29": (25, 29),
    "30-35": (30, 35),
    "36-45": (36, 45),
    "46+": (46, 120),
}


def _sentences(quote: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", quote) if part.strip()]


def _has_any(quote: str, keywords: list[str]) -> bool:
    return any(keyword in quote for keyword in keywords)


def _is_temporary_stop(quote: str) -> bool:
    if any(
        phrase in quote
        for phrase in (
            "temporarily stopped",
            "stopped temporarily",
            "stopped for now",
            "temporary stop",
            "temporarily paused",
            "paused for now",
        )
    ):
        return True
    if TEMPORARY_PAUSE_RE.search(quote):
        return True
    if re.search(r"\b(?:stopped|paused)\b.{0,70}\b(?:and|then)\b.{0,40}\b(?:restart|resum|started again)", quote, re.I):
        return True
    return False


def _is_third_person_action(sentence: str) -> bool:
    if not any(re.search(pattern, sentence, re.I) for pattern in THIRD_PERSON_PATTERNS):
        return False
    # If the author explicitly describes their own action in the same sentence,
    # keep it. Example: "My friend stopped his SIP, but I stopped mine too."
    if re.search(
        r"\bi\s+(?:also\s+)?(?:stopped|paused|cancelled|canceled|started|increased|decreased|withdrew|redeemed|restarted|resumed)\b",
        sentence,
        re.I,
    ):
        return False
    return True


def _has_action(
    quote: str,
    keywords: list[str],
    context_keywords: list[str] | None = None,
    require_first_person: bool = False,
    skip_payment_stop: bool = False,
    negation_pattern: str | None = None,
) -> bool:
    for sentence in _sentences(quote):
        if not any(keyword in sentence for keyword in keywords):
            continue
        if context_keywords and not any(context in sentence for context in context_keywords):
            continue
        if require_first_person and not FIRST_PERSON_RE.search(sentence):
            continue
        if require_first_person and _is_third_person_action(sentence):
            continue
        if negation_pattern and re.search(negation_pattern, sentence, re.I):
            continue
        if skip_payment_stop and any(phrase in sentence for phrase in PAYMENT_MECHANISM_STOP):
            continue
        if any(phrase in sentence for phrase in ATTEMPT_PHRASES):
            continue
        return True
    return False


def _ground_behaviors(quote: str, values: list[str]) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    dropped: list[str] = []
    normalized_values: list[str] = []
    for value in values:
        # "I paused my SIP" is often labelled stopped by the model. Normalize
        # it to paused before checking support, so a temporary pause is not
        # counted as a lapse.
        if (
            value == "stopped_sip"
            and re.search(r"\bpaus", quote, re.I)
            and not re.search(r"\bstop", quote, re.I)
        ):
            value = "paused_sip"
        normalized_values.append(value)

    for value in normalized_values:
        if value in ("other", "unknown"):
            dropped.append(value)
            continue
        keywords = SUPPORT["behaviors"].get(value)
        if keywords is None:
            kept.append(value)
            continue
        if value in SIP_SPECIFIC_BEHAVIORS:
            context = ["sip"] if value in SIP_ONLY_BEHAVIORS else SIP_CONTEXT
            if _has_action(
                quote,
                keywords,
                context,
                require_first_person=True,
                skip_payment_stop=value in ("stopped_sip", "paused_sip"),
                negation_pattern=NEGATION_PATTERNS.get(value),
            ):
                kept.append(value)
            else:
                dropped.append(value)
        elif _has_any(quote, keywords):
            kept.append(value)
        else:
            dropped.append(value)

    # High-precision derived behaviours: if the quote explicitly says the
    # author paused or restarted their SIP, keep that event even when the model
    # labelled it as a stop.
    if "paused_sip" not in kept and _has_action(
        quote,
        ["paus", "pause", "paused"],
        ["sip"],
        require_first_person=True,
        negation_pattern=NEGATION_PATTERNS["paused_sip"],
    ):
        kept.append("paused_sip")
    if "restarted_sip" not in kept and RESTART_RE.search(quote) and _has_action(
        quote,
        ["restart", "resum", "started again"],
        ["sip"],
        require_first_person=True,
        negation_pattern=NEGATION_PATTERNS["restarted_sip"],
    ):
        kept.append("restarted_sip")
    if "stopped_sip" in kept and RESTART_RE.search(quote) and _is_temporary_stop(quote):
        kept.remove("stopped_sip")
        if "paused_sip" not in kept:
            kept.append("paused_sip")
        if "restarted_sip" not in kept:
            kept.append("restarted_sip")
    return list(dict.fromkeys(kept)), dropped


def _ground_list(quote: str, field: str, values: list[str]) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    dropped: list[str] = []
    for value in values:
        if value in ("other", "unknown"):
            dropped.append(value)
            continue
        keywords = SUPPORT.get(field, {}).get(value)
        if keywords is None:
            kept.append(value)
        elif _has_any(quote, keywords):
            kept.append(value)
        else:
            dropped.append(value)
    return kept, dropped


def _ground_stage(quote: str, stage: str) -> tuple[str, list[str]]:
    if stage in (None, "unknown"):
        return "unknown", []
    keywords = SUPPORT["journey_stages"].get(stage)
    if keywords and _has_any(quote, keywords):
        return stage, []
    return "unknown", [f"journey_stage unsupported: {stage}"]


def _ground_outcome(quote: str, outcome: str) -> tuple[str, list[str]]:
    if outcome in (None, "unknown"):
        return "unknown", []
    keywords = SUPPORT["outcomes"].get(outcome)
    if not keywords:
        return "unknown", [f"outcome unsupported: {outcome}"]
    if outcome in ("stopped", "paused", "returned", "reduced", "increased", "continues"):
        negation = {
            "stopped": NEGATION_PATTERNS["stopped_sip"],
            "paused": NEGATION_PATTERNS["paused_sip"],
            "returned": NEGATION_PATTERNS["restarted_sip"],
            "reduced": NEGATION_PATTERNS["decreased_sip"],
            "increased": NEGATION_PATTERNS["increased_sip"],
        }.get(outcome)
        if _has_action(
            quote,
            keywords,
            SIP_CONTEXT,
            require_first_person=True,
            skip_payment_stop=False,
            negation_pattern=negation,
        ):
            if outcome == "stopped" and _is_temporary_stop(quote):
                return "paused", []
            if outcome in ("stopped", "paused") and RESTART_RE.search(quote):
                return "returned", []
            return outcome, []
    elif _has_any(quote, keywords):
        return outcome, []
    return "unknown", [f"outcome unsupported: {outcome}"]


def _age_supported(quote: str, band: str) -> bool:
    match = re.search(r"\b(\d{2})\s*(?:years?|yrs?)\s*old\b", quote)
    if not match:
        match = re.search(r"\bi(?:'m| am)\s+(\d{2})\b", quote)
    if not match:
        return False
    age = int(match.group(1))
    low, high = AGE_RANGES.get(band, (0, -1))
    return low <= age <= high


def _ground_segments(quote: str, segment: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    grounded: dict[str, str] = {}
    warnings: list[str] = []
    for key, value in segment.items():
        if value in (None, "unknown", "unspecified"):
            grounded[key] = "unknown"
            continue
        if key == "age_band":
            supported = _age_supported(quote, str(value))
        elif key == "ticket_size":
            supported = bool(re.search(r"(₹|rs\.?|inr|rupees|lakh|crore|\d{4,})", quote))
        else:
            supported = _has_any(quote, SUPPORT.get("segments", {}).get(key, {}).get(str(value), []))
        if supported:
            grounded[key] = str(value)
        else:
            grounded[key] = "unknown"
            warnings.append(f"segment {key} unsupported: {value}")
    return grounded, warnings


def is_meaningful(payload: dict[str, Any]) -> bool:
    """A tenure-only or segment-only signal is not useful on its own."""
    if payload.get("outcome") not in (None, "unknown"):
        return True
    for field in ("triggers", "behaviors", "emotions", "expectations"):
        if payload.get(field):
            return True
    return False


def _derive_stage(quote: str, payload: dict[str, Any]) -> str | None:
    """Fill an unknown journey stage from explicit tenure language."""
    if payload.get("journey_stage") not in (None, "unknown"):
        return None

    if "first statement" in quote or "first month" in quote:
        stage = "m1_first_statement"
    else:
        stage = None
        word_to_num = {
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
        }
        month_match = re.search(
            r"\b(\d+|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s*(month|months)\b",
            quote,
        )
        if month_match:
            raw = month_match.group(1)
            months = int(raw) if raw.isdigit() else word_to_num.get(raw)
            if months is not None:
                if 2 <= months <= 4:
                    stage = "m3_early"
                elif 5 <= months <= 8:
                    stage = "m6_mid"
                elif months >= 9:
                    stage = "m9_late"
        if stage is None:
            year_match = re.search(
                r"\b(\d+(?:\.\d+)?|one|two|three|four)\s*(year|years)\b", quote
            )
            if year_match or "a year" in quote:
                stage = "m9_late"

    if stage:
        payload["journey_stage"] = stage
        return f"journey_stage {stage} (tenure)"
    return None


def _derive_codes(quote: str, payload: dict[str, Any]) -> list[str]:
    """Add high-precision codes from explicit phrases the LLM sometimes misses."""
    derived: list[str] = []
    triggers = list(payload.get("triggers") or [])

    has_cancel = any(
        phrase in quote
        for phrase in (
            "cancellation request",
            "requested to cancel",
            "cancel my sip",
            "cancel my monthly sip",
            "cancel sip",
        )
    )
    has_delay = any(
        phrase in quote
        for phrase in (
            "still active",
            "still deducted",
            "money got deducted",
            "amount got deducted",
            "not stopped",
            "still not stopped",
        )
    )
    if has_cancel and has_delay and "app_friction" not in triggers:
        triggers.append("app_friction")
        derived.append("trigger app_friction (cancellation flow)")

    if "sip" in quote and any(
        phrase in quote
        for phrase in (
            "debit failed",
            "payment failed",
            "auto debit failed",
            "autopay failed",
            "amount bounced",
            "sip bounced",
        )
    ):
        if "payment_failure" not in triggers:
            triggers.append("payment_failure")
            derived.append("trigger payment_failure (debit failure)")

    if "mandate" in quote and any(
        phrase in quote for phrase in ("failed", "rejected", "not registered", "issue", "problem")
    ):
        if "mandate_issue" not in triggers:
            triggers.append("mandate_issue")
            derived.append("trigger mandate_issue (mandate problem)")

    if "market" in quote and any(
        phrase in quote for phrase in ("really bad", "bad", "crash", "fall", "correction")
    ):
        if "market_drawdown" not in triggers:
            triggers.append("market_drawdown")
            derived.append("trigger market_drawdown (market sentiment)")

    has_sip_action = any(
        behavior in (payload.get("behaviors") or [])
        for behavior in ("stopped_sip", "paused_sip", "decreased_sip", "withdrew")
    )
    if has_sip_action and any(
        phrase in quote
        for phrase in (
            "house fund",
            "home loan",
            "buying a house",
            "wedding",
            "marriage",
            "child",
            "education",
            "closing the loan",
            "loan prepayment",
            "prepay",
        )
    ):
        if "life_event" not in triggers:
            triggers.append("life_event")
            derived.append("trigger life_event (competing goal/life event)")

    if "sip" in quote and any(
        phrase in quote
        for phrase in (
            "paused due to",
            "rule about foreign investment",
            "foreign investment limit",
            "fund suspended",
            "scheme suspended",
            "amc paused",
            "stopped accepting",
            "sebi",
            "rbi",
        )
    ):
        if "product_suspension" not in triggers:
            triggers.append("product_suspension")
            derived.append("trigger product_suspension (AMC/regulator pause)")

    payload["triggers"] = triggers

    if "sip" in quote and any(
        phrase in quote
        for phrase in (
            "never stopped",
            "didn't stop",
            "did not stop",
            "haven't stopped",
            "have not stopped",
            "still investing",
            "still doing sip",
            "continuing my sip",
        )
    ):
        if payload.get("outcome") in (None, "unknown"):
            payload["outcome"] = "continues"
            derived.append("outcome continues (explicit continuation)")

    stage_note = _derive_stage(quote, payload)
    if stage_note:
        derived.append(stage_note)

    return derived


def ground_signal_payload(
    payload: dict[str, Any],
    quote: str,
    segment_quote: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Drop codes not supported by the quote. Returns cleaned payload and warnings.

    Behavioural codes are grounded against ``quote``. Segment cues are grounded
    against ``segment_quote`` when the model supplied a separate, verified
    segment-evidence span; otherwise they fall back to the main quote.
    """
    quote_lower = " ".join(quote.lower().split())
    segment_text = segment_quote.strip() if segment_quote else quote
    segment_lower = " ".join(segment_text.lower().split())
    grounded = dict(payload)
    warnings: list[str] = []

    stage, stage_warnings = _ground_stage(quote_lower, grounded.get("journey_stage", "unknown"))
    grounded["journey_stage"] = stage
    warnings.extend(stage_warnings)

    outcome, outcome_warnings = _ground_outcome(quote_lower, grounded.get("outcome", "unknown"))
    grounded["outcome"] = outcome
    warnings.extend(outcome_warnings)

    for field in ("triggers", "emotions", "expectations", "help_seeking"):
        kept, dropped = _ground_list(quote_lower, field, grounded.get(field) or [])
        grounded[field] = kept
        if dropped:
            warnings.append(f"{field} unsupported: {dropped}")

    behaviors, dropped_behaviors = _ground_behaviors(quote_lower, grounded.get("behaviors") or [])
    grounded["behaviors"] = behaviors
    if dropped_behaviors:
        warnings.append(f"behaviors unsupported: {dropped_behaviors}")

    if _is_temporary_stop(quote_lower):
        behaviors = list(grounded.get("behaviors") or [])
        if "stopped_sip" in behaviors:
            behaviors.remove("stopped_sip")
            if "paused_sip" not in behaviors:
                behaviors.append("paused_sip")
            warnings.append("temporary stop -> paused_sip")
        grounded["behaviors"] = behaviors
        if grounded.get("outcome") == "stopped":
            grounded["outcome"] = "paused"
            warnings.append("temporary stop -> outcome paused")

    if grounded.get("outcome") in (None, "unknown"):
        if "restarted_sip" in (grounded.get("behaviors") or []):
            grounded["outcome"] = "returned"
            warnings.append("outcome returned (from restarted_sip)")
        elif "paused_sip" in (grounded.get("behaviors") or []):
            grounded["outcome"] = "paused"
            warnings.append("outcome paused (from paused_sip)")

    derived = _derive_codes(quote_lower, grounded)
    if derived:
        warnings.extend(f"derived: {item}" for item in derived)

    segments, segment_warnings = _ground_segments(segment_lower, grounded.get("segment_cues") or {})
    grounded["segment_cues"] = segments
    warnings.extend(segment_warnings)

    return grounded, warnings
