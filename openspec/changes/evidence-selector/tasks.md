# Tasks: Evidence Selector (Version 1)

Tasks are grouped by dependency order. Each task is small enough to complete in one session and produces a verifiable artifact. Tasks intentionally do NOT include source-code lines — they describe the artifact to be produced, not the exact text to type.

## 1. Input / Output Schema and Module Skeleton

- [x] 1.1 Create the module file `src/evidence_selector.py` and re-export the public API from `src/__init__.py` (analogous to the Evidence Extractor's `__init__.py` exports).
- [x] 1.2 Define a typed `EvidenceSelectorError(ValueError)` exception class for unrecoverable input problems (e.g., missing `prediction`, `prediction` not in `{"UP","DOWN","HOLD"}`, missing or non-list `evidence_candidates`).
- [x] 1.3 Document in the module docstring the contract: the selector consumes a (prediction, evidence_candidates) request and emits a structured per-prediction result object, never re-implements temporal filtering, and never reads a ground-truth label.
- [x] 1.4 Define the input field list and output field list as constants in the module (e.g., `EvidenceSelector.REQUIRED_INPUT_FIELDS`, `EvidenceSelector.OUTPUT_GROUPS = ("pro_evidence", "counterevidence", "neutral_evidence")`) so tests and downstream code can introspect them.

## 2. Classification Rules

- [x] 2.1 Implement the **Classification Table** as a module-level constant `_CLASSIFICATION_TABLE: Dict[Tuple[str, str], str]` mapping `(prediction, expected_direction) → selector_label`. Cover all nine cells.
- [x] 2.2 Implement the **Classification Reason Table** as a sibling constant `_REASON_TABLE: Dict[Tuple[str, str], str]` with the exact reason strings from the spec.
- [x] 2.3 Implement a private helper `_classify(prediction, expected_direction) -> Tuple[str, str]` that returns `(selector_label, reason)`. Raise `EvidenceSelectorError` for an unknown `prediction`; raise for an unknown `expected_direction` only if the candidate is well-formed enough to know the direction.
- [x] 2.4 Add a unit test asserting the full nine-cell table maps to the expected `(selector_label, reason)` pairs. Parametrize over the table.

## 3. Future-Evidence Protection and Skipped Candidates

- [x] 3.1 Implement a private helper `_parse_news_time(value) -> Optional[datetime]` that returns `None` for missing, `None`, or unparseable values (defensive default per the spec).
- [x] 3.2 Implement a private helper `_is_future(news_time, forecast_time) -> bool` that compares parsed datetimes with the same UTC-naive normalization rules used by the Temporal Retriever (so naive timestamps are interpreted as UTC).
- [x] 3.3 Wire future-evidence flagging into the candidate loop: candidates with `news_time > forecast_time` go to `invalid_future_evidence` with `reason = "future_evidence"`. Candidates with missing or unparseable `news_time` are treated as not-future.
- [x] 3.4 Wire malformed-candidate handling: candidates missing `expected_direction` or with an unknown `expected_direction` go to an `invalid_candidates` list (not `invalid_future_evidence`); well-formed candidates in the same request are still classified.
- [x] 3.5 Add unit tests for: (a) a future candidate is flagged and not classified; (b) an equal-timestamp candidate is classified normally; (c) a missing-`news_time` candidate is classified normally; (d) one malformed candidate does not abort the batch.

## 4. Ranking and top_k Truncation

- [x] 4.1 Implement a private helper `_sort_by_score_desc(items) -> List[dict]` that performs a stable sort by `selector_score` descending (use Python's stable sort with key `-selector_score`).
- [x] 4.2 Implement a private helper `_truncate(items, top_k) -> List[dict]` that returns the first `top_k` items (the post-sort list is already in correct order).
- [x] 4.3 Add unit tests for ranking (descending by score; stable on ties) and for `top_k` truncation (per-group cap; `summary` counts unchanged).

## 5. Summary Metrics

- [x] 5.1 Implement a private helper `_build_summary(pro_full, counter_full, neutral_full) -> dict` returning `{pro_count, counter_count, neutral_count, has_counterevidence, counterevidence_ratio}`. The `counterevidence_ratio` is `0.0` when `pro_count + counter_count == 0`.
- [x] 5.2 Add unit tests for: (a) the three ratio cases (both > 0, only pro, neither); (b) `has_counterevidence` boolean for all combinations; (c) `summary` counts use pre-truncation totals.

## 6. Public API

- [x] 6.1 Implement `EvidenceSelector.select(request: dict, *, top_k_pro: int = 3, top_k_counter: int = 3, top_k_neutral: int = 3) -> dict` that:
  - Validates the top-level fields and raises `EvidenceSelectorError` on bad `prediction` or non-list `evidence_candidates`.
  - Iterates candidates, applies future-evidence protection, classifies valid candidates, and aggregates into the three groups.
  - Sorts and truncates each group with the appropriate `top_k`.
  - Builds the `summary` from the pre-truncation groups.
  - Returns the result dict with `selection_method = "rule_based"`.
- [x] 6.2 Implement `EvidenceSelector.select_batch(requests: List[dict], **kwargs) -> List[dict]` that returns one result per input, in input order. No time-based filtering, no parallelism.
- [x] 6.3 Add an optional `select_evidence_with_coverage(request, *, expected_labels: Optional[Dict[str, str]] = None)` helper that, when `expected_labels` is provided, augments the result with a `coverage` field containing `counterevidence_coverage` and `counterevidence_detected_rate` (per-prediction) values. Document that this helper exists for the Faithfulness Evaluator to use and that it never reads a label from the input candidate list.
- [x] 6.4 Add a module-level `EvidenceSelector.CLASSIFICATION_TABLE` and `EvidenceSelector.REASON_TABLE` re-export so downstream modules (Faithfulness Evaluator, Dashboard) can import them as the single source of truth (analogous to the Evidence Extractor's `EvidenceExtractor.KEYWORD_TO_POLARITY`).

## 7. Unit Tests — Classification Matrix

- [x] 7.1 Test all nine cells of the classification table (parametrized over `(prediction, expected_direction, expected_label, expected_reason_substring)`).
- [x] 7.2 Test the `reason` strings are emitted verbatim (exact-string assertions for at least three representative cells).
- [x] 7.3 Test ranking: items in the same group sorted by `selector_score` descending; stable on equal scores.
- [x] 7.4 Test `top_k` truncation per group; defaults to `(3, 3, 3)`.
- [x] 7.5 Test empty `evidence_candidates` → all groups `[]`, all counts `0`, `has_counterevidence = false`, `counterevidence_ratio = 0.0`, no exception.

## 8. Unit Tests — Edge Cases and Defensive Behavior

- [x] 8.1 Test future-evidence flagging: a candidate with `news_time > forecast_time` goes to `invalid_future_evidence`, NOT to any pro/counter/neutral group; `summary` counts exclude it.
- [x] 8.2 Test equal-timestamp evidence is classified normally (not flagged as future).
- [x] 8.3 Test missing or unparseable `news_time` is treated as not-future.
- [x] 8.4 Test one bad candidate does not abort the batch (a malformed candidate is reported in `invalid_candidates`; other candidates are still classified).
- [x] 8.5 Test top-level validation failures raise `EvidenceSelectorError` (missing `prediction`, `prediction` not in `{"UP","DOWN","HOLD"}`, missing/non-list `evidence_candidates`).
- [x] 8.6 Test field preservation: every output evidence item contains all seven input fields plus `selector_label`, `selector_score`, `reason`; no `ground_truth_label` echoed.
- [x] 8.7 Test label-leakage protection: a candidate carrying `ground_truth_label = "DOWN"` is classified purely on its `expected_direction`; the output item does NOT contain `ground_truth_label`.
- [x] 8.8 Test determinism: same input twice → same output (byte-equal for the JSON-serializable parts, including the order of items within each group).
- [x] 8.9 Test empty groups are returned as `[]` (not `null`) for all four list fields.

## 9. Golden Fixtures

- [x] 9.1 Create `samples/evidence_selector/01_up_with_counter_input.json` and `_expected.json` (UP prediction, one pro, one counter, one neutral, one future).
- [x] 9.2 Create `samples/evidence_selector/02_down_input.json` and `_expected.json` (DOWN prediction, one pro, one counter).
- [x] 9.3 Create `samples/evidence_selector/03_hold_input.json` and `_expected.json` (HOLD prediction, one pro, one counter).
- [x] 9.4 Add a `samples/evidence_selector/README.md` describing the schema and the example coverage.
- [x] 9.5 Add a parametrized regression test in `tests/test_evidence_selector.py` (analogous to `test_golden_fixture_matches_extractor_output`) that asserts byte-equality on every fixture pair.

## 10. Module Integration and Re-exports

- [x] 10.1 Update `src/__init__.py` to re-export `EvidenceSelector.select`, `EvidenceSelector.select_batch`, `EvidenceSelectorError`, and the public classification / reason tables.
- [x] 10.2 Verify there are no circular imports with `src/retriever.py` and `src/evidence_extractor.py`.
- [x] 10.3 Verify the module does not import `datetime` parsing utilities from the Temporal Retriever (or, if it does, document the dependency and pin the contract).

## 11. Documentation

- [x] 11.1 Update `README.md` to add an "Evidence Selector" section with single-prediction and batch examples, the contract notes for downstream consumers (Faithfulness Evaluator, Dashboard), and a pointer to the sample fixtures.
- [x] 11.2 Document the rule-based scope in the module docstring and `README.md` (no LLM, no FinBERT, no model training, no network access).
- [x] 11.3 Add a "Limitations" subsection enumerating: rule-based misclassification on nuanced cases, `extractor_score`-only ranking, `top_k` truncation silently dropping items beyond the cap (with `summary` counts still full), and the V2 extension point for `keyword_strength * recency_weight`.

## 12. Validation

- [x] 12.1 Run `pytest tests/ -v` and confirm a green run, including the new `test_evidence_selector.py` suite and the golden fixture regression.
- [x] 12.2 Run `openspec validate evidence-selector --strict` (or the local equivalent) and resolve any reported issues.
- [x] 12.3 Run `openspec status --change evidence-selector` and confirm the change is ready to apply.
- [x] 12.4 Run `pytest tests/ --tb=short` after a clean run and confirm zero failures and zero warnings related to the new module.
