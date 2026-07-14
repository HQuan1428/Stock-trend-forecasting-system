# Faithfulness Evaluator — Design (Version 1)

## Context

The Faithful Evidence-Centric Financial News Forecasting pipeline currently has four modules:

```
News + Price Data
  → Temporal Retriever       (owns temporal validity)
  → Evidence Extractor       (owns per-phrase evidence + polarity + expected_direction)
  → Evidence Selector        (owns pro / counter / neutral role assignment)
  → Forecast Model           (owns UP/DOWN/HOLD prediction + confidence + cited evidence)
  → Faithfulness Evaluator   (this change)
  → Visualization Dashboard  (consumes prediction + evaluation metrics)
```

After the Forecast Model runs, the prototype produces a `ForecastResult` that includes a prediction, a confidence in `[0.5, 0.95]`, and cited evidence items — but it has no module that asks the central research question: **"When the model cites evidence for its prediction, does that evidence actually influence the prediction?"** Without this evaluation step, the dashboard cannot distinguish a prediction that is *driven* by its cited evidence from one that merely *mentions* the evidence decoratively.

The Faithfulness Evaluator is a deterministic, rule-based function of the `ForecastResult` it is given plus a single re-invocation of the Forecast Model on an ablated input. It is NOT a learned model, does NOT call any LLM / FinBERT / transformer, and does NOT consult price data. It is the final analytical stage in the pipeline, and the Visualization Dashboard is its only downstream consumer.

This change introduces three new source files (`src/faithfulness_metrics.py`, `src/faithfulness_evaluator.py`, plus updates to `src/__init__.py`) and two test files (`tests/test_faithfulness_metrics.py`, `tests/test_faithfulness_evaluator.py`).

## Goals / Non-Goals

**Goals**

- Provide a pure-function module `src/faithfulness_metrics.py` with seven named metric functions and zero IO / no module-level side effects:
  - `calculate_prediction_temporal_validity(cited_evidence, forecast_time) -> float`
  - `calculate_dataset_temporal_validity(records) -> float` (operates on a batch)
  - `evidence_support_score(prediction, expected_direction) -> float`
  - `calculate_evidence_support(prediction, cited_evidence) -> float`
  - `calculate_confidence_drop(original_confidence, original_prediction, reduced_prediction, reduced_confidence, class_confidences=None, reduced_class_confidences=None) -> float`
  - `calculate_faithfulness_score(temporal_validity, evidence_support, confidence_drop) -> float`
  - `classify_faithfulness(temporal_validity, evidence_support, confidence_drop, prediction, prediction_after_removal) -> str`
- Provide a `FaithfulnessEvaluator` class in `src/faithfulness_evaluator.py` with a single public method `evaluate(original_input, original_result, *, ablation_strategy="remove_cited_pro_evidence") -> FaithfulnessReport` and a `FaithfulnessEvaluatorError(ValueError)` exception class.
- Re-use the existing `src.forecast_model.predict` and `src.forecast_model.ForecastModel.predict_without_evidence` for ablation. The evaluator MUST NOT duplicate the prediction algorithm.
- Export a small, fixed `VERDICTS` constant (six labels) and an `FaithfulnessEvaluator.ABLATION_STRATEGIES` constant (two V1 strategies).
- Export the public API from `src/__init__.py` so downstream consumers (Visualization Dashboard, `pipeline.py`) import a single stable surface.
- Provide an `FaithfulnessEvaluator.evaluate_batch(reports, *, output_csv_path="outputs/faithfulness_results.csv", output_json_path=None) -> List[dict]` helper that writes a per-row scalar CSV for the dashboard and a JSON sibling for full-fidelity inspection.
- Export `FaithfulnessEvaluator.CSV_COLUMNS` as a module-level constant (single source of truth for the dashboard) and `FaithfulnessEvaluator.CSV_DEFAULT_PATH` / `FaithfulnessEvaluator.JSON_DEFAULT_PATH` for the default file locations.
- Ship deterministic golden fixtures under `samples/faithfulness_evaluator/` covering the four canonical archetypes: strong-faithful, decorative-explanation-risk, temporal-leakage, and unsupported-evidence.
- Be fully testable with `pytest`, including the eleven named test cases from the spec.

**Non-Goals**

