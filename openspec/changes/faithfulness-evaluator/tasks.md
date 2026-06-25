# Tasks: Faithfulness Evaluator (Version 1)

Tasks are grouped by dependency order. Each task is small enough to complete in one session and produces a verifiable artifact. Tasks intentionally do NOT include source-code lines — they describe the artifact to be produced, not the exact text to type.

## 1. Module Skeleton and Constants

- [x] 1.1 Create `src/faithfulness_metrics.py` with module docstring documenting the contract: pure metric functions, no IO, no LLM, no network, deterministic. Mirror the docstring style of `src/forecast_model.py`.
- [x] 1.2 Define a typed `FaithfulnessEvaluatorError(ValueError)` exception class in `src/faithfulness_evaluator.py` for unrecoverable input problems (e.g., missing `prediction`, invalid `ablation_strategy`).
- [x] 1.3 Define module-level constants in `src/faithfulness_evaluator.py`:
  - `VERDICTS = frozenset({"invalid_temporal_leakage", "unsupported_evidence", "strong_faithful_candidate", "moderate_faithful_candidate", "weak_faithful_candidate", "decorative_explanation_risk"})`
  - `ABLATION_STRATEGIES = ("remove_cited_pro_evidence", "remove_all_cited_evidence")`
  - `CSV_COLUMNS = ("ticker", "forecast_time", "prediction", "original_confidence", "prediction_after_removal", "confidence_after_removal", "confidence_drop", "temporal_validity", "evidence_support", "faithfulness_score", "verdict", "warnings")`
  - `CSV_DEFAULT_PATH = "outputs/faithfulness_results.csv"`
  - `JSON_DEFAULT_PATH = "outputs/faithfulness_results.json"`
- [x] 1.4 Re-export the public surface from `src/__init__.py`: `FaithfulnessEvaluator`, `FaithfulnessEvaluatorError`, the seven metric functions, and the four constants from task 1.3.
- [x] 1.5 Add a `_parse_news_time` helper (local to `src/faithfulness_metrics.py` or `src/faithfulness_evaluator.py`) that reuses `src.retriever._parse_datetime` and `src.retriever._normalize_to_utc` for UTC-naive consistency with the rest of the pipeline.

## 2. Pure Metric Helpers — Temporal Validity

- [x] 2.1 Implement `calculate_prediction_temporal_validity(cited_evidence, forecast_time) -> float`. Empty list → `1.0`. Any item with parsed `news_time > forecast_time` → `0.0`. Equal timestamps are valid (strict inequality).
- [x] 2.2 Implement a private helper `_collect_temporal_warnings(cited_evidence, forecast_time) -> List[str]` that returns one warning string per offending item (`"TEMPORAL_LEAKAGE: evidence_id=<X>, news_time=<T>, forecast_time=<F>"`) and one warning per malformed timestamp (`"MALFORMED_NEWS_TIME: evidence_id=<X>"`).
- [x] 2.3 Implement `calculate_dataset_temporal_validity(records) -> float` over a list of `{news_time, forecast_time}` dicts. Empty list → `1.0`. Otherwise `valid_count / total_count`.
- [x] 2.4 Add unit tests in `tests/test_faithfulness_metrics.py`: all-valid (1.0), one-future (0.0 + warning), empty cited (1.0), dataset empty (1.0), dataset with one future (`0.66...` for 2-of-3), `news_time == forecast_time` (valid).

## 3. Pure Metric Helpers — Evidence Support

- [x] 3.1 Implement `evidence_support_score(prediction, expected_direction) -> float`. Exact match → `1.0`. Either side HOLD → `0.5`. Opposite → `0.0`. Unknown `expected_direction` treated as HOLD (defensive default).
- [x] 3.2 Implement `calculate_evidence_support(prediction, cited_evidence) -> float`. Empty list → `1.0`. Otherwise mean of per-item scores.
- [x] 3.3 Implement a private helper `_collect_support_warnings(prediction, cited_evidence) -> List[str]` that returns one warning per item whose per-item score is `< 1.0`, formatted as `"UNSUPPORTED: evidence_id=<X>, expected_direction=<Y>, score=<S>"`.
- [x] 3.4 Add unit tests: DOWN/DOWN (1.0), UP/DOWN (0.0), UP/HOLD (0.5), HOLD/UP (0.5), DOWN/UP (0.0), HOLD/HOLD (1.0), empty (1.0), three-item average ((1+0+0.5)/3).

## 4. Pure Metric Helpers — Confidence Drop and Composite

