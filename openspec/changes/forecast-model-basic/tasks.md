# Tasks: Forecast Model (Version 1)

Tasks are grouped by dependency order. Each task is small enough to complete in one session and produces a verifiable artifact. Tasks intentionally do NOT include source-code lines — they describe the artifact to be produced, not the exact text to type.

## 1. Module Skeleton and Constants

- [x] 1.1 Create the module file `src/forecast_model.py` and re-export the public API from `src/__init__.py` (analogous to the Evidence Selector's `__init__.py` exports).
- [x] 1.2 Define a typed `ForecastModelError(ValueError)` exception class for unrecoverable input problems (e.g., missing `forecast_time`, malformed `forecast_time`).
- [x] 1.3 Define the input field list and output field list as `ForecastModel` class constants: `REQUIRED_INPUT_FIELDS = ("sample_id", "ticker", "forecast_time", "evidence")`, `VALID_PREDICTIONS = ("UP", "DOWN", "HOLD")`, `VALID_DIRECTIONS = ("UP", "DOWN", "HOLD")`, `MODEL_VERSION = "rule_based_v1"`, `OUTPUT_EVIDENCE_LISTS = ("pro_evidence", "counter_evidence", "up_evidence", "down_evidence", "neutral_evidence")`. The CSV column list and rationale templates are also exposed as `ForecastModel` class constants so downstream classes can import them as the single source of truth.
- [x] 1.4 Document in the module docstring the contract: the model consumes a `(sample_id, ticker, forecast_time, evidence)` request and emits a `ForecastResult` dict. It does NOT re-extract evidence from raw news text, does NOT call any LLM / FinBERT / transformer / logistic regression / deep-learning model / external API, and does NOT consult price data. The Temporal Retriever owns temporal validity (defense-in-depth here); the Evidence Extractor owns polarity; the Evidence Selector owns pro/counter/neutral classification.

## 2. Voting and Confidence Helpers

- [x] 2.1 Implement a private helper `_vote(evidence_items) -> Tuple[int, int, int, int]` that returns `(positive_count, negative_count, neutral_count, score)`. Iterate the items once; reject unknown `expected_direction` values by raising `ForecastModelError` (the strict-mode policy is enforced here, while the default skip-and-warn behavior is enforced in the public function).
- [x] 2.2 Implement a private helper `_compute_confidence(score, directional_evidence_count) -> float` that returns `0.5` when `directional_evidence_count == 0`, else `max(0.5, min(0.95, 0.5 + min(abs(score) * 0.1, 0.45)))`.
- [x] 2.3 Implement a private helper `_compute_evidence_strength(score, directional_evidence_count) -> float` returning `abs(score) / directional_evidence_count` (or `0.0` when the denominator is 0).
- [x] 2.4 Implement a private helper `_compute_conflict_ratio(positive_count, negative_count) -> float` returning `min(p, n) / max(p + n, 1)`.
- [x] 2.5 Add unit tests pinning the four helpers' values for: (a) UP-dominant (3/1), (b) DOWN-dominant (1/3), (c) balanced (2/2), (d) neutral-only (0/0 with HOLD items), (e) empty (0/0/0). Confidence values MUST be 0.7, 0.7, 0.5, 0.5, 0.5 respectively.

## 3. Pro / Counter / Raw Evidence Partition

- [x] 3.1 Implement a private helper `_partition_evidence(evidence_items) -> Dict[str, List[dict]]` that returns `{"up_evidence", "down_evidence", "neutral_evidence"}`. Each list is sorted by `evidence_id` ascending (stable, deterministic). Unknown `expected_direction` values are routed to a `warnings` list (caller-supplied) and excluded from all three lists.
- [x] 3.2 Implement a private helper `_build_pro_and_counter(prediction, up, down) -> Tuple[List[dict], List[dict]]` that returns `(pro_evidence, counter_evidence)` per the spec table (UP→UP/DOWN, DOWN→DOWN/UP, HOLD→[]/[]). Both lists are sorted by `evidence_id` ascending.
- [x] 3.3 Add unit tests for: (a) UP prediction with both UP and DOWN evidence; (b) DOWN prediction with both UP and DOWN evidence; (c) HOLD prediction with all three kinds; (d) HOLD prediction with only neutral evidence. Each test asserts the `pro_evidence` / `counter_evidence` lists are exactly what the spec table requires, in `evidence_id` order.

## 4. Rationale Builder

- [x] 4.1 Implement a private helper `_build_rationale(prediction, positive_count, negative_count, directional_evidence_count) -> str` that returns the exact string from the rationale template table. The four branches are: UP, DOWN, HOLD-balanced, HOLD-no-directional. The function uses an `f`-string per branch — no concatenation, no LLM.
- [x] 4.2 Add unit tests pinning the exact string for each of the four branches, including the integer formatting of `{positive_count}` and `{negative_count}`.

## 5. Temporal Validation and Defensive Helpers

- [x] 5.1 Implement a private helper `_parse_news_time(value) -> Optional[datetime]` that returns `None` for missing, `null`, or unparseable values. The function MUST be tolerant of both `"T"` and `" "` separators. Reuse the `src.retriever.TimeUtils.parse_datetime` and `src.retriever.TimeUtils.normalize_to_utc` helpers (or local copies of the same logic) so naive timestamps are interpreted as UTC consistently across the pipeline.
- [x] 5.2 Implement a private helper `_is_future(news_time, forecast_time) -> bool` that compares parsed datetimes in UTC, returning `True` only when `news_time` is STRICTLY greater than `forecast_time` (equal is not future).
- [x] 5.3 Implement a private helper `_deduplicate(evidence_items, warnings_out) -> List[dict]` that walks the input in order, keeps the first occurrence of each `evidence_id`, and appends a `{"code": "DUPLICATE_EVIDENCE_ID", "evidence_id": ..., "message": ...}` entry to `warnings_out` for each dropped duplicate.
- [x] 5.4 Implement a private helper `_filter_temporal(evidence_items, forecast_time, warnings_out) -> List[dict]` that returns the items that are NOT in the future (strict inequality), appending a `TEMPORAL_LEAKAGE_BLOCKED` entry to `warnings_out` for each excluded item and a `MALFORMED_NEWS_TIME` entry for items with missing or unparseable `news_time`.
- [x] 5.5 Add unit tests for: (a) future item excluded with warning; (b) equal-timestamp item included; (c) missing `news_time` included with `MALFORMED_NEWS_TIME` warning; (d) duplicate `evidence_id` kept-once with `DUPLICATE_EVIDENCE_ID` warning.

## 6. Public API — `ForecastModel.predict` and `ForecastModel.predict_without_evidence`

- [x] 6.1 Implement `_predict_core(input_data, *, exclude_ids=frozenset(), strict=False) -> dict` that:
  - Validates the top-level fields and raises `ForecastModelError` on missing `sample_id`, missing `ticker`, missing or unparseable `forecast_time`, or non-list `evidence`.
  - Deduplicates by `evidence_id` via `_deduplicate` (emitting `DUPLICATE_EVIDENCE_ID` warnings).
  - Filters temporal-leakage via `_filter_temporal` (emitting `TEMPORAL_LEAKAGE_BLOCKED` / `MALFORMED_NEWS_TIME` warnings).
  - Filters out items whose `evidence_id` is in `exclude_ids` (silently — this is the faithfulness support path, not a warning).
  - Splits items into directional vs. neutral; under `strict = False` skips items with missing or unknown `expected_direction` and emits `INVALID_EVIDENCE` warnings; under `strict = True` raises on the first such item.
  - Calls `_vote`, `_compute_confidence`, `_compute_evidence_strength`, `_compute_conflict_ratio` to compute the score, confidence, evidence_strength, and conflict_ratio.
  - Calls `_partition_evidence` and `_build_pro_and_counter` to populate the five evidence lists.
  - Calls `_build_rationale` to produce the rationale string.
  - Echoes `sample_id`, `ticker`, `forecast_time`, and (if present) `label` verbatim in the result.
  - Returns a dict containing every field in the spec's output schema, with `model_version = "rule_based_v1"`.
- [x] 6.2 Implement `ForecastModel.predict(input_data, *, strict=False) -> dict` as a thin wrapper that calls `_predict_core(input_data, strict=strict)`.
- [x] 6.3 Implement `ForecastModel.predict_without_evidence(input_data, removed_evidence_ids, *, strict=False) -> dict` that calls `_predict_core(input_data, exclude_ids=frozenset(removed_evidence_ids or ()), strict=strict)`. The function MUST accept `removed_evidence_ids = None` and treat it as empty.
- [x] 6.4 Add unit tests for the nine acceptance scenarios from the spec (UP-dominant, DOWN-dominant, balanced HOLD, neutral-only HOLD, empty HOLD, future-evidence blocking, ForecastModel.predict_without_evidence for confidence_drop, template-based rationale, batch evaluation — the last is covered in task 7).

## 7. Public API — Batch, CSV, and Evaluation Helper

- [x] 7.1 Implement `ForecastModel.predict_batch(records, *, output_csv_path=None, output_json_path=None, strict=False) -> List[dict]` that:
  - Iterates `records` in input order and calls `ForecastModel.predict` on each.
  - Catches `ForecastModelError` per record: on error, returns a default result with `prediction = "HOLD"`, `confidence = 0.5`, all counts zero, and an `INPUT_ERROR` warning. The batch never raises.
  - Returns a list of result dicts, one per record, in input order.
  - When `output_csv_path` is provided, writes the per-row scalar fields (`sample_id`, `ticker`, `forecast_time`, `prediction`, `confidence`, `score`, `positive_count`, `negative_count`, `neutral_count`, `total_evidence`, `directional_evidence_count`, `evidence_strength`, `conflict_ratio`, `label`, `model_version`) as a CSV. The column list is exposed as `ForecastModel.CSV_COLUMNS`. The default `output_csv_path` is `outputs/prediction_results.csv`.
  - When `output_json_path` is provided, writes the full list of result dicts (including the evidence lists) as a JSON file. The default `output_json_path` is `outputs/prediction_results.json` (sibling of the CSV).
- [x] 7.2 Implement `ForecastModel.compute_accuracy_and_confusion(results, *, label_key="label") -> dict` that:
  - Accepts a list of result dicts (each carrying `label`) OR a list of `(input_record, result_dict)` pairs (label lives on the input).
  - Builds a 3×3 confusion matrix over `["UP", "DOWN", "HOLD"]` with rows = predicted, columns = actual.
  - Computes `accuracy`, `precision`, `recall`, `f1`, `support` for each class.
  - Returns `{ "accuracy": float, "confusion_matrix": {"labels": [...], "matrix": [[...]]}, "per_class": {...}, "n_samples": int }`.
  - Returns zero metrics for an empty input list. Raises `ValueError` for a non-empty input where every record is missing a label (defensive default).
- [x] 7.3 Add unit tests for: (a) batch returns one result per record in input order; (b) batch writes a CSV with the correct header and one row per record; (c) batch writes a JSON file with the full per-record objects; (d) `ForecastModel.compute_accuracy_and_confusion` returns the expected matrix and metrics for a small fixture (e.g., 6 records: 2 UP/UP, 1 UP/DOWN, 1 DOWN/UP, 1 HOLD/HOLD, 1 DOWN/HOLD); (e) `ForecastModel.compute_accuracy_and_confusion` raises on a non-empty input with no labels.

## 8. Module Integration and Re-exports

- [x] 8.1 Update `src/__init__.py` to re-export `ForecastModel` and `ForecastModelError` (constants `MODEL_VERSION`, `VALID_PREDICTIONS`, `VALID_DIRECTIONS`, `REQUIRED_INPUT_FIELDS`, `OUTPUT_EVIDENCE_LISTS`, `CSV_COLUMNS`, `RATIONALE_TEMPLATES`, `CSV_DEFAULT_PATH` / `JSON_DEFAULT_PATH` are reached as `ForecastModel.<NAME>` class attributes).
- [x] 8.2 Verify there are no circular imports with `src/retriever.py`, `src/evidence_extractor.py`, and `src/evidence_selector.py`. The Forecast Model reuses `TimeUtils.parse_datetime` / `TimeUtils.normalize_to_utc` from the retriever (or a local copy with identical behavior) but does NOT import from the Evidence Extractor or the Evidence Selector.
- [x] 8.3 Add a `__pycache__`/`__init__.py` no-op if the package is being reorganized (only if the existing layout requires it — do not move files).

## 9. Golden Fixtures

- [x] 9.1 Create `samples/forecast_model/01_up_input.json` and `_expected.json` (3 UP + 1 DOWN → UP, score 2, confidence 0.7).
- [x] 9.2 Create `samples/forecast_model/02_down_input.json` and `_expected.json` (1 UP + 3 DOWN → DOWN, score -2, confidence 0.7).
- [x] 9.3 Create `samples/forecast_model/03_balanced_hold_input.json` and `_expected.json` (2 UP + 2 DOWN → HOLD, score 0, confidence 0.5).
- [x] 9.4 Create `samples/forecast_model/04_empty_hold_input.json` and `_expected.json` (empty `evidence` → HOLD, confidence 0.5, "no valid directional evidence" rationale).
- [x] 9.5 Create `samples/forecast_model/05_future_evidence_input.json` and `_expected.json` (mixed evidence with one future item → future item excluded, `TEMPORAL_LEAKAGE_BLOCKED` warning, prediction uses only valid items).
- [x] 9.6 Add a `samples/forecast_model/README.md` describing the schema and the example coverage.
- [x] 9.7 Add a parametrized regression test in `tests/test_forecast_model.py` (analogous to `test_golden_fixture_matches_selector_output`) that asserts byte-equality on every fixture pair.

## 10. Unit Tests — Acceptance Scenarios

- [ ] 10.1 Scenario 1 — Predict UP from positive-dominant evidence (3 UP + 1 DOWN → UP, score 2, confidence 0.7).
- [ ] 10.2 Scenario 2 — Predict DOWN from negative-dominant evidence (1 UP + 3 DOWN → DOWN, score -2, confidence 0.7).
- [ ] 10.3 Scenario 3 — Predict HOLD from balanced evidence (2 UP + 2 DOWN → HOLD, score 0, confidence 0.5).
- [ ] 10.4 Scenario 4 — Predict HOLD from neutral-only evidence (3 HOLD + 0 UP + 0 DOWN → HOLD, confidence 0.5, "no valid directional evidence" rationale).
- [ ] 10.5 Scenario 5 — Predict HOLD from empty evidence (HOLD, confidence 0.5, "no valid directional evidence" rationale, all evidence lists `[]`).
- [ ] 10.6 Scenario 6 — Block future evidence (`forecast_time = "2025-03-12 09:00"`, one item with `news_time = "2025-03-12 15:30"` → that item excluded, `TEMPORAL_LEAKAGE_BLOCKED` warning).
- [ ] 10.7 Scenario 7 — Support confidence drop evaluation (original confidence 0.8, ForecastModel.predict_without_evidence removes pro evidence → reduced confidence, evaluator can compute `confidence_drop`).
- [ ] 10.8 Scenario 8 — Generate template-based rationale (rationale mentions evidence count comparison; rationale does not invent external reasons).
- [ ] 10.9 Scenario 9 — Batch evaluation output (ForecastModel.predict_batch + ForecastModel.compute_accuracy_and_confusion → accuracy, confusion matrix, per-class metrics).

## 11. Unit Tests — Edge Cases and Defensive Behavior

- [ ] 11.1 Test `evidence_strength` and `conflict_ratio` formulas directly: (1, 0) → strength 1.0, ratio 0.0; (3, 1) → strength 0.5, ratio 0.25; (1, 1) → strength 0.0, ratio 0.5; (0, 0) → strength 0.0, ratio 0.0.
- [ ] 11.2 Test `confidence` clamping: `abs(score) = 0` → 0.5; `abs(score) = 5` → 0.95 (saturates); `abs(score) = 10` → 0.95 (still saturated).
- [ ] 11.3 Test rationale template exact match for the four branches.
- [ ] 11.4 Test deduplication: two items with the same `evidence_id` → first kept, second reported in `warnings` as `DUPLICATE_EVIDENCE_ID`.
- [ ] 11.5 Test invalid `expected_direction`: skipped with `INVALID_EVIDENCE` warning under `strict = False`; raises `ForecastModelError` under `strict = True`.
- [ ] 11.6 Test missing or unparseable `news_time`: item included with `MALFORMED_NEWS_TIME` warning.
- [ ] 11.7 Test missing or unparseable `forecast_time`: `ForecastModel.predict` raises `ForecastModelError`.
- [ ] 11.8 Test missing `sample_id`, missing `ticker`, missing `evidence`: `ForecastModel.predict` raises `ForecastModelError`.
- [ ] 11.9 Test field preservation: every output evidence item contains `evidence_id`, `news_id`, `news_time`, `evidence_text`, `polarity`, `expected_direction`, `support_score`. No `ground_truth_label` echoed.
- [ ] 11.10 Test empty evidence lists are returned as `[]` (not `null`) for all five evidence-list fields.
- [ ] 11.11 Test determinism: same input twice → same output (byte-equal for JSON-serializable parts, including the order of items within each evidence list).
- [ ] 11.12 Test that `ForecastModel.predict` does NOT read `label` even when present (label is echoed in output, never used for prediction).

## 12. Integration Test with the Evidence Extractor / Selector

- [ ] 12.1 Add an integration test that wires `EvidenceExtractor.extract` → `EvidenceSelector.select` (mocked, since V1 is single-ticker) → `ForecastModel.predict` on a small fixture and asserts the dashboard-ready result is well-formed and uses the correct `model_version`.
- [ ] 12.2 Add an integration test that calls `ForecastModel.predict_batch` on a 5-record fixture and asserts the CSV is written with the correct header and one row per record. Reuse the same fixture for the JSON sibling.
- [ ] 12.3 Add an integration test that calls `ForecastModel.predict_batch` followed by `ForecastModel.compute_accuracy_and_confusion` and asserts `n_samples`, `accuracy`, and the confusion matrix match the expected values for the fixture.

## 13. Documentation

- [ ] 13.1 Update `README.md` to add a "Forecast Model" section with: the algorithm summary, the input/output schemas, the rationale templates, the `ForecastModel.predict` / `ForecastModel.predict_batch` / `ForecastModel.predict_without_evidence` API, and a pointer to the sample fixtures.
- [ ] 13.2 Document the rule-based scope in the module docstring and `README.md` (no LLM, no FinBERT, no model training, no network access, no price features).
- [ ] 13.3 Add a "Limitations" subsection enumerating: integer-only score (no `support_score` weighting), confidence saturation at `abs(score) = 5`, the rationale is intentionally templated (no nuance), the V1 model is not designed for trading decisions, and the V2 extension point for keyword strength / recency weighting.

## 14. Validation

- [ ] 14.1 Run `pytest tests/ -v` and confirm a green run, including the new `test_forecast_model.py` suite, the golden fixture regression, and the integration tests.
- [ ] 14.2 Run `openspec validate forecast-model-basic --strict` and resolve any reported issues.
- [ ] 14.3 Run `openspec status --change forecast-model-basic` and confirm the change is ready to apply.
- [ ] 14.4 Run `pytest tests/ --tb=short` after a clean run and confirm zero failures and zero warnings related to the new module.