- LLM-based counterfactual reasoning, learned attention-based attribution, SHAP / LIME, gradient-based explanation, or any neural-network-based faithfulness signal.
- Calling FinBERT, transformer models, logistic regression, deep-learning models, or any external API.
- Re-extracting evidence from raw news text. The Evidence Extractor owns that. The evaluator is a deterministic function of the `ForecastResult` it is given.
- Re-classifying evidence. The Evidence Selector owns `pro_evidence` / `counter_evidence` assignment.
- Replacing or modifying the Forecast Model. The evaluator only consumes its output and re-invokes it on the ablated input.
- Reading raw `news_text`, `title`, or price data. The evaluator MUST be reachable from a CI run with no network, no GPU, and no external services.
- Calibrated probabilistic confidence, Platt scaling, isotonic regression, temperature scaling, or any other learned calibration.
- Multi-ticker or multi-horizon evaluation. Each `evaluate(...)` call is independent and single-ticker.
- Multi-step conversational faithfulness, LLM-as-judge, or natural-language explanation scoring.
- Trading advice, buy/sell recommendations, portfolio action, or any form of financial decision support.
- Scientifically validating the composite `faithfulness_score`. It is documented as a V1 dashboard heuristic, not a final metric.

## Decisions

### D1. Two-module split: `faithfulness_metrics` (pure) + `faithfulness_evaluator` (class)

**Choice.** Keep the seven metric functions in a pure module (`src/faithfulness_metrics.py`) with no IO, no globals beyond constants, and no side effects. The orchestrator (`FaithfulnessEvaluator`) lives in `src/faithfulness_evaluator.py` and is the only place that imports `src.forecast_model`.

**Why.** Pure functions are trivially unit-testable. The orchestrator owns the ablation call to the Forecast Model and the policy decisions (which ablation strategy to use, how to handle warnings, how to build the verdict). Splitting the two means a reviewer can audit the metric math without touching the Forecast Model.

**Alternatives considered.** A single file would be shorter but mixes pure math with IO. Keeping everything inside the orchestrator class makes the pure functions hard to reuse from the dashboard's own tests. Two modules wins on testability and on the single-responsibility boundary.

### D2. Ablation happens via `ForecastModel.predict_without_evidence`, not by re-extracting evidence

**Choice.** The evaluator passes the original `input_data` envelope and a list of removed evidence IDs to `src.forecast_model.ForecastModel.predict_without_evidence`. The evaluator itself never touches the raw `evidence` list in any way that could drift from the Forecast Model's scoring.

**Why.** The Forecast Model is the single source of truth for `score`, `confidence`, and `prediction`. If the evaluator re-implemented the voting math it could silently drift from the model and the `confidence_drop` signal would be meaningless. Calling `ForecastModel.predict_without_evidence` guarantees that the only thing changing between the two runs is the evidence set.

**Alternatives considered.** A "shadow" implementation in the evaluator that re-runs the voting algorithm would avoid the second call but would be a maintenance hazard. A third-party library (e.g., a faithfulness library) would add a dependency. Reusing `ForecastModel.predict_without_evidence` is the safest choice.

### D3. Evidence removal is by `evidence_id`, with an explicit `news_id` collapse rule

**Choice.** When removing evidence, the evaluator filters by `evidence_id` (the unique key produced by the Evidence Extractor). When the ablation strategy targets `news_id` removal, the evaluator maps each cited `evidence_id` to its `news_id`, dedupes the resulting `news_id` set, and the Forecast Model removes every evidence item belonging to that news.

**Why.** `evidence_id` is the stable, deduplicated key. `news_id` is the source-article key; the Evidence Extractor may produce several evidence snippets from the same news article. The evaluator documents this explicitly because two snippets from the same article are both kept by default (they came from one real-world signal), but they are both removable together when the article-level ablation is requested.

**Alternatives considered.** A naive "remove by news_id" without the per-evidence expansion would lose evidence items that the Forecast Model would otherwise score. The explicit two-step (`evidence_id` → `news_id`) preserves the contract that the Forecast Model sees a coherent input list.

### D4. `prediction_after_removal` is part of the report, not just `confidence_drop`

**Choice.** The report includes `prediction_after_removal` so the verdict can mark a "strong faithful candidate" when the prediction itself flips after ablation (e.g., UP → DOWN). Without this, a large `confidence_drop` that does not flip the prediction would look the same as a small one that does.

**Why.** The verdict table is explicit: "if prediction changes after evidence removal → strong_faithful_candidate" is one of the six branches and the dashboard surfaces it. Hiding the post-removal prediction would force the dashboard to re-run the Forecast Model itself.