- [x] 4.1 Implement `confidence_after_removal_for_original_class(original_prediction, reduced_prediction, reduced_confidence, reduced_class_confidences=None) -> float`. Class-confidences branch → `reduced_class_confidences[original_prediction]` when present. Same-prediction branch → `reduced_confidence`. Fallback → `0.0`.
- [x] 4.2 Implement `calculate_confidence_drop(original_confidence, original_prediction, reduced_prediction, reduced_confidence, reduced_class_confidences=None) -> float` as `original_confidence - confidence_after_removal_for_original_class(...)`. Signed; may be negative.
- [x] 4.3 Implement `calculate_faithfulness_score(temporal_validity, evidence_support, confidence_drop) -> float` as `0.35 * temporal_validity + 0.30 * evidence_support + 0.35 * min(max(confidence_drop, 0.0) / 0.30, 1.0)`.
- [x] 4.4 Add unit tests for task 4.2: large positive drop (0.25), near-zero drop (0.01), negative drop (-0.25), prediction flip with class confidences (uses class_confidences branch), prediction flip without class confidences (uses 0.0 fallback). Also test that `confidence_increased_after_removal` is included in `ablation_warnings` whenever drop < 0.

## 5. Pure Metric Helpers — Verdict Classifier

- [x] 5.1 Implement `classify_faithfulness(temporal_validity, evidence_support, confidence_drop, prediction, prediction_after_removal) -> str` following the documented seven-branch ordered cascade. Clamp `temporal_validity` and `evidence_support` to `[0.0, 1.0]` before branching.
- [x] 5.2 Add unit tests pinning each of the seven branches plus the clamp behavior (`temporal_validity = -0.1` → `invalid_temporal_leakage`; `evidence_support = 1.5` → treated as `1.0`).

## 6. Per-Evidence Results and Warning Helpers

- [x] 6.1 Implement `_build_per_evidence_results(prediction, cited_evidence, forecast_time) -> List[Dict[str, Any]]` that returns one dict per cited evidence item in `evidence_id` ascending order, with the keys `evidence_id`, `news_id`, `news_time`, `expected_direction`, `support_score`, `is_cited`, `temporal_warning`.
- [x] 6.2 Implement `_empty_per_evidence_results() -> List[Dict[str, Any]]` that returns `[]` for the empty-cited case.
- [x] 6.3 Add unit tests: per-evidence results are sorted by `evidence_id` ascending; the empty-cited case returns `[]`; a temporal-leakage item carries the warning string.

## 7. Ablation Logic

- [x] 7.1 Implement `_select_removed_evidence_ids(strategy, original_result, original_input) -> Tuple[List[str], List[str]]` that returns `(removed_evidence_ids, ablation_warnings)`. For `remove_cited_pro_evidence`, collect `pro_evidence` IDs. For `remove_all_cited_evidence`, collect `pro_evidence + counter_evidence` IDs.
- [x] 7.2 Implement `_expand_to_news_ids(removed_evidence_ids, original_input) -> Tuple[List[str], List[str]]` that maps each removed `evidence_id` to its `news_id`, dedupes, and returns the collapsed list plus the warnings. Document this in the warnings as `"COLLAPSED_BY_NEWS_ID: <news_id> (expanded from <evidence_id_list>)"`.
- [x] 7.3 Implement `_invoke_ablation(original_input, removed_evidence_ids) -> Tuple[Dict[str, Any], List[str]]` that calls `src.forecast_model.predict_without_evidence(original_input, removed_evidence_ids)` and catches `ForecastModelError` (appending `"FORECAST_MODEL_ERROR: <message>"` to warnings, returning a default `{"prediction": "HOLD", "confidence": 0.5}` result). The function MUST NOT raise.
- [x] 7.4 Add unit tests for: default strategy uses `pro_evidence`; explicit `remove_all_cited_evidence` uses both lists; news-id collapse produces the right warning; `ForecastModelError` is caught and the default HOLD result is returned.

## 8. FaithfulnessEvaluator Class

- [x] 8.1 Implement `FaithfulnessEvaluator.evaluate(original_input, original_result, *, ablation_strategy="remove_cited_pro_evidence") -> Dict[str, Any]` that:
  - Validates `original_input` is a dict, `original_result` is a dict, `ablation_strategy in ABLATION_STRATEGIES`, `prediction in VALID_PREDICTIONS`, `confidence` is numeric.
  - Raises `FaithfulnessEvaluatorError` on validation failure.
  - Calls the helpers from tasks 2–7 to build the report.
  - Returns the populated `FaithfulnessReport` dict (all keys present).
