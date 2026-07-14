## Why

The Faithful Evidence-Centric Financial News Forecasting pipeline needs a deterministic, rule-based Evidence Extractor to convert validated news text into structured evidence phrases. Without it, downstream modules (Evidence Selector, Forecast Model, Faithfulness Evaluator) cannot reason about which exact phrases support or contradict a prediction, and faithfulness evaluation becomes impossible. Version 1 must be simple, deterministic, and testable so that counterevidence coverage and auditability can be built on a stable foundation.

## What Changes

- Add a new `evidence-extractor` module that ingests news items from the Temporal Retriever and produces a structured evidence list per news item.
- Define a Version 1 keyword dictionary for positive and negative sentiment-bearing phrases (no LLM, no FinBERT, no transformer models).
- Define deterministic evidence IDs, polarity, expected direction, character offsets, and `support_score` for every match.
- Preserve all matched positive and negative evidence so the downstream pipeline can identify both pro evidence and counterevidence.
- Emit a per-news summary (positive/negative/neutral counts, mixed-evidence flag) and an optional deterministic `primary_evidence_id`.
- Add acceptance criteria and unit tests covering positive-only, negative-only, neutral, mixed, and case-insensitive scenarios.
- Document out-of-scope items (LLM extraction, FinBERT, NER, prediction, temporal filtering, trading advice).

## Capabilities

### New Capabilities
- `evidence-extractor`: Rule-based extraction of evidence phrases from a single news item, including keyword matching, polarity classification, evidence IDs, summary counts, and primary evidence selection.

### Modified Capabilities
- *(none — this change introduces a new capability; no existing spec-level requirements change.)*

## Impact

- New code area: `src/evidence_extractor/` (or equivalent module path decided at implementation time), including the keyword dictionary, single-item and batch extraction functions, and tests.
- New spec area: `openspec/changes/evidence-extractor/specs/evidence-extractor/spec.md` (this change) and, once archived, `openspec/specs/evidence-extractor/spec.md`.
- Downstream consumers: Evidence Selector, Forecast Model, Faithfulness Evaluator, Visualization Dashboard. They will consume the per-news result object defined in this change.
- Pipeline contract: The Temporal Retriever is responsible for temporal validity; the Evidence Extractor must not filter future news.
- No external dependencies, no model downloads, no GPU, no network access required at runtime.