**Alternatives considered.** Returning only `confidence_drop` would force the dashboard to re-invoke the model to surface the flip. Including `prediction_after_removal` keeps the dashboard a pure consumer of the report.

### D5. Composite `faithfulness_score` is heuristic, with `confidence_drop` as the primary signal

**Choice.** The composite score is `0.35 * temporal_validity + 0.30 * evidence_support + 0.35 * normalized_drop`, where `normalized_drop = min(max(confidence_drop, 0.0) / 0.30, 1.0)`. The docstring on `calculate_faithfulness_score` and the README both state explicitly that this is a V1 dashboard heuristic, not a final scientific metric. The `confidence_drop` field is the only signal that carries primary weight in the verdict table.

**Why.** The prototype needs a single readable number for the dashboard, but the user-facing documentation must not overclaim. The composite has a fixed maximum (1.0), the normalized drop saturates at `0.30`, and the weights are pinned in the spec so reviewers can reason about them.

**Alternatives considered.** Reporting only the three sub-metrics would push the burden of aggregation onto the dashboard. A learned weighted score would be unsupportable from a rule-based prototype. The 35/30/35 weighting is the simplest choice that keeps the three sub-metrics in balance and matches the example in the proposal.

### D6. Verdict classification is deterministic and ordered

**Choice.** The verdict is computed by a fixed ordered cascade:

1. `temporal_validity < 1.0` → `invalid_temporal_leakage`
2. `evidence_support < 0.5` → `unsupported_evidence`
3. `prediction_after_removal != prediction` → `strong_faithful_candidate`
4. `confidence_drop >= 0.20` → `strong_faithful_candidate`
5. `confidence_drop >= 0.10` → `moderate_faithful_candidate`
6. `confidence_drop >= 0.05` → `weak_faithful_candidate`
7. else → `decorative_explanation_risk`

The branches are evaluated top-to-bottom and stop at the first match. The `VERDICTS` constant is exported as a `frozenset` of six labels so tests can assert membership.

**Why.** A deterministic ordered cascade is easy to test, easy to audit, and stable across runs. Random forests or learned thresholds would be inappropriate for a prototype that has to explain itself.

**Alternatives considered.** A scoring function with smooth blending would produce values like `0.62` and force the dashboard to bucket them. A rule engine like `durable-rules` would add a dependency. A simple if/elif chain wins.

### D7. Per-evidence results are a list of dicts, not nested objects

**Choice.** The `per_evidence_results` field is a list of dicts with the keys `evidence_id`, `expected_direction`, `support_score`, `is_cited`, and (when applicable) `temporal_warning`. Lists of dicts are JSON-serializable, CSV-friendly for the dashboard, and round-trip cleanly through `pytest`.

**Why.** The dashboard wants a flat table per row to render evidence-by-evidence sparklines. Nested dataclasses would force the dashboard to flatten them on every render.

**Alternatives considered.** A list of typed dataclasses would be cleaner in Python but would require a custom JSON encoder. Lists of dicts are the lower-friction option and match the rest of the pipeline's "dict-per-row" convention.

### D8. Warnings are categorized into three lists, not one

**Choice.** The report has three warning lists: `temporal_warnings`, `support_warnings`, `ablation_warnings`. Each list is always present and is `[]` when empty.

**Why.** The dashboard surfaces warnings by category: a temporal-leakage warning belongs in a red badge next to the timestamp, an unsupported-evidence warning belongs in a yellow badge next to the cited evidence, an ablation warning belongs in a footnote below the table. Categorizing at the source removes the dashboard's need to filter a single warnings list.

**Alternatives considered.** A single `warnings` list with a `category` field would push the bucketing onto the dashboard. Three pre-bucketed lists keep the contract minimal.

### D9. CSV columns are a module-level constant

**Choice.** `FaithfulnessEvaluator.CSV_COLUMNS = ("ticker", "forecast_time", "prediction", "original_confidence", "prediction_after_removal", "confidence_after_removal", "confidence_drop", "temporal_validity", "evidence_support", "faithfulness_score", "verdict", "warnings")` is exported from `src/faithfulness_evaluator.py`. The `FaithfulnessEvaluator.evaluate_batch` helper writes exactly these columns in this order.

**Why.** A single source of truth for the column list means the dashboard never has to guess the schema, and a future change can extend the list without breaking consumers that import it. The `warnings` column is the JSON-encoded list (empty `[]` when none), so each row is a single CSV line.

