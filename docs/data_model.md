# Data model

## Entity map

```
sources 1 ─── * documents 1 ─── * signals * ─── * themes
                                  │
                                  ├── * evidence
                                  └── * theme_signals

runs 1 ─── * signals
runs 1 ─── * validation_results

documents 1 ─── * gold_set
opportunities (standalone, references theme IDs)
```

## Tables

### `sources`

One row per collection source (Play Store, App Store, Reddit, YouTube, forum).

| Column | Type | Notes |
|---|---|---|
| `id` | integer | primary key |
| `name` | string | unique, e.g. `play_store:INDmoney` |
| `kind` | string | `play_store`, `app_store`, `reddit`, `youtube`, `forum` |
| `base_url` | string | optional |
| `created_at` | datetime | |

### `documents`

One row per public document (review, post, comment, forum answer).

| Column | Type | Notes |
|---|---|---|
| `id` | integer | primary key |
| `source_id` | integer | FK to `sources` |
| `external_id` | string | source-specific ID; unique with `source_id` |
| `url` | string | public link |
| `author_hash` | string | SHA-256; no raw usernames |
| `published_at` | datetime | source timestamp |
| `fetched_at` | datetime | collection timestamp |
| `language` | string | `en`, `hi`, etc. |
| `raw_text` | text | original text |
| `normalized_text` | text | cleaned text for coding |
| `metadata` | JSON | score, app, subreddit, video, etc. |
| `content_hash` | string | SHA-256 of normalized text |
| `dedupe_group` | string | near-duplicate group |
| `is_relevant` | boolean | SIP/MF relevance |
| `relevance_score` | float | optional |

### `runs`

One row per extraction, validation, or analysis run.

| Column | Type | Notes |
|---|---|---|
| `id` | integer | primary key |
| `run_type` | string | `extract`, `validate`, `theme`, `quantify` |
| `provider` | string | `gemini`, `groq` |
| `model_id` | string | exact model |
| `model_version` | string | provider version if available |
| `prompt_version` | string | codebook/prompt version |
| `started_at` | datetime | |
| `finished_at` | datetime | |
| `status` | string | `running`, `done`, `failed` |
| `stats` | JSON | counts, tokens, errors |

### `signals`

The atomic unit of evidence. One row per distinct claim in a document.

| Column | Type | Notes |
|---|---|---|
| `id` | integer | primary key |
| `document_id` | integer | FK |
| `run_id` | integer | FK |
| `journey_stage` | string | codebook |
| `triggers` | JSON | array |
| `behaviors` | JSON | array |
| `emotions` | JSON | array |
| `expectations` | JSON | array |
| `help_seeking` | JSON | array |
| `outcome` | string | codebook |
| `segment` | JSON | segment cues |
| `quote` | text | exact substring |
| `quote_start` | integer | character offset |
| `quote_end` | integer | character offset |
| `confidence` | string | `high`, `medium`, `low` |
| `raw` | JSON | full model response |

### `themes`

| Column | Type | Notes |
|---|---|---|
| `id` | integer | primary key |
| `name` | string | human name |
| `slug` | string | unique machine name |
| `definition` | text | inclusion/exclusion rules |
| `parent_id` | integer | optional hierarchy |
| `created_at` | datetime | |

### `theme_signals`

Many-to-many mapping between themes and signals, with confidence.

### `opportunities`

| Column | Type | Notes |
|---|---|---|
| `id` | integer | primary key |
| `name` | string | |
| `description` | text | |
| `theme_ids` | JSON | linked themes |
| `reach` | float | 0–1 |
| `severity` | float | 1–5 |
| `evidence_strength` | float | 1–5 |
| `expected_lift` | float | relative lift assumption |
| `effort` | float | 1–5 |
| `score` | float | computed |
| `metric_bridge` | JSON | assumptions and range |
| `guardrail_pass` | boolean | no fund advice, no fear/FOMO/urgency |

### `evidence`

One row per quote used in an insight card. Links an insight to a signal and a
public source.

### `gold_set`

Human-labelled documents used to validate the extractor.

### `validation_results`

Metrics from validation runs: precision, recall, Cohen's kappa, quote
verification rate, model-swap agreement.

## Design choices

- **Signals are multi-label.** A post can be about a payment failure, shame, and
  a stop decision at the same time.
- **Quotes are verified.** The database stores character offsets; the pipeline
  rejects quotes that are not exact substrings.
- **Runs are versioned.** Every signal points to the model, prompt, and run that
  produced it.
- **No raw usernames.** Author identity is hashed at ingestion.
- **Public data only.** No DMs, private groups, or internal analytics.
