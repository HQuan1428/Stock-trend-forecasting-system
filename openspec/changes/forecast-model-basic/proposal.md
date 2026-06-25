## Why

The Faithful Evidence-Centric Financial News Forecasting pipeline already produces selected, valid evidence (Temporal Retriever → Evidence Extractor → Evidence Selector) but has no module that turns that evidence into a stock-movement prediction. Version 1 cannot ship a working end-to-end demo, a confusion-matrix evaluation, or a Faithfulness Evaluator without a deterministic, traceable prediction step. The Forecast Model v1 must be small, rule-based, and faithful to its inputs: every prediction must be derivable from the evidence it cites, and every cited evidence must be removable so the Faithfulness Evaluator can compute `confidence_drop`.

## What Changes

- Add a new module `src/forecast_model.py` exposing `predict(input_data) -> ForecastResult`, `predict_batch(records) -> list[ForecastResult]`, and `predict_without_evidence(input_data, removed_evidence_ids) -> ForecastResult`.
- Implement a deterministic, rule-based voting algorithm: `expected_direction = UP` → vote `+1`, `DOWN` → vote `-1`, `HOLD` → vote `0`. `score = positive_count - negative_count`. `prediction = UP` if `score > 0`, `DOWN` if `score < 0`, `HOLD` if `score == 0`.
- Implement a stable confidence formula `confidence = 0.5 + min(abs(score) * 0.1, 0.45)`, clamped to `[0.5, 0.95]`. No directional evidence → `prediction = HOLD`, `confidence = 0.5`. Neutral evidence MUST NOT increase confidence.
- Compute `evidence_strength = abs(score) / directional_evidence_count` (zero when no directional evidence) and `conflict_ratio = min(positive_count, negative_count) / max(positive_count + negative_count, 1)`.
- Build `pro_evidence` (matching-direction items), `counter_evidence` (opposing-direction items), `rationale` (template-based, NOT LLM-generated), and `warnings` (a list of structured warning codes such as `TEMPORAL_LEAKAGE_BLOCKED`).
- Defensively validate evidence timestamps: any item with `news_time > forecast_time` is excluded from scoring and triggers a `TEMPORAL_LEAKAGE_BLOCKED` warning (defense-in-depth; the Temporal Retriever normally prevents this).
- Deduplicate evidence with the same `evidence_id` (kept the first occurrence, subsequent ones reported in `warnings` as `DUPLICATE_EVIDENCE_ID`); evidence with missing or invalid `expected_direction` is ignored under the default `strict = False` behavior, with an `INVALID_EVIDENCE` warning emitted.
- Emit a per-prediction `ForecastResult` dict including `prediction`, `confidence`, `score`, `positive_count`, `negative_count`, `neutral_count`, `total_evidence`, `directional_evidence_count`, `evidence_strength`, `conflict_ratio`, `pro_evidence`, `counter_evidence`, `up_evidence`, `down_evidence`, `neutral_evidence`, `rationale`, `warnings`, `model_version`, and the echoed `sample_id`, `ticker`, `forecast_time`.
- Persist a CSV `outputs/prediction_results.csv` containing the per-row scalar fields (one row per input sample) so the Faithfulness Evaluator and dashboard can compute accuracy and confusion matrices.
- Provide an evaluation helper `compute_accuracy_and_confusion(results, label_key="label") -> dict` that returns `accuracy`, `confusion_matrix` (3×3 over `UP/DOWN/HOLD`), `per_class`, and `n_samples` for batch evaluation.
- Add acceptance criteria and unit tests covering the nine scenarios (UP-dominant, DOWN-dominant, balanced HOLD, neutral-only HOLD, empty HOLD, future-evidence blocking, predict_without_evidence for confidence_drop, template-based rationale, and batch evaluation).
- Re-export the public API from `src/__init__.py` so downstream modules import from the package root.

## Capabilities

### New Capabilities

- `forecasting`: Rule-based prediction of stock movement (UP / DOWN / HOLD) from selected evidence. Emits `prediction`, `confidence`, `score`, evidence counts, `evidence_strength`, `conflict_ratio`, `pro_evidence`, `counter_evidence`, `rationale`, `warnings`, and `model_version`. Supports `predict`, `predict_batch`, and `predict_without_evidence` (the last is required by the Faithfulness Evaluator for `confidence_drop`). Version 1 does not use LLM, FinBERT, logistic regression, deep learning, external APIs, or price features.

### Modified Capabilities

_None._ This change introduces a new capability. The Temporal Retriever, Evidence Extractor, and Evidence Selector specs are unaffected; the Forecast Model only consumes the Selector's selected evidence and never re-implements their responsibilities.

## Impact

- New code area: `src/forecast_model.py` (single-file module), re-exported from `src/__init__.py`.
- New spec area: `openspec/changes/forecast-model-basic/specs/forecasting/spec.md`; once archived, `openspec/specs/forecasting/spec.md`.
- New tests: `tests/test_forecast_model.py` covering all nine acceptance scenarios (UP-dominant, DOWN-dominant, balanced HOLD, neutral-only HOLD, empty HOLD, future-evidence blocking, predict_without_evidence, template-based rationale, batch evaluation), plus defensive checks (duplicate `evidence_id`, invalid `expected_direction`, malformed `news_time`).
- New sample data: `samples/forecast_model/` with at least four `_input.json` / `_expected.json` pairs (UP-dominant, DOWN-dominant, balanced HOLD, empty HOLD, future-evidence). Used as golden fixtures for regression testing.
- New output: `outputs/prediction_results.csv` (per-row scalar fields) is regenerated by `predict_batch`. The full per-result objects (including `pro_evidence` / `counter_evidence` lists) are emitted as `outputs/prediction_results.json` for the dashboard.
- Downstream consumers: the Faithfulness Evaluator (later change) imports `predict_without_evidence` and the rationale template constants; the Visualization Dashboard imports `predict_batch` and the evaluation helper. The Forecast Model MUST NOT import from those modules.
- Pipeline contract: the Temporal Retriever owns temporal validity (defense-in-depth here); the Evidence Extractor owns per-phrase polarity; the Evidence Selector owns pro/counter/neutral classification. The Forecast Model only consumes evidence already validated by the upstream pipeline; it MUST NOT re-extract phrases from raw news text or re-classify evidence.
- No external dependencies, no model downloads, no GPU, no network access required at runtime.