**Alternatives considered.** Hardcoding the column list inside `FaithfulnessEvaluator.evaluate_batch` would make it harder to extend. Letting the dashboard introspect the keys of the first row would produce unstable ordering. A module-level constant is the simplest durable contract.

### D10. Default ablation strategy is `remove_cited_pro_evidence`

**Choice.** When the caller does not specify an `ablation_strategy`, the evaluator uses `remove_cited_pro_evidence`. This strategy removes the cited evidence items whose `expected_direction` matches the prediction (i.e., the items that supported the prediction).

**Why.** Removing only the supporting evidence is the strongest test of the cited-evidence explanation: if the prediction collapses when the cited support is removed, the evidence was load-bearing. Removing all cited evidence (the alternative default) would also remove counter-evidence, which would skew the post-removal prediction upward by default and produce a less interpretable signal.

**Alternatives considered.** A "leave-one-out" ablation over every cited evidence item would be more thorough but would require N model calls per evaluation. A "remove all cited evidence" strategy is supported as `remove_all_cited_evidence` for callers who want the broader view.

## Metric Formulas

The metrics are implemented as pure functions. The formulas are pinned in the spec; this section documents the implementation choices.

### Temporal Validity

```
prediction_temporal_validity = 1.0   if every cited item has news_time <= forecast_time
                                0.0   if any cited item has news_time > forecast_time
                                1.0   if the cited list is empty (vacuous truth)

dataset_temporal_validity     = valid_news_count / total_news_count     if total_news_count > 0
                                1.0                                       otherwise (empty batch, no leakage)
```

The dataset-level metric is computed across a list of `(news_time, forecast_time)` pairs (or records carrying both). The default of `1.0` for an empty batch is the same convention used by the Forecast Model: an empty list is not a leakage.

### Evidence Support

```
evidence_support_score(prediction, expected_direction):
    if prediction == expected_direction:                  return 1.0
    if one of (prediction, expected_direction) is HOLD:    return 0.5
    return 0.0                                            (opposite directional)

prediction_evidence_support = mean([ evidence_support_score(prediction, e.expected_direction) for e in cited_evidence ])
```

The aggregation is a plain arithmetic mean. When `cited_evidence` is empty, the function returns `1.0` (no cited evidence → nothing to contradict).

### Confidence Drop

```
confidence_after_removal_for_original_class:
    if class_confidences_available(reduced_result):
        return reduced_result.class_confidences[original_prediction]
    elif reduced_result.prediction == original_prediction:
        return reduced_result.confidence
    else:
        return 0.0

confidence_drop = original_confidence - confidence_after_removal_for_original_class
```

The function accepts `reduced_class_confidences=None` and `original_class_confidences=None`. When both are absent, it falls through to the prediction-equality branch. The fallback to `0.0` is intentional: when the prediction flips, the original class has effectively zero support, and we want a large positive `confidence_drop` to flag that case. Negative `confidence_drop` is preserved verbatim, and the `classify_faithfulness` function emits `confidence_increased_after_removal` as an `ablation_warning`.

### Composite Score

```
normalized_drop = min(max(confidence_drop, 0.0) / 0.30, 1.0)
faithfulness_score = 0.35 * temporal_validity
                   + 0.30 * evidence_support
                   + 0.35 * normalized_drop
```

Negative `confidence_drop` values are clamped to `0.0` for the composite (the `confidence_drop` field itself keeps the signed value). The composite is in `[0.0, 1.0]`.

### Verdict

The verdict cascade is the seven-branch ordered list documented in `D6`. Each branch is a pure test of the three sub-metrics plus the prediction-equality check.

## Data Contracts

### Input Envelope

`evaluate(original_input, original_result, ...)` accepts:

| Argument          | Type                  | Required | Description |
|-------------------|-----------------------|----------|-------------|
| `original_input`  | `dict`                | yes      | The same envelope passed to `ForecastModel.predict(...)`. Carries `sample_id`, `ticker`, `forecast_time`, and `evidence`. The Forecast Model re-invokes on this exact envelope (with the relevant `evidence` items removed). |
| `original_result` | `dict` (ForecastResult) | yes    | The result returned by `ForecastModel.predict(...)` or `ForecastModel.predict_batch(...)`. Carries `prediction`, `confidence`, `score`, `pro_evidence`, `counter_evidence`, `warnings`, etc. |
| `ablation_strategy` | `str`               | no       | One of `FaithfulnessEvaluator.ABLATION_STRATEGIES` (`remove_cited_pro_evidence`, `remove_all_cited_evidence`). Default `remove_cited_pro_evidence`. |

