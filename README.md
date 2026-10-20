# INDmoney SIP Discovery Engine

A public-evidence discovery engine for understanding why first-time Indian
mutual-fund investors stop their SIPs before month 12, and which retention
interventions are worth building first.

The engine collects public conversations, extracts structured behavioural
signals with a free-tier LLM, grounds every signal in a verified quote, then
computes prevalence, lapse associations, segment cuts, and opportunity scores
in Python/SQL. The model does not count, rank, or invent themes; those steps are
deterministic and reproducible.

## Deliverables

| Deliverable | Path |
|---|---|
| Case write-up (PDF) | `deliverables/INDmoney_SIP_Case_Writeup.pdf` |
| Discovery deck (PPTX) | `deliverables/INDmoney_SIP_Discovery_Deck.pptx` |
| Discovery deck (PDF) | `deliverables/INDmoney_SIP_Discovery_Deck.pdf` |
| PRD + retention appendix (PDF) | `deliverables/INDmoney_SIP_Discovery_PRD.pdf` |
| AI Evidence Log (PDF) | `deliverables/AI_Evidence_Log.pdf` |
| AI Evidence Log (CSV/JSONL) | `data/exports/ai_evidence_log.csv`, `data/exports/ai_evidence_log.jsonl` |
| Validation report | `data/exports/final_qa_report.json` |
| Red-team report | `data/exports/red_team_report.json` |
| Model-swap agreement | `data/exports/model_swap_agreement.json` |
| Charts | `deliverables/charts/` |

## How it works

```
Public sources                  Deterministic layer                 Decision layer
--------------                  -------------------                 --------------
Play Store  ┐                   normalize + dedupe                  theme prevalence
App Store   │                   keyword + strict filters            lapse associations
Reddit      ├──> SQLite corpus ──> LLM extraction ──> grounding ──> segment/stage cuts
YouTube     │                   (quote-first)       (rules)         opportunity scores
ValuePickr  │                                                        │
TradingQ&A  ┘                                                        ├─> dashboard
                                                                    ├─> evidence log
                                                                    └─> deck / PRD
```

1. **Collect** public reviews, posts, comments, and forum threads from six
   sources. Competitor app reviews are included to learn category-wide
   friction; INDmoney-specific views remain filterable.
2. **Filter** broadly for SIP/mutual-fund relevance, then strictly for
   first-person SIP/MF experience. Strict candidates are the extraction pool.
3. **Extract** up to three signals per document with a versioned prompt. The
   model must return a contiguous source quote before assigning any code.
4. **Ground** every code deterministically: exact quote verification, keyword
   support, first-person action checks, negation handling, attempt-vs-completed
   actions, payment-mechanism exclusions, temporary-pause normalization, and
   segment-quote verification. Unsupported codes are dropped.
5. **Quantify** themes, outcomes, journey stages, segments, sources, and
   opportunity scores. Themes with no resolved outcomes are shown as `n/a` and
   receive a modest friction prior, flagged in the UI and documents.
6. **Validate** with a 200-item stratified evaluation set, a second-model swap,
   Cohen's kappa, a 30-item human-review queue, and a red-team suite that
   includes a live prompt-injection check.

## Setup

Requirements: Python 3.11+, Windows PowerShell, and a free-tier Gemini API key.
A Groq key is optional for failover and a secondary robustness check.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Set keys without pasting them into chat or source files:

```powershell
.\setup-key.bat
.\check-keys.bat
```

`.env` is gitignored. The setup script prints only whether a key is set and its
length. Keys are never written to logs or deliverables.

## Reproduce the pipeline

Run these from the project root with the virtual environment active.

```powershell
# 1. Collect the public corpus (or use the existing data/indmoney.db)
python scripts/collect_sample.py --source all --quick

# 2. Extract signals. Resume is safe; completed documents are skipped.
python scripts/extract_signals.py --source reddit --limit 400 --batch-size 6 --resume
python scripts/extract_signals.py --source forums --limit 250 --batch-size 6 --resume
python scripts/extract_signals.py --source youtube --limit 100 --batch-size 6 --resume
python scripts/extract_signals.py --source app_store --limit 500 --batch-size 8 --resume
python scripts/extract_signals.py --source play_store --limit 800 --batch-size 10 --resume

# 3. Re-apply deterministic grounding after prompt or rule changes
python scripts/reground_signals.py

# 4. Quantify and export analysis tables
python scripts/analyze.py --no-db

# 5. Build charts and the AI Evidence Log
python scripts\build_charts.py
python scripts\export_evidence_log.py

# 6. Explore the evidence
streamlit run dashboard/app.py
```

The dashboard has overview, theme deep dives, signal explorer, segment/stage
views, method/guardrails, filters, and CSV download. It is read-only.

## Validation

