"""Re-run deterministic grounding on stored signals after rule changes.

This does not call the LLM. It removes false positives that the current
grounding rules reject (third-person actions, negations, payment-mechanism
stops) and adds high-precision derived behaviours such as paused/restarted.
Dropped signals are retained for audit but excluded from analysis.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from src.db import get_session
from src.grounding import ground_signal_payload, is_meaningful
from src.models import Signal


def main() -> None:
    with get_session() as session:
        signals = session.scalars(select(Signal).order_by(Signal.id)).all()
        kept = 0
        dropped = 0
        changed = 0
        for signal in signals:
            raw = dict(signal.raw or {})
            if raw.get("reground_status") == "dropped":
                dropped += 1
                continue
            payload = {
                "journey_stage": signal.journey_stage or "unknown",
                "triggers": list(signal.triggers or []),
                "behaviors": list(signal.behaviors or []),
                "emotions": list(signal.emotions or []),
                "expectations": list(signal.expectations or []),
                "help_seeking": list(signal.help_seeking or []),
                "outcome": signal.outcome or "unknown",
                "segment_cues": dict(signal.segment or {}),
                "confidence": signal.confidence or "medium",
            }
            before = (
                payload["journey_stage"],
                tuple(payload["behaviors"]),
                payload["outcome"],
            )
            grounded, warnings = ground_signal_payload(
                payload,
                signal.quote or "",
                segment_quote=raw.get("segment_quote"),
            )
            meaningful = is_meaningful(grounded)
            signal.journey_stage = grounded["journey_stage"]
            signal.triggers = grounded["triggers"]
            signal.behaviors = grounded["behaviors"]
            signal.emotions = grounded["emotions"]
            signal.expectations = grounded["expectations"]
            signal.help_seeking = grounded["help_seeking"]
            signal.outcome = grounded["outcome"]
            signal.segment = grounded["segment_cues"]
            raw["reground_status"] = "kept" if meaningful else "dropped"
            raw["reground_warnings"] = warnings
            raw["reground_at"] = datetime.utcnow().isoformat() + "Z"
            signal.raw = raw
            after = (
                signal.journey_stage,
                tuple(signal.behaviors),
                signal.outcome,
            )
            if before != after:
                changed += 1
            if meaningful:
                kept += 1
            else:
                dropped += 1
        session.commit()

    print(f"Signals processed: {len(signals)}")
    print(f"Kept: {kept}")
    print(f"Dropped: {dropped}")
    print(f"Changed by regrounding: {changed}")


if __name__ == "__main__":
    main()