### ForecastResult Shape (read by the evaluator)

The evaluator reads the following fields from `original_result`:

| Field            | Type    | Used for |
|------------------|---------|----------|
| `sample_id`      | str     | Echoed to the report (optional). |
| `ticker`         | str     | Echoed to the report. |
| `forecast_time`  | str     | Compared to each cited evidence `news_time`. May also be read from `original_input` as a fallback. |
| `prediction`     | str     | Verdict, evidence support, confidence drop. |
| `confidence`     | float   | Confidence drop. |
| `pro_evidence`   | list    | Cited-evidence set for the default ablation strategy. |
| `counter_evidence` | list  | Cited-evidence set for the broader ablation strategy. |
| `warnings`       | list    | Echoed into `ablation_warnings` when applicable. |
| `class_confidences` | dict\|None | Optional override of the post-removal confidence lookup. The Forecast Model currently does NOT emit `class_confidences`; the function tolerates `None`. |

When `pro_evidence` / `counter_evidence` are absent (e.g., a hand-built test fixture), the evaluator falls back to `cited_evidence` carried on the result. The `original_input["evidence"]` is the source-of-truth list for ablation; if a `cited_evidence` field is present on the result it is used for the metric and the `evidence` field on the input is used for ablation.

### FaithfulnessReport Shape

The report is a dict with the following keys, all always present:

| Key                       | Type            | Description |
|---------------------------|-----------------|-------------|
| `sample_id`               | str             | Echoed from input (may be empty). |
| `ticker`                  | str             | Echoed from input. |
| `forecast_time`           | str             | Echoed from input. |
| `prediction`              | str             | The original prediction. |
| `original_confidence`     | float           | The original confidence. |
| `temporal_validity`       | float           | `calculate_prediction_temporal_validity` on the cited evidence. |
| `evidence_support`        | float           | `calculate_evidence_support` over the cited evidence. |
| `confidence_drop`         | float           | Signed. May be negative. |
| `confidence_after_removal`| float           | The post-removal confidence for the original class. |
| `prediction_after_removal`| str             | The post-removal prediction. |
| `faithfulness_score`      | float           | The composite heuristic. |
| `verdict`                 | str             | One of `VERDICTS`. |
| `temporal_warnings`       | list[str]       | Always present; empty when none. |
| `support_warnings`        | list[str]       | Always present; empty when none. |
| `ablation_warnings`       | list[str]       | Always present; empty when none. |
| `per_evidence_results`    | list[dict]      | Per-evidence detail. Always present; empty when no cited evidence. |

### CSV Row Schema

`FaithfulnessEvaluator.evaluate_batch(...)` writes one CSV row per report, using these columns in this order:

```
ticker, forecast_time, prediction, original_confidence,
prediction_after_removal, confidence_after_removal, confidence_drop,
temporal_validity, evidence_support, faithfulness_score,
verdict, warnings
```

The `warnings` column is the JSON-encoded concatenation of the three warning lists. Empty warnings are encoded as `[]`. The CSV is written with a header row and quoted strings.

## Error Handling

| Condition                                          | Behavior                                                                                  |
|----------------------------------------------------|-------------------------------------------------------------------------------------------|
| `original_input` is not a dict                     | `FaithfulnessEvaluatorError`. Hard failure.                                               |
| `original_result` is not a dict                    | `FaithfulnessEvaluatorError`. Hard failure.                                               |
| `original_result["prediction"]` not in `{UP,DOWN,HOLD}` | `FaithfulnessEvaluatorError`. Hard failure.                                          |
| `original_result["confidence"]` is None or non-numeric | `FaithfulnessEvaluatorError`. Hard failure.                                              |
| `ablation_strategy` not in `FaithfulnessEvaluator.ABLATION_STRATEGIES`   | `FaithfulnessEvaluatorError`. Hard failure.                                               |
| `forecast_time` missing on both result and input   | `FaithfulnessEvaluatorError`. Hard failure (temporal validity is impossible).             |
| `ForecastModel.predict_without_evidence` raises `ForecastModelError` | Caught: appended to `ablation_warnings`; the post-removal prediction is forced to `HOLD` with confidence `0.5`; `confidence_drop` is computed against `0.5`. The report is still produced. |
| `cited_evidence` missing on the result and no `pro_evidence` / `counter_evidence` | `temporal_warnings` and `support_warnings` are populated, `temporal_validity = 1.0`, `evidence_support = 1.0`, `confidence_drop = 0.0`, `verdict = decorative_explanation_risk`. The report is still produced. |
| Empty cited evidence list                          | `temporal_validity = 1.0`, `evidence_support = 1.0`, `confidence_drop = 0.0`, `verdict = decorative_explanation_risk`. `per_evidence_results = []`. |
| `news_time` missing or unparseable on a cited item | Treated as not-future; added to `temporal_warnings` as `"MALFORMED_NEWS_TIME"`; included in the support aggregation. |