```powershell
# 200-item stratified evaluation set + 30-item human-review queue
python scripts\build_gold_set.py --size 200

# Quota-sized second-model subset: all 80 resolved outcomes + 20 controls
python scripts\build_swap_subset.py

# Gemini 3.1 Flash-Lite: a prior-generation Lite model for a clean 100-item swap.
# Gemini 3.8 Flash was attempted first but its 20-request/day free-tier cap
# stopped at 36 valid items; that output is retained for audit, not cited.
python scripts\model_swap.py --gold data/exports/gold_set_swap_100.csv `
  --provider gemini --model gemini/gemini-3.1-flash-lite `
  --batch-size 8 --limit 100 --max-tokens 10000 --timeout 180 --sleep 5 --resume `
  --output data/exports/model_swap_gemini31lite_100.jsonl

# Cohen's kappa, bootstrap CI, and disagreement export
python scripts\compare_model_swap.py `
  --gold data/exports/gold_set_swap_100.csv `
  --second data/exports/model_swap_gemini31lite_100.jsonl `
  --output data/exports

# Deterministic red team + optional end-to-end prompt-injection call
python scripts\red_team.py --llm
```

Groq's free tier is capped at 8,000 tokens per minute. If you want a secondary
Groq check, use `--batch-size 2 --limit 30` and a separate output file.

`gold_set_200.csv` contains the primary-model coding and blank human-review
columns. `gold_set_review_30.csv` is the prioritised human-adjudication queue.
`gold_set_swap_100.csv` is the quota-sized second-model subset: all 80 resolved
outcomes plus 20 signal/no-signal controls.
Kappa in the model-swap report is **agreement with the primary extraction**, not
human truth; the documents report that distinction explicitly. The current
100-item swap (Gemini 3.1 Flash-Lite vs the primary Gemini 3.5 Flash-Lite) gives
relevance kappa **0.81** (95% CI 0.50-1.00), outcome kappa **0.94** (0.86-1.00,
n=72), and theme kappa **0.60** (0.44-0.74, n=55); mean behaviour Jaccard is
**0.78**. Gemini 3.8 Flash was tried first but stopped at 36 items on its
20-request daily free-tier cap; that pilot is retained for audit and is not
cited. The red-team report currently passes **15/15** tests, including a live
end-to-end prompt-injection call against the bulk model.

## Build the written deliverables

```powershell
python scripts\build_deck.py
powershell -ExecutionPolicy Bypass -File scripts\export_deck_pdf.ps1

python scripts\build_prd.py
python scripts\build_case_writeup.py
python scripts\final_qa.py
```

PPTX-to-PDF export uses PowerPoint COM (`SaveAs(..., 32)`) because LibreOffice
is not available on this machine. On a machine without PowerPoint, keep the
PPTX and render the PDF from the same content generator.

## Repository layout

```
config/                 model routing, source config, codebook
src/collectors/         Play Store, App Store, Reddit, YouTube, Discourse
src/pipeline/           extraction, LLM client, quote verification
src/grounding.py        deterministic signal grounding rules
src/analysis.py         themes, outcomes, segments, opportunity scoring
src/reporting.py        fact sheet, chart helpers, validation loader
scripts/                collection, extraction, analysis, exports, build, QA
prompts/                versioned extraction prompts
dashboard/app.py        Streamlit evidence explorer
data/indmoney.db        SQLite corpus and signal store
deliverables/           PDFs, PPTX, charts
```

## Guardrails

- **Quote-first extraction.** No code without a source quote. Quotes are exact
  substrings after normalization; fabricated or over-long quotes are rejected.
- **Deterministic counting.** The LLM never computes prevalence, lapse rates,
  opportunity scores, or segment sizes.
- **First-person only.** Third-person stories ("my friend stopped") and
  hypotheticals ("if I stop") are rejected by grounding.
- **Payment mechanisms are not voluntary stops.** A failed debit or mandate
  issue keeps `outcome=stopped` but is coded as `payment_failure` /
  `mandate_issue`, not `stopped_sip`.
- **Temporary pauses are normalized.** "Paused for three months and restarted"
  becomes `paused_sip` + `restarted_sip`, `outcome=returned`, not a permanent
  stop.
- **No resolved outcome, no fake rate.** Themes with no resolved outcomes show
  `n/a`; their opportunity score uses a flagged 0.35 friction prior.
- **No specific funds or stocks.** Recommendations are about mechanics,
  communication, and product flows.
- **No fear, FOMO, or urgency.** Retention copy is framed around control,
  affordability, and goal progress.
- **Untrusted input.** Document text is sanitized and treated as data, never as
  instructions.

## Known limitations

- Public posts are self-selected; people with problems are more likely to post.
- Self-reported outcomes are not the product's 12-month metric.
- Theme-lapse associations are correlational, not causal.
- App reviews are short and often lack context; narrative sources carry more
  explanatory weight.
- Segment cues are sparse and self-reported.
- The corpus spans 2014–2026; platform and market conditions change.
- Kappa is inter-model agreement, not human ground truth. The 30-item review
  queue is a seed for human adjudication, not a completed gold standard.