- [x] 8.2 Implement `_extract_cited_evidence(original_result) -> List[Dict[str, Any]]` with the documented fallback: `pro_evidence + counter_evidence` when present, else `cited_evidence`, else `[]`.
- [x] 8.3 Implement `_extract_forecast_time(original_input, original_result) -> str` with the documented fallback chain.
- [x] 8.4 Add unit tests for the class: raises on missing `prediction`; raises on invalid strategy; produces a fully populated report on a happy-path fixture.

## 9. evaluate_batch Helper and CSV/JSON Export

- [x] 9.1 Implement `_flatten_report_to_csv_row(report) -> Dict[str, Any]` that maps the report to the 12-column schema, JSON-encoding the concatenated `warnings` list into the `warnings` column.
- [x] 9.2 Implement `_write_csv(rows, output_csv_path) -> None` that writes the CSV with the `CSV_COLUMNS` header and one row per record.
- [x] 9.3 Implement `_write_json(reports, output_json_path) -> None` that writes the full per-record reports as JSON.
- [x] 9.4 Implement `evaluate_batch(reports, *, output_csv_path=None, output_json_path=None) -> List[Dict[str, Any]]` that:
  - Iterates `reports` in input order and calls `FaithfulnessEvaluator().evaluate(...)` on each.
  - Catches `FaithfulnessEvaluatorError` per record and replaces the row with `verdict = "unsupported_evidence"` and a `warnings` column starting with `"EVALUATION_ERROR: "`.
  - Returns a list of result reports in input order.
  - When `output_csv_path` is provided, writes the CSV. When `output_json_path` is provided, writes the JSON sibling.
- [x] 9.5 Add unit tests: batch returns one result per input report; CSV header matches `CSV_COLUMNS`; JSON contains the full reports; per-record error is captured without aborting the batch.

## 10. Module Integration and Re-exports

- [x] 10.1 Update `src/__init__.py` to re-export `FaithfulnessEvaluator`, `FaithfulnessEvaluatorError`, `calculate_prediction_temporal_validity`, `calculate_dataset_temporal_validity`, `evidence_support_score`, `calculate_evidence_support`, `calculate_confidence_drop`, `calculate_faithfulness_score`, `classify_faithfulness`, `VERDICTS`, `ABLATION_STRATEGIES`, `CSV_COLUMNS`, `CSV_DEFAULT_PATH`, `JSON_DEFAULT_PATH`.
- [x] 10.2 Verify there are no circular imports with `src/forecast_model.py`, `src/evidence_selector.py`, `src/evidence_extractor.py`, and `src/retriever.py`. The Faithfulness Evaluator imports `predict` and `predict_without_evidence` from `src.forecast_model` and `_parse_datetime` / `_normalize_to_utc` from `src.retriever`.
- [x] 10.3 Verify the package still imports cleanly: `python -c "import src; print(src.FaithfulnessEvaluator)"`.

## 11. Golden Fixtures

- [x] 11.1 Create `samples/faithfulness_evaluator/01_strong_faithful_input.json` and `_expected.json` (3 UP + 1 DOWN, prediction UP, ablation removes the 3 cited UP → prediction flips UP→DOWN, `confidence_drop = 0.7`, verdict `strong_faithful_candidate`).
- [x] 11.2 Create `samples/faithfulness_evaluator/02_decorative_input.json` and `_expected.json` (1 UP + 1 DOWN, prediction HOLD, ablation removes the UP item → still HOLD with confidence 0.5, `confidence_drop ≈ 0`, verdict `decorative_explanation_risk`).
- [x] 11.3 Create `samples/faithfulness_evaluator/03_temporal_leakage_input.json` and `_expected.json` (prediction UP, cited evidence includes one item with `news_time > forecast_time`, `temporal_validity = 0.0`, verdict `invalid_temporal_leakage`).
- [x] 11.4 Create `samples/faithfulness_evaluator/04_unsupported_input.json` and `_expected.json` (prediction UP, cited evidence all DOWN, `evidence_support = 0.0`, verdict `unsupported_evidence`).
- [x] 11.5 Add `samples/faithfulness_evaluator/README.md` describing the schema and the example coverage.
- [x] 11.6 Add a parametrized regression test in `tests/test_faithfulness_evaluator.py` (analogous to `test_golden_fixture_matches_forecast_model_output`) that asserts byte-equality on every fixture pair.

## 12. Unit Tests — Acceptance Scenarios from the Spec