The `FaithfulnessEvaluator.evaluate_batch` helper never raises for a per-record error: a record that fails to evaluate is logged as a row with `verdict = "unsupported_evidence"` and an `ablation_warnings` entry of the form `EVALUATION_ERROR: <message>`. The CSV is always written with the same columns.

## Edge Cases

| Edge case                                                  | Expected behavior                                                                                                                                            |
|------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Cited evidence all valid (every `news_time <= forecast_time`) | `temporal_validity = 1.0`, no `temporal_warnings`.                                                                                                       |
| One cited evidence has `news_time > forecast_time`         | `temporal_validity = 0.0`, `temporal_warnings` lists the offending `evidence_id` and the parsed timestamps, `verdict = invalid_temporal_leakage`.            |
| Empty cited evidence                                       | `temporal_validity = 1.0`, `evidence_support = 1.0`, `confidence_drop = 0.0`, `verdict = decorative_explanation_risk`. `per_evidence_results = []`.             |
| All cited evidence matches the prediction                  | `evidence_support = 1.0`, no `support_warnings`.                                                                                                            |
| Cited evidence is mixed (some UP, some DOWN)               | `evidence_support` is the average; `support_warnings` lists each mismatched item with its expected direction.                                                |
| Cited evidence is HOLD only                                | `evidence_support = 0.5` per item (HOLD vs. UP/DOWN), aggregated as the mean.                                                                                 |
| Confidence drops after ablation                            | `confidence_drop > 0`; verdict branches into strong / moderate / weak faithful candidate based on the drop.                                                  |
| Confidence unchanged after ablation                        | `confidence_drop ≈ 0`; `verdict = decorative_explanation_risk`.                                                                                              |
| Confidence increases after ablation                        | `confidence_drop < 0`; verdict branches back to faithful candidate (the cited evidence was actively undermining the prediction); `ablation_warnings` includes `confidence_increased_after_removal`. |
| Prediction flips after ablation                            | `prediction_after_removal != prediction`; verdict `strong_faithful_candidate`.                                                                              |
| Ablation removes every directional evidence                | `ForecastModel.predict_without_evidence` returns `HOLD`, confidence `0.5`. `confidence_drop = original_confidence - 0.5`. Verdict branches accordingly.                       |
| `news_id` collapse when multiple evidence snippets share the same article | Both snippets are removed together by the `remove_all_cited_evidence` strategy. Documented in the report's `ablation_warnings`.                |

## Test Strategy

### Unit Tests (`tests/test_faithfulness_metrics.py`)

Pure-function tests, one assertion per test, fixture data inline. The eleven named scenarios from the proposal each become at least one test:

