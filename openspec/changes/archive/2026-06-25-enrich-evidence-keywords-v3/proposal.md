## Why

After `enrich-evidence-keywords-v2` was applied, the pipeline output still classifies 78/100 sample rows as `HOLD` even though only 27 of those rows have a true `HOLD` label. The remaining 51 are false-HOLDs: 27 UP-labelled and 24 DOWN-labelled sentences that the V2 keyword dictionary still missed because their language is softer and shorter than the V2 keyword vocabulary was tuned for.

Examples of the residual false-HOLDs that V3 needs to cover:

- UP: *Google expands Gemini features for enterprise productivity customers* — `expands`
- UP: *Meta reports stronger advertiser retention among small businesses* — `stronger` (not the longer `stronger than expected`)
- UP: *Google announces a cloud margin improvement program* — `improvement`
- DOWN: *Google warns that cloud capacity constraints may limit near term sales* — covered by V2's `warns that`, but the short `warns` is added as defence-in-depth
- DOWN: *Apple reports weaker Mac shipments in a supply chain channel check* — `weaker`
- DOWN: *Google delays a planned cloud region because of permitting issues* — `permitting`
- DOWN: *Amazon reports a temporary outage in a major AWS region* — `outage in` (V2 has `outage` but it would also match the UP sentence "Amazon Web Services launches new cost efficient AI chips" if broadened)

This change extends the V2 dictionary with a third wave of keywords that recover most of the residual false-HOLDs. It is **backward-compatible** (V1 and V2 keywords are retained verbatim, the rule-based algorithm and the overlap-resolution rules are unchanged) and **rule-based, deterministic** — no LLM, no FinBERT, no transformer, no network call. Every V3 entry has been checked against `data/sample_dataset.csv` for false-positives on the opposite-direction class and on the HOLD class.

## What Changes

- Extend `EvidenceExtractor.POSITIVE_KEYWORDS` in `src/evidence_extractor.py` with 21 V3 entries.
- Extend `EvidenceExtractor.NEGATIVE_KEYWORDS` in `src/evidence_extractor.py` with 16 V3 entries.
- Update the V2 dictionary assertions in `tests/test_evidence_extractor.py` (`test_positive_keywords_match_spec_vocabulary`, `test_negative_keywords_match_spec_vocabulary`) to match the V3 lists.
- Add 9 new unit tests that pin V3 behaviour on real sample sentences (3 UP, 4 DOWN, 2 HOLD regression).
- Add a `Version 3 Keyword Dictionary` section and a new `V3 keyword coverage` requirement to the delta spec, with normative scenarios and an extra acceptance criterion.

## Capabilities

### Modified Capabilities

- `evidence-extractor`: extend the Version 2 keyword dictionary with V3 phrases; keep V1, V2 entries verbatim. The delta spec adds a `V3 keyword coverage` requirement; the V1 and V2 requirements remain normative.

## Impact

- `src/evidence_extractor.py` (V3 keyword constants only — algorithm and helper signatures unchanged).
- `tests/test_evidence_extractor.py` (V3 dictionary assertions + 9 new tests on real sample sentences).
- `openspec/changes/enrich-evidence-keywords-v3/specs/evidence-extractor/spec.md` (delta spec with V3 vocabulary, V3 coverage requirement, V3 acceptance criterion).
- Regenerated `outputs/prediction_results.csv`, `outputs/evidence_results.csv`, `outputs/faithfulness_results.csv`, `outputs/temporal_leakage_results.csv` (run `python -m src.pipeline` after the source edit).
- **No changes** to `src/__init__.py` (re-export already uses `*`), `src/evidence_selector.py`, `src/forecast_model.py`, `src/faithfulness_evaluator.py`, `src/faithfulness_metrics.py`, `src/pipeline.py`, `src/schema.py`, or any file under `src/dashboard/` — they import the keyword constants by name.
- **No external dependencies, no model downloads, no GPU, no network access** required at runtime.