- [x] 12.1 Scenario 1 — Temporal validity pass (all cited evidence valid).
- [x] 12.2 Scenario 2 — Temporal leakage detected (one cited item with `news_time > forecast_time`, verdict `invalid_temporal_leakage`).
- [x] 12.3 Scenario 3 — Evidence support exact match (DOWN/DOWN, support score 1.0).
- [x] 12.4 Scenario 4 — Evidence support mismatch (UP/DOWN, support score 0.0, verdict `unsupported_evidence`).
- [x] 12.5 Scenario 5 — Evidence support HOLD partial match (UP/HOLD, support score 0.5).
- [x] 12.6 Scenario 6 — Confidence drop large (0.80 - 0.55 = 0.25).
- [x] 12.7 Scenario 7 — Confidence drop near zero (0.80 - 0.79 = 0.01, verdict `decorative_explanation_risk`).
- [x] 12.8 Scenario 8 — Confidence drop negative (0.55 - 0.80 = -0.25, warning `confidence_increased_after_removal`).
- [x] 12.9 Scenario 9 — Prediction changes after ablation (UP → DOWN, confidence_after_removal fallback 0.0, verdict `strong_faithful_candidate`).
- [x] 12.10 Scenario 10 — Empty cited evidence handled safely (verdict `decorative_explanation_risk`, no exceptions).
- [x] 12.11 Scenario 11 — Batch CSV export contains required columns (header matches `CSV_COLUMNS` in order, one row per report, warnings JSON-encoded).

## 13. Unit Tests — Edge Cases and Defensive Behavior

- [x] 13.1 Test `temporal_validity == 1.0` for empty cited evidence.
- [x] 13.2 Test `dataset_temporal_validity == 1.0` for empty batch.
- [x] 13.3 Test `dataset_temporal_validity` handles `total_news_count = 0` without raising.
- [x] 13.4 Test `evidence_support_score` for unknown `expected_direction` (treated as HOLD).
- [x] 13.5 Test `calculate_faithfulness_score` clamps negative `confidence_drop` for the composite (negative drop → composite uses `normalized_drop = 0.0`).
- [x] 13.6 Test `calculate_faithfulness_score` saturates `confidence_drop = 0.30` at `normalized_drop = 1.0`.
- [x] 13.7 Test `classify_faithfulness` clamps out-of-range `temporal_validity` and `evidence_support` before branching.
- [x] 13.8 Test `evaluate` raises `FaithfulnessEvaluatorError` on missing `prediction`, missing `confidence`, missing `forecast_time`, invalid `ablation_strategy`.
- [x] 13.9 Test `evaluate` reports all keys present on the output dict (no `None` for any list-valued key).
- [x] 13.10 Test `per_evidence_results` are sorted by `evidence_id` ascending.
- [x] 13.11 Test determinism: same input twice → byte-equal output (including list ordering).
- [x] 13.12 Test `evaluate_batch` swallows per-record errors without raising and records the failure in the row's `warnings`.

## 14. Integration Test with the Forecast Model

- [x] 14.1 Add an integration test that wires a small fixture through `predict(...)` → `evaluate(...)` and asserts the dashboard-ready report is well-formed and the verdict is one of `VERDICTS`.
- [x] 14.2 Add an integration test that wires `predict_batch(...)` → `evaluate_batch(...)` on a 5-record fixture and asserts the CSV is written with the correct header and one row per record.
- [x] 14.3 Add an integration test that exercises both ablation strategies (`remove_cited_pro_evidence`, `remove_all_cited_evidence`) on a single fixture and asserts the reports differ when the cited sets differ.
- [x] 14.4 Add an integration test that exercises the news-id collapse when the Forecast Model only accepts news-level input (mock if needed) and asserts the `ablation_warnings` record the expansion.

## 15. Documentation

- [x] 15.1 Update `README.md` to add a "Faithfulness Evaluator" section with: the algorithm summary (the three metrics + composite + verdict), the input/output schemas, the ablation strategies, the CSV columns, and a pointer to the sample fixtures.
- [x] 15.2 Document the rule-based scope in the module docstrings of `src/faithfulness_metrics.py` and `src/faithfulness_evaluator.py` (no LLM, no FinBERT, no model training, no network access, no price features).
- [x] 15.3 Add a "Limitations" subsection enumerating: composite score is a V1 heuristic, integer-only verdict cascade, single-ticker evaluation, deterministic and rule-based, the V2 extension point for per-evidence leave-one-out ablation.

## 16. Validation

- [x] 16.1 Run `pytest tests/ -v` and confirm a green run, including the new `test_faithfulness_metrics.py` and `test_faithfulness_evaluator.py` suites, the golden fixture regression, and the integration tests.
- [x] 16.2 Run `openspec validate faithfulness-evaluator --strict` and resolve any reported issues.
- [x] 16.3 Run `openspec status --change faithfulness-evaluator` and confirm the change is ready to apply.
- [x] 16.4 Run `pytest tests/ --tb=short` after a clean run and confirm zero failures and zero warnings related to the new modules.