1. `test_calculate_prediction_temporal_validity_all_valid` — all `news_time <= forecast_time` → `1.0`.
2. `test_calculate_prediction_temporal_validity_one_future` — one item `news_time > forecast_time` → `0.0`, warning present.
3. `test_calculate_prediction_temporal_validity_empty_cited` — empty list → `1.0`.
4. `test_calculate_dataset_temporal_validity_zero_total` — `total_news_count = 0` → `1.0`, no division error.
5. `test_evidence_support_score_exact_match_DOWN_DOWN` — `1.0`.
6. `test_evidence_support_score_exact_match_UP_DOWN` — `0.0`.
7. `test_evidence_support_score_hold_partial_UP_HOLD` — `0.5`.
8. `test_calculate_evidence_support_average_multiple` — three cited items, mixed scores, assert mean.
9. `test_calculate_confidence_drop_large_positive` — `0.80 - 0.55 = 0.25`.
10. `test_calculate_confidence_drop_near_zero` — `0.80 - 0.79 = 0.01`.
11. `test_calculate_confidence_drop_negative` — `0.55 - 0.80 = -0.25`.
12. `test_calculate_confidence_drop_prediction_flips` — uses `class_confidences` fallback; expects `0.80 - 0.0 = 0.80`.
13. `test_calculate_faithfulness_score_known_weights` — `0.35 * 1.0 + 0.30 * 1.0 + 0.35 * 1.0 = 1.0`.
14. `test_classify_faithfulness_temporal_leakage` — `temporal_validity < 1.0` → `invalid_temporal_leakage`.
15. `test_classify_faithfulness_unsupported` — `evidence_support < 0.5` → `unsupported_evidence`.
16. `test_classify_faithfulness_strong_via_flip` — `prediction_after_removal != prediction` → `strong_faithful_candidate`.
17. `test_classify_faithfulness_strong_via_drop` — `confidence_drop >= 0.20` → `strong_faithful_candidate`.
18. `test_classify_faithfulness_moderate` — `confidence_drop >= 0.10` → `moderate_faithful_candidate`.
19. `test_classify_faithfulness_weak` — `confidence_drop >= 0.05` → `weak_faithful_candidate`.
20. `test_classify_faithfulness_decorative` — `confidence_drop < 0.05` → `decorative_explanation_risk`.

### Integration Tests (`tests/test_faithfulness_evaluator.py`)

1. End-to-end happy path: extract → select → predict → evaluate → assert report shape, verdict, and CSV row.
2. Strong-faithful scenario: 4 UP + 0 DOWN, citation of 3 UP items, ablation removes them → prediction flips to HOLD, `confidence_drop` large, verdict `strong_faithful_candidate`.
3. Decorative-explanation scenario: 1 UP + 1 DOWN, balanced, prediction HOLD, ablation removes the UP item → prediction still HOLD with confidence `0.5`, `confidence_drop ≈ 0`, verdict `decorative_explanation_risk`.
4. Temporal-leakage scenario: cited item with `news_time > forecast_time`, `temporal_validity = 0.0`, verdict `invalid_temporal_leakage`.
5. Unsupported-evidence scenario: prediction UP, cited evidence all DOWN, `evidence_support = 0.0`, verdict `unsupported_evidence`.
6. Empty cited evidence: prediction UP, `cited_evidence = []`, verdict `decorative_explanation_risk`, no exceptions.
7. Batch CSV export: 5-record batch, asserts CSV header is `FaithfulnessEvaluator.CSV_COLUMNS` and one row per record.
8. Golden fixtures: 4 `_input.json` / `_expected.json` pairs in `samples/faithfulness_evaluator/`, asserted byte-equal against `evaluate(...)` output.

## Dashboard / Export Requirements

- `outputs/faithfulness_results.csv` is the dashboard's primary input. One row per evaluated prediction. Column order pinned by `FaithfulnessEvaluator.CSV_COLUMNS`.
- `outputs/faithfulness_results.json` is the full-fidelity sibling, written when `output_json_path` is provided. The dashboard prefers the JSON for per-evidence drill-down.
- The `verdict` column drives the dashboard's color coding: red (`invalid_temporal_leakage`, `unsupported_evidence`), green (`strong_faithful_candidate`), yellow (moderate / weak), gray (`decorative_explanation_risk`).
- The `warnings` column is parsed as JSON in the dashboard. Empty list → no badge.
- `sample_id` is preserved through the pipeline so the dashboard can join `faithfulness_results.csv` back to `prediction_results.csv` (Forecast Model output) for cross-tabulation.
- The composite `faithfulness_score` is displayed with a footer caveat: "V1 heuristic — see spec."

## Migration Plan

1. **Land `src/faithfulness_metrics.py`** with the seven pure functions and unit tests. This module has no dependency on the Forecast Model and can be reviewed independently.
2. **Land `src/faithfulness_evaluator.py`** with the `FaithfulnessEvaluator` class, the `FaithfulnessEvaluator.evaluate_batch` helper, the `VERDICTS` and `FaithfulnessEvaluator.ABLATION_STRATEGIES` constants, and the `FaithfulnessEvaluator.CSV_COLUMNS` / `FaithfulnessEvaluator.CSV_DEFAULT_PATH` / `FaithfulnessEvaluator.JSON_DEFAULT_PATH` constants.
3. **Update `src/__init__.py`** to re-export the public surface.
4. **Land the golden fixtures** under `samples/faithfulness_evaluator/`.
5. **Land the integration tests** in `tests/test_faithfulness_evaluator.py`.
6. **Update `README.md`** with the "Faithfulness Evaluator" section: input/output schemas, metric formulas, ablation strategies, and a pointer to the fixtures.
7. **Run `pytest tests/ -v`** and confirm green.
8. **Run `openspec validate faithfulness-evaluator --strict`** and resolve any reported issues.

