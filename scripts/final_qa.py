"""Final QA checks for the discovery engine and its deliverables."""

from __future__ import annotations

import json
import py_compile
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import pymupdf
from pptx import Presentation
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.analysis import LAPSE_OUTCOMES, document_outcomes, signals_frame, theme_summary
from src.db import get_session
from src.grounding import is_meaningful
from src.models import Document, Signal
from src.pipeline.extract import verify_quote

ROOT = Path(__file__).resolve().parents[1]
DELIVERABLES = ROOT / "deliverables"
EXPORTS = ROOT / "data" / "exports"


def check(condition: bool, label: str, detail: str = "") -> dict:
    return {"check": label, "pass": bool(condition), "detail": detail}


def main() -> None:
    checks: list[dict] = []

    with get_session() as session:
        signals, documents = signals_frame(session)
        documents = document_outcomes(signals, documents)
        summary = theme_summary(signals, documents)
        total_documents = int(len(documents))
        deep_coded = int(documents["deep_coded"].sum())
        strict = int(documents["strict_relevant"].sum())
        all_signals = session.scalars(
            select(Signal).options(selectinload(Signal.document))
        ).all()

    checks.append(check(total_documents >= 5000, "Corpus >= 5,000 documents", str(total_documents)))
    checks.append(check(strict >= 1500, "Strict candidates >= 1,500", str(strict)))
    checks.append(check(deep_coded >= 1500, "Deep-coded >= 1,500", str(deep_coded)))
    checks.append(check(len(signals) >= 200, "Grounded signals >= 200", str(len(signals))))

    quote_ok = 0
    quote_bad = 0
    for signal in all_signals:
        if signal.quote and verify_quote(signal.document, signal.quote) is not None:
            quote_ok += 1
        else:
            quote_bad += 1
    checks.append(
        check(
            quote_bad == 0,
            "Every stored signal has a verifiable quote",
            f"{quote_ok} verified, {quote_bad} rejected",
        )
    )

    meaningful = sum(
        1
        for row in signals.to_dict("records")
        if is_meaningful(
            {
                "outcome": row.get("outcome"),
                "triggers": row.get("triggers") or [],
                "behaviors": row.get("behaviors") or [],
                "emotions": row.get("emotions") or [],
                "expectations": row.get("expectations") or [],
            }
        )
    )
    checks.append(
        check(
            meaningful == len(signals),
            "Every active signal has at least one meaningful code",
            f"{meaningful}/{len(signals)}",
        )
    )

    resolved_docs = int(
        documents["document_outcome"]
        .isin(LAPSE_OUTCOMES | {"continues", "increased", "returned"})
        .sum()
    )
    checks.append(
        check(
            resolved_docs >= 75,
            "At least 75 documents have a resolved outcome",
            str(resolved_docs),
        )
    )

    checks.append(
        check(
            len(summary[summary["kind"] == "problem"]) >= 6,
            "At least six problem themes",
            str(len(summary[summary["kind"] == "problem"])),
        )
    )

    # Validation artefacts
    gold_path = EXPORTS / "gold_set_200.csv"
    gold_rows = 0
    if gold_path.exists():
        gold_rows = len(pd.read_csv(gold_path))
    checks.append(check(gold_rows >= 200, "Gold set has 200 rows", str(gold_rows)))

    swap_path = EXPORTS / "model_swap_agreement.json"
    swap = json.loads(swap_path.read_text(encoding="utf-8")) if swap_path.exists() else {}
    checks.append(
        check(
            int(swap.get("compared_items") or 0) >= 100,
            "Model swap covers >= 100 quota-sized items",
            str(swap.get("compared_items", 0)),
        )
    )

    checks.append(
        check(
            int((swap.get("outcome") or {}).get("compared") or 0) >= 60,
            "Outcome kappa covers >= 60 resolved outcomes",
            str((swap.get("outcome") or {}).get("compared", 0)),
        )
    )

    red_path = EXPORTS / "red_team_report.json"
    red = json.loads(red_path.read_text(encoding="utf-8")) if red_path.exists() else {}
    checks.append(
        check(
            red.get("failed", 1) == 0,
            "Red-team suite has no failures",
            f"{red.get('passed', 0)}/{red.get('tests', 0)}",
        )
    )

    # Deliverables
    expected = {
        "Evidence log PDF": DELIVERABLES / "AI_Evidence_Log.pdf",
        "Evidence log CSV": EXPORTS / "ai_evidence_log.csv",
        "Evidence log JSONL": EXPORTS / "ai_evidence_log.jsonl",
        "Deck PPTX": DELIVERABLES / "INDmoney_SIP_Discovery_Deck.pptx",
        "Deck PDF": DELIVERABLES / "INDmoney_SIP_Discovery_Deck.pdf",
        "PRD PDF": DELIVERABLES / "INDmoney_SIP_Discovery_PRD.pdf",
        "Case write-up PDF": DELIVERABLES / "INDmoney_SIP_Case_Writeup.pdf",
    }
    for label, path in expected.items():
        checks.append(check(path.exists() and path.stat().st_size > 10_000, label, str(path)))

    if (DELIVERABLES / "AI_Evidence_Log.pdf").exists():
        pages = len(pymupdf.open(DELIVERABLES / "AI_Evidence_Log.pdf"))
        checks.append(check(pages >= 2, "Evidence log PDF has content", f"{pages} pages"))
    if (DELIVERABLES / "INDmoney_SIP_Discovery_PRD.pdf").exists():
        pages = len(pymupdf.open(DELIVERABLES / "INDmoney_SIP_Discovery_PRD.pdf"))
        checks.append(check(pages >= 12, "PRD PDF has content", f"{pages} pages"))
    if (DELIVERABLES / "INDmoney_SIP_Case_Writeup.pdf").exists():
        pages = len(pymupdf.open(DELIVERABLES / "INDmoney_SIP_Case_Writeup.pdf"))
        checks.append(check(pages >= 4, "Case write-up has content", f"{pages} pages"))
    if (DELIVERABLES / "INDmoney_SIP_Discovery_Deck.pptx").exists():
        slides = len(Presentation(DELIVERABLES / "INDmoney_SIP_Discovery_Deck.pptx").slides)
        checks.append(check(slides >= 15, "Deck has >= 15 slides", f"{slides} slides"))

    # Syntax / import smoke checks
    for script in ("dashboard/app.py", "src/analysis.py", "src/reporting.py"):
        try:
            py_compile.compile(str(ROOT / script), doraise=True)
            checks.append(check(True, f"Compiles: {script}"))
        except py_compile.PyCompileError as exc:
            checks.append(check(False, f"Compiles: {script}", str(exc)[:200]))

    passed = sum(1 for item in checks if item["pass"])
    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "passed": passed,
        "total": len(checks),
        "failed": len(checks) - passed,
        "checks": checks,
        "facts": {
            "documents": total_documents,
            "strict_candidates": strict,
            "deep_coded": deep_coded,
            "signals": int(len(signals)),
            "signal_documents": int(signals["document_id"].nunique()) if not signals.empty else 0,
            "known_outcomes": resolved_docs,
        },
    }
    EXPORTS.mkdir(parents=True, exist_ok=True)
    (EXPORTS / "final_qa_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Final QA: {passed}/{len(checks)} checks passed")
    for item in checks:
        status = "PASS" if item["pass"] else "FAIL"
        print(f"  [{status}] {item['check']}: {item['detail']}")
    print(f"Report: {EXPORTS / 'final_qa_report.json'}")
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
