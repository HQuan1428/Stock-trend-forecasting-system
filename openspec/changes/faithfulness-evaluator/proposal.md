## Why

The Faithful Evidence-Centric Financial News Forecasting pipeline now produces a `ForecastResult` (a `UP` / `DOWN` / `HOLD` prediction with cited `pro_evidence` / `counter_evidence` and a confidence) but has no module that asks the central research question: **"When the model cites evidence for its prediction, does that evidence actually influence the prediction?"** Without this evaluation step, the prototype can show predictions and citations side-by-side, but it cannot distinguish a prediction that is genuinely *driven* by its cited evidence from one that just *mentions* the evidence decoratively. The Faithfulness Evaluator is the missing module that turns a `ForecastResult` into a FaithfulnessReport with three required metrics (Temporal Validity, Evidence Support, Confidence Drop), an optional composite `faithfulness_score`, and a readable verdict for the Visualization Dashboard.

## What Changes

- Add a new module `src/faithfulness_metrics.py` exposing pure metric functions: `calculate_prediction_temporal_validity`, `calculate_dataset_temporal_validity`, `evidence_support_score`, `calculate_evidence_support`, `calculate_confidence_drop`, `calculate_faithfulness_score`, and `classify_faithfulness`.
- Add a new module `src/faithfulness_evaluator.py` exposing a `FaithfulnessEvaluator` class with an `evaluate(original_input, original_result, ablation_strategy="remove_cited_pro_evidence") -> FaithfulnessReport` method, plus a `FaithfulnessEvaluatorError(ValueError)` for unrecoverable input problems.
- Define an `FaithfulnessEvaluator.ABLATION_STRATEGIES` constant with V1 values: `remove_cited_pro_evidence` and `remove_all_cited_evidence`. The default is `remove_cited_pro_evidence`.
- Define a `VERDICTS` constant with the six required verdict labels: `invalid_temporal_leakage`, `unsupported_evidence`, `strong_faithful_candidate`, `moderate_faithful_candidate`, `weak_faithful_candidate`, `decorative_explanation_risk`.
- Define the `FaithfulnessReport` dict schema (the V1 contract returned by `evaluate`) with `temporal_validity`, `evidence_support`, `confidence_drop`, `confidence_after_removal`, `prediction_after_removal`, `faithfulness_score`, `verdict`, `temporal_warnings`, `support_warnings`, `ablation_warnings`, and `per_evidence_results` — all keys always present, lists/dicts empty rather than `null` when there is nothing to report.
- Define a `FaithfulnessEvaluator.evaluate_batch(reports, *, output_csv_path="outputs/faithfulness_results.csv", output_json_path=None) -> List[dict]` helper that writes a per-row scalar CSV suitable for the Visualization Dashboard, plus a JSON sibling for full-fidelity inspection.
- Define the required CSV column list (`FaithfulnessEvaluator.CSV_COLUMNS`) as a module-level constant so downstream modules import the single source of truth.
- Re-export the public API (`FaithfulnessEvaluator`, `FaithfulnessEvaluatorError`, `FaithfulnessReport`, `VERDICTS`, `FaithfulnessEvaluator.ABLATION_STRATEGIES`, `FaithfulnessEvaluator.CSV_COLUMNS`, `FaithfulnessEvaluator.CSV_DEFAULT_PATH`, `FaithfulnessEvaluator.JSON_DEFAULT_PATH`, plus the pure metric functions) from `src/__init__.py`.
- The module MUST NOT re-extract evidence from raw news text, MUST NOT call any LLM / FinBERT / transformer / logistic regression / deep-learning model / external API, and MUST NOT consult price data. It is a deterministic, traceable function of the `ForecastResult` it is given plus a single re-invocation of the Forecast Model on the ablated input.
- The composite `faithfulness_score` MUST be documented as a V1 prototype heuristic, not a scientifically validated metric. The `confidence_drop` value is the primary signal.
- The evaluator MUST use the existing `src.forecast_model.predict` and `src.forecast_model.ForecastModel.predict_without_evidence` for ablation; it MUST NOT duplicate the prediction algorithm.

## Capabilities

### New Capabilities

- `faithfulness-evaluation`: Rule-based evaluation of a `ForecastResult` that returns a `FaithfulnessReport` with `temporal_validity`, `evidence_support`, `confidence_drop`, an optional composite `faithfulness_score`, a readable `verdict`, and a `per_evidence_results` breakdown. Supports `remove_cited_pro_evidence` and `remove_all_cited_evidence` ablation strategies, batch CSV/JSON export, and a small fixed set of `VERDICTS`. The evaluator is deterministic, side-effect-free in single-evaluation mode, and never invokes any LLM, FinBERT, transformer model, or external API.

### Modified Capabilities

_None._ This change introduces a new capability. The Temporal Retriever, Evidence Extractor, Evidence Selector, and Forecast Model specs are unaffected. The Faithfulness Evaluator consumes the Forecast Model's output and re-invokes it for ablation; it does not change the Forecast Model's contract. Once `forecast-model-basic` is archived, its `forecasting` capability spec will be the stable contract; no delta is required.

## Impact

- New code areas: `src/faithfulness_metrics.py` (pure functions, no IO) and `src/faithfulness_evaluator.py` (the `FaithfulnessEvaluator` class and `FaithfulnessEvaluator.evaluate_batch` helper), re-exported from `src/__init__.py`.
- New spec area: `openspec/changes/faithfulness-evaluator/specs/faithfulness-evaluation/spec.md`; once archived, `openspec/specs/faithfulness-evaluation/spec.md`.
- New tests: `tests/test_faithfulness_metrics.py` (pure function tests) and `tests/test_faithfulness_evaluator.py` (integration tests wiring `ForecastModel.predict` → `evaluate` → `FaithfulnessEvaluator.evaluate_batch`).
- New sample data: `samples/faithfulness_evaluator/` with at least four `_input.json` / `_expected.json` pairs (strong faithful, decorative explanation risk, temporal leakage, unsupported evidence). A parametrized regression test asserts byte-equality on every fixture pair.
- New output: `outputs/faithfulness_results.csv` (per-row scalar fields written by `FaithfulnessEvaluator.evaluate_batch`). The full per-record reports (including `per_evidence_results` lists) are emitted as `outputs/faithfulness_results.json` for the dashboard.
- Downstream consumers: the Visualization Dashboard imports `FaithfulnessEvaluator.evaluate_batch` and the `FaithfulnessEvaluator.CSV_COLUMNS` constant. The Faithfulness Evaluator is the only documented caller of `ForecastModel.predict_without_evidence`.
- Pipeline contract: the Faithfulness Evaluator is the final analytical stage. It MUST NOT re-extract evidence, re-classify evidence, or replace the Forecast Model. It MUST be able to run on any `ForecastResult` produced by the existing rule-based Forecast Model, including results from `ForecastModel.predict_batch`.
- No external dependencies, no model downloads, no GPU, no network access required at runtime.
- **Not in scope:** trading advice, scientifically validated faithfulness metrics, learned attention-based attribution, LLM-based counterfactual reasoning, multi-ticker or multi-horizon evaluation. The V1 composite score is a dashboard heuristic, not a final metric.
