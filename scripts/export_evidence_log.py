"""Export the AI Evidence Log as CSV, JSONL, and a readable PDF."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.analysis import (
    document_outcomes,
    signals_frame,
    theme_summary,
)
from src.db import get_session
from src.reporting import STAGE_LABELS

NAVY = colors.HexColor("#17324D")
TEAL = colors.HexColor("#1F6F5C")
LIGHT = colors.HexColor("#EEF4F1")
GREY = colors.HexColor("#5B6770")


PDF_TRANSLATION = str.maketrans(
    {
        "\u20b9": "Rs ",
        "\u03ba": "kappa",
        "\u2265": ">=",
        "\u2264": "<=",
        "\u2192": "->",
        "\u2212": "-",
    }
)


def _pdf_safe(value: object) -> str:
    return str(value).translate(PDF_TRANSLATION)


def _short(value: object, limit: int = 240) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    text = text if len(text) <= limit else text[: limit - 1] + "…"
    return _pdf_safe(text)


def _theme_names(summary: pd.DataFrame) -> dict[str, str]:
    return dict(zip(summary["slug"], summary["name"]))


def build_evidence_frame(
    signals: pd.DataFrame,
    summary: pd.DataFrame,
) -> pd.DataFrame:
    names = _theme_names(summary)
    frame = signals.copy()
    frame["primary_theme_name"] = frame["primary_theme"].map(names).fillna(frame["primary_theme"])
    frame["theme_names"] = frame["themes"].apply(
        lambda values: "; ".join(names.get(value, value) for value in values)
    )
    frame["triggers_text"] = frame["triggers"].apply(lambda values: ", ".join(values) or "—")
    frame["behaviors_text"] = frame["behaviors"].apply(lambda values: ", ".join(values) or "—")
    frame["emotions_text"] = frame["emotions"].apply(lambda values: ", ".join(values) or "—")
    frame["expectations_text"] = frame["expectations"].apply(
        lambda values: ", ".join(values) or "—"
    )
    frame["help_text"] = frame["help_seeking"].apply(lambda values: ", ".join(values) or "—")
    frame["segment_text"] = frame.apply(
        lambda row: ", ".join(
            f"{key}={row[key]}"
            for key in (
                "age_band",
                "income_stability",
                "source_of_money",
                "influence",
                "ticket_size",
                "goal_type",
            )
            if row.get(key) not in (None, "unknown", "")
        )
        or "—",
        axis=1,
    )
    frame["verified"] = frame["quote_start"].notna().map(lambda value: "yes" if value else "no")
    frame["quote"] = frame["quote"].fillna("")
    return frame


def write_csv_jsonl(frame: pd.DataFrame, output_dir: Path) -> None:
    columns = [
        "signal_id",
        "document_id",
        "source",
        "url",
        "published_at",
        "primary_theme_name",
        "theme_names",
        "quote",
        "quote_start",
        "quote_end",
        "verified",
        "outcome",
        "journey_stage",
        "confidence",
        "triggers_text",
        "behaviors_text",
        "emotions_text",
        "expectations_text",
        "help_text",
        "segment_text",
        "segment_quote",
        "model",
        "provider",
    ]
    evidence = frame[columns].copy()
    evidence.columns = [
        "evidence_id",
        "document_id",
        "source",
        "source_url",
        "source_date",
        "primary_theme",
        "all_themes",
        "quote",
        "quote_start",
        "quote_end",
        "quote_verified",
        "outcome",
        "journey_stage",
        "confidence",
        "triggers",
        "behaviors",
        "emotions",
        "expectations",
        "help_seeking",
        "segments",
        "segment_quote",
        "model",
        "provider",
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence.to_csv(output_dir / "ai_evidence_log.csv", index=False, encoding="utf-8-sig")
    with (output_dir / "ai_evidence_log.jsonl").open("w", encoding="utf-8") as handle:
        for record in evidence.to_dict(orient="records"):
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def build_pdf(
    frame: pd.DataFrame,
    summary: pd.DataFrame,
    output_path: Path,
    limit_per_theme: int = 25,
) -> None:
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CoverTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=30,
            leading=36,
            textColor=NAVY,
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverSub",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=13,
            leading=19,
            textColor=GREY,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Section",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=TEAL,
            spaceBefore=8,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Small",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9.5,
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9.5,
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="QuoteSmall",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=7.5,
            leading=9.5,
            alignment=TA_LEFT,
        )
    )

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title="AI Evidence Log — INDmoney SIP Discovery Engine",
        author="INDmoney Growth Discovery Engine",
    )
    story = []
    story.append(Spacer(1, 38 * mm))
    story.append(Paragraph("AI Evidence Log", styles["CoverTitle"]))
    story.append(
        Paragraph(
            "Why first-time Indian mutual-fund investors lapse by month 12",
            styles["CoverSub"],
        )
    )
    story.append(
        Paragraph(
            "Grounded public evidence, source links, and machine-readable codes. "
            "Every quote in this log was verified against the source document.",
            styles["CoverSub"],
        )
    )
    story.append(Spacer(1, 12 * mm))
    story.append(
        Paragraph(
            f"Signals: {len(frame):,} · Documents with signals: {frame['document_id'].nunique():,} · "
            f"Themes: {len(summary):,}",
            styles["Small"],
        )
    )
    story.append(
        Paragraph(
            "Public sources only: Play Store, App Store, Reddit, YouTube, ValuePickr, TradingQ&A. "
            "No internal analytics, CRM records, or primary interviews.",
            styles["Small"],
        )
    )
    story.append(PageBreak())

    story.append(Paragraph("How to read this log", styles["Section"]))
    story.append(
        Paragraph(
            "Each row is one grounded signal: a short exact quote from a public post plus the "
            "behaviour, trigger, emotion, expectation, outcome, and journey-stage codes that the "
            "quote supports. Codes that were not supported by the quote were dropped by the "
            "deterministic grounding layer. Segment cues may use a separate verified segment quote. "
            "The full machine-readable table is in ai_evidence_log.csv and ai_evidence_log.jsonl.",
            styles["Small"],
        )
    )
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Theme summary", styles["Section"]))
    summary_rows = [
        [
            Paragraph("Theme", styles["SmallBold"]),
            Paragraph("Signals", styles["SmallBold"]),
            Paragraph("Docs", styles["SmallBold"]),
            Paragraph("Lapse rate", styles["SmallBold"]),
            Paragraph("Lift", styles["SmallBold"]),
            Paragraph("Score", styles["SmallBold"]),
        ]
    ]
    for _, row in summary.head(10).iterrows():
        summary_rows.append(
            [
                Paragraph(str(row["name"]), styles["Small"]),
                Paragraph(str(int(row["signals"])), styles["Small"]),
                Paragraph(str(int(row["documents"])), styles["Small"]),
                Paragraph(str(row["lapse_display"]), styles["Small"]),
                Paragraph(str(row["lift_display"]), styles["Small"]),
                Paragraph(f"{row['opportunity_score']:.1f}", styles["Small"]),
            ]
        )
    table = Table(summary_rows, colWidths=[87 * mm, 18 * mm, 16 * mm, 22 * mm, 26 * mm, 18 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
                ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C9D6D0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAF8")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(table)
    story.append(
        Paragraph(
            "n/a = no resolved outcome in public posts; the opportunity score uses a friction prior, not an observed "
            "lapse rate. Lift compares the theme's lapse rate with the corpus baseline.",
            styles["Small"],
        )
    )
    story.append(PageBreak())

    names = _theme_names(summary)
    for _, theme_row in summary.iterrows():
        slug = theme_row["slug"]
        if slug == "other_unclassified":
            continue
        subset = frame[frame["themes"].apply(lambda values: slug in values)]
        if subset.empty:
            continue
        story.append(Paragraph(names.get(slug, slug), styles["Section"]))
        story.append(
            Paragraph(
                f"{theme_row['definition']}  ·  Signals: {int(theme_row['signals'])}  ·  "
                f"Documents: {int(theme_row['documents'])}  ·  Lapse rate: {theme_row['lapse_display']}  ·  "
                f"Lift: {theme_row['lift_display']}  ·  Opportunity score: {theme_row['opportunity_score']:.1f}",
                styles["Small"],
            )
        )
        story.append(Spacer(1, 2 * mm))
        rows = [
            [
                Paragraph("ID", styles["SmallBold"]),
                Paragraph("Source", styles["SmallBold"]),
                Paragraph("Quote (verified)", styles["SmallBold"]),
                Paragraph("Outcome / stage", styles["SmallBold"]),
                Paragraph("Codes", styles["SmallBold"]),
                Paragraph("Link", styles["SmallBold"]),
            ]
        ]
        subset = subset.sort_values(
            ["confidence", "signal_id"],
            ascending=[True, True],
        )
        for _, row in subset.head(limit_per_theme).iterrows():
            codes = " · ".join(
                part
                for part in [
                    f"T: {row['triggers_text']}" if row["triggers_text"] != "—" else "",
                    f"B: {row['behaviors_text']}" if row["behaviors_text"] != "—" else "",
                    f"E: {row['emotions_text']}" if row["emotions_text"] != "—" else "",
                    f"X: {row['expectations_text']}" if row["expectations_text"] != "—" else "",
                ]
                if part
            ) or "—"
            rows.append(
                [
                    Paragraph(str(int(row["signal_id"])), styles["Small"]),
                    Paragraph(_short(row["source"], 28), styles["Small"]),
                    Paragraph(_short(row["quote"], 300), styles["QuoteSmall"]),
                    Paragraph(
                        _pdf_safe(
                            f"{row['outcome']} · "
                            f"{STAGE_LABELS.get(row['journey_stage'], row['journey_stage'])} · "
                            f"{row['confidence']}"
                        ),
                        styles["Small"],
                    ),
                    Paragraph(_short(codes, 180), styles["Small"]),
                    Paragraph(_short(row["url"] or "—", 70), styles["Small"]),
                ]
            )
        table = Table(
            rows,
            colWidths=[10 * mm, 27 * mm, 112 * mm, 34 * mm, 62 * mm, 42 * mm],
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
                    ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C9D6D0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAF8")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        story.append(table)
        if len(subset) > limit_per_theme:
            story.append(
                Paragraph(
                    f"Showing {limit_per_theme} of {len(subset)} signals. The full set is in the CSV/JSONL export.",
                    styles["Small"],
                )
            )
        story.append(PageBreak())

    story.append(Paragraph("Verification and guardrails", styles["Section"]))
    story.append(
        Paragraph(
            "Quote verification: every behavioural quote is checked as a normalized substring of the "
            "source document. Quotes that cannot be verified, exceed the length limit, or rely on a "
            "soft match are rejected. Grounding then checks sentence-level keyword support, first-person "
            "action language, attempt-vs-completed actions, payment-mechanism language, temporary-stop "
            "language, and separate segment evidence. The LLM is used for extraction and drafting, not "
            "for counting. No specific funds or stocks are recommended; no fear, FOMO, or urgency nudges "
            "are used in the interventions.",
            styles["Small"],
        )
    )
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("Column dictionary", styles["Section"]))
    dictionary_rows = [
        [Paragraph("Column", styles["SmallBold"]), Paragraph("Meaning", styles["SmallBold"])],
        [
            Paragraph("ID", styles["Small"]),
            Paragraph("Stable signal identifier within this corpus snapshot.", styles["Small"]),
        ],
        [
            Paragraph("Source", styles["Small"]),
            Paragraph("Platform and app/forum label, for example reddit or app_store:Kuvera.", styles["Small"]),
        ],
        [
            Paragraph("Quote", styles["Small"]),
            Paragraph("Exact verified substring from the public document; no paraphrase.", styles["Small"]),
        ],
        [
            Paragraph("Outcome / stage", styles["Small"]),
            Paragraph("Self-reported outcome, journey stage, and confidence; unknown means not stated.", styles["Small"]),
        ],
        [
            Paragraph("Codes", styles["Small"]),
            Paragraph("T = trigger, B = behaviour, E = emotion, X = expectation. Codes are grounded.", styles["Small"]),
        ],
        [
            Paragraph("Link", styles["Small"]),
            Paragraph("Public URL, truncated in the PDF; full URL in the CSV/JSONL export.", styles["Small"]),
        ],
    ]
    dictionary = Table(dictionary_rows, colWidths=[32 * mm, 142 * mm])
    dictionary.hAlign = "LEFT"
    dictionary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E5A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D9E2DE")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(dictionary)
    story.append(Spacer(1, 5 * mm))
    story.append(
        Paragraph(
            "How to cite: INDmoney SIP Discovery Engine, AI Evidence Log, October 2026. "
            "Signal IDs are stable within this snapshot; re-extraction can change them. "
            "The full machine-readable exports are data/exports/ai_evidence_log.csv and ai_evidence_log.jsonl.",
            styles["Small"],
        )
    )
    doc.build(story)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/exports")
    parser.add_argument("--pdf", default="deliverables/AI_Evidence_Log.pdf")
    parser.add_argument("--limit-per-theme", type=int, default=25)
    args = parser.parse_args()

    with get_session() as session:
        signals, documents = signals_frame(session)
        if signals.empty:
            print("No current signals. Run extraction first.")
            return
        documents = document_outcomes(signals, documents)
        summary = theme_summary(signals, documents)

    frame = build_evidence_frame(signals, summary)
    output_dir = Path(args.output)
    write_csv_jsonl(frame, output_dir)
    pdf_path = Path(args.pdf)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    build_pdf(frame, summary, pdf_path, limit_per_theme=args.limit_per_theme)
    print(f"Wrote {len(frame):,} evidence rows to {output_dir}")
    print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    main()