Rollback: removing the two new modules and the `__init__.py` re-export is a single git revert. No data migration is required because the Faithfulness Evaluator writes to fresh output paths (`outputs/faithfulness_results.csv`, `outputs/faithfulness_results.json`) that did not exist before this change.

## Open Questions

- **Should `FaithfulnessEvaluator.evaluate_batch` also produce a JSON sibling by default?** Current plan: only when `output_json_path` is provided. The Forecast Model writes its JSON sibling by default; the Faithfulness Evaluator could match that convention. Revisit when the dashboard mockups are in.
- **Should the `confidence_increased_after_removal` warning also be raised when `class_confidences` are provided and the original-class confidence went up?** Current plan: yes — the warning is about the signed `confidence_drop`, regardless of how it was computed.
- **Should the per-evidence `temporal_warning` field carry the parsed timestamps or just the evidence_id?** Current plan: just `evidence_id` plus the parsed `news_time` / `forecast_time` ISO strings (verbose enough for the dashboard but not for raw logs).
- **Should the verdict table be configurable?** Current plan: no — the verdict cascade is pinned in the spec. A future change can extend the table without breaking the existing verdicts.

## Risks / Trade-offs

- **[Risk] The composite `faithfulness_score` is a heuristic, not a scientific metric.** → Mitigation: documented prominently in the module docstring, the README, and the spec. The `confidence_drop` is the primary signal; the composite is for at-a-glance dashboard display only.
- **[Risk] The verdict cascade can hide edge cases.** → Mitigation: every `evaluate` call produces a fully populated report; the dashboard can render the raw sub-metrics alongside the verdict. The verdict is a label, not a filter.
- **[Risk] The evaluator depends on `ForecastModel.predict_without_evidence` to compute `confidence_drop`. If the Forecast Model changes its confidence algorithm, the absolute `confidence_drop` values shift.** → Mitigation: the evaluator pins the `MODEL_VERSION` indirectly through the `pro_evidence` / `counter_evidence` shape; a future change that introduces a V2 model can gate `evaluate` on `model_version` if needed.
- **[Risk] Calling `ForecastModel.predict_without_evidence` doubles the runtime per evaluation.** → Mitigation: the dashboard evaluates a batch once at the end of the pipeline, not on every render. For a 100-row batch the doubling is acceptable. A future change could cache `ForecastModel.predict_without_evidence` results if profiling shows it matters.
- **[Risk] `news_id` collapse removes every evidence snippet from the same article, which could be either more conservative (less ablation) or less conservative (more ablation) than the user expected.** → Mitigation: the report's `ablation_warnings` records exactly which `news_id`s were collapsed and which `evidence_id`s were removed as a result.
- **[Risk] `FaithfulnessEvaluator.evaluate_batch` swallows per-record errors.** → Mitigation: every error becomes a CSV row with `verdict = "unsupported_evidence"` and an `EVALUATION_ERROR` warning, so the dashboard sees the failure. The batch helper never raises.
- **[Risk] The `original_input` argument shadows the input's own `evidence` list when the result's `pro_evidence` / `counter_evidence` are present.** → Mitigation: the design documents that the Forecast Model re-invocation always uses the `original_input["evidence"]` list (after removal), not the result's `pro_evidence` / `counter_evidence`. The result's lists are read-only for the metrics.

## Out-of-Scope (Explicit)

The following are explicitly out of scope for V1 and will require a future change:

- LLM-as-judge for free-text rationale evaluation.
- Learned attention-based or SHAP-based faithfulness signals.
- Multi-ticker or multi-horizon evaluation.
- Caching of `ForecastModel.predict_without_evidence` results across batches.
- Configurable verdict thresholds.
- Per-evidence contribution scores (e.g., leave-one-out per item).
- Real-time streaming evaluation (the V1 is a batch evaluator).
- Multi-language support (the V1 operates on English-language news and English-language evidence text).
