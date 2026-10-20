"""Debug sentence-level grounding for a sample quote."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import src.grounding as grounding

QUOTE = (
    "I started investing in Mutual Funds in 2020 with a small amount, I have "
    "gradually increased it to a point that my existing equity portfolio is "
    "80% MF. I had SIP in 4 funds, in which i was increasing my SIP amount "
    "whenever I could."
).lower()

print("Sentences:")
for index, sentence in enumerate(grounding._sentences(QUOTE), start=1):
    print(f"  {index}: {sentence!r}")
    print(f"    sip in sentence: {'sip' in sentence}")
    print(f"    increase in sentence: {'increase' in sentence}")
    for phrase in grounding.ATTEMPT_PHRASES:
        if phrase in sentence:
            print(f"    attempt phrase: {phrase!r}")

print("keywords:", grounding.SUPPORT["behaviors"]["increased_sip"])
print("has_action:", grounding._has_action(QUOTE, ["increase"], ["sip"]))
kept, dropped = grounding._ground_behaviors(QUOTE, ["started_sip", "increased_sip"])
print(f"kept={kept} dropped={dropped}")
