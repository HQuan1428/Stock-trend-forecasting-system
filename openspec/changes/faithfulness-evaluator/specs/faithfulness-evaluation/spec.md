# Faithfulness Evaluator — Spec (Version 1)

This spec defines the behavior of the **Faithfulness Evaluator** module in the Faithful Evidence-Centric Financial News Forecasting pipeline. The Faithfulness Evaluator consumes a `ForecastResult` produced by the Forecast Model and a `FaithfulnessReport` describing whether the cited evidence actually influenced the prediction. It is the final analytical stage in the pipeline; the Visualization Dashboard is its only downstream consumer.

Version 1 is **deterministic, rule-based, and side-effect-free in single-evaluation mode**. It does NOT use any LLM, FinBERT, transformer, logistic regression, deep-learning model, or external API. It does NOT read raw `news_text` or price data. It does NOT modify the Forecast Model. It computes three required metrics (`temporal_validity`, `evidence_support`, `confidence_drop`), an optional composite `faithfulness_score`, and a readable `verdict`. The composite score is documented as a V1 heuristic; `confidence_drop` is the primary signal.

---

## Input Schema

The module SHALL expose `FaithfulnessEvaluator.evaluate(original_input, original_result, *, ablation_strategy="remove_cited_pro_evidence") -> FaithfulnessReport`.

### `original_input`

A dict matching the Forecast Model input envelope:

| Field           | Type   | Required | Description |
|-----------------|--------|----------|-------------|
| `sample_id`     | string | yes      | Stable identifier for the sample. Echoed in the report. |
| `ticker`        | string | yes      | Stock ticker the forecast is about. Echoed in the report. |
| `forecast_time` | string | yes      | Datetime string at which the forecast is made. Compared to each cited evidence `news_time`. |
| `evidence`      | list   | yes      | Full evidence list as passed to the Forecast Model. May be empty. |
| `label`         | string | no       | Preserved if present; NEVER read by the evaluator. |

Each `evidence` entry MUST contain the fields documented by the Forecast Model spec (`evidence_id`, `news_id`, `news_time`, `evidence_text`, `polarity`, `expected_direction`, optional `support_score`).

### `original_result`

A `ForecastResult` dict produced by `ForecastModel.predict(...)`, `ForecastModel.predict_batch(...)`, or a hand-built fixture. The evaluator reads:

| Field             | Type    | Description |
|-------------------|---------|-------------|
| `sample_id`       | string  | Echoed when present on the result; otherwise falls back to `original_input["sample_id"]`. |
| `ticker`          | string  | Same fallback as `sample_id`. |
| `forecast_time`   | string  | Same fallback as `sample_id`. |
| `prediction`      | string  | One of `"UP"`, `"DOWN"`, `"HOLD"`. MUST be present. |
| `confidence`      | number  | In `[0.5, 0.95]`. MUST be present. |
| `pro_evidence`    | list    | Cited evidence supporting the prediction (per Forecast Model spec). MAY be absent; the evaluator falls back to a `cited_evidence` field if present, and otherwise to `[]`. |
| `counter_evidence`| list    | Cited evidence conflicting with the prediction. Same fallback as `pro_evidence`. |
| `cited_evidence`  | list    | Optional explicit cited-evidence list. Used when `pro_evidence` / `counter_evidence` are absent. |
| `class_confidences` | dict\|None | Optional class-level confidence distribution. When present, used as the source for `confidence_after_removal` on the original class. |

### `ablation_strategy`

One of `FaithfulnessEvaluator.ABLATION_STRATEGIES`:

| Strategy                         | Description |
|----------------------------------|-------------|
| `remove_cited_pro_evidence`      | Default. Removes every evidence item whose `evidence_id` is in `pro_evidence` (the cited evidence supporting the prediction). |
| `remove_all_cited_evidence`      | Removes every evidence item whose `evidence_id` is in `pro_evidence` OR `counter_evidence`. |

For V1, the evaluator MUST raise `FaithfulnessEvaluatorError(ValueError)` if `ablation_strategy` is not one of these two values.

### Evidence Removal

When the ablation strategy targets an `evidence_id`, the Forecast Model's `ForecastModel.predict_without_evidence` is invoked with the matching `evidence_id` set. When the Forecast Model only accepts news-level input (i.e., when `ForecastModel.predict_without_evidence` is internally mapped to news IDs), the evaluator MUST expand each removed `evidence_id` to its `news_id`, dedupe the resulting `news_id` set, and remove every evidence item whose `news_id` is in the expanded set. The report MUST record this expansion in `ablation_warnings` as `"COLLAPSED_BY_NEWS_ID: <news_id> (expanded from <evidence_id_list>)"`.

When multiple cited evidence snippets come from the same news article, both snippets are removed together. This behavior is explicitly documented and applies only to the `remove_all_cited_evidence` strategy when invoked at the news level (the default behavior removes by `evidence_id` first, so multiple snippets from the same article stay removed together regardless).

---

## Output Schema

`evaluate(...)` returns a `FaithfulnessReport` dict. All keys are always present; list-valued keys are `[]` when empty, never `null`.

| Key                        | Type            | Description |
|----------------------------|-----------------|-------------|
| `sample_id`                | string          | Echoed from input. Empty string when unavailable. |
| `ticker`                   | string          | Echoed from input. |
| `forecast_time`            | string          | Echoed from input. |
| `prediction`               | string          | The original prediction (`UP` / `DOWN` / `HOLD`). |
| `original_confidence`      | number          | The original confidence (in `[0.5, 0.95]`). |
| `temporal_validity`        | number          | In `{0.0, 1.0}`. `1.0` if every cited evidence is temporally valid; `0.0` otherwise. |
| `evidence_support`         | number          | In `[0.0, 1.0]`. Mean of per-evidence support scores. |
| `confidence_drop`          | number          | Signed. `original_confidence - confidence_after_removal`. May be negative. |
| `confidence_after_removal` | number          | The post-removal confidence for the original prediction class. |
| `prediction_after_removal` | string          | The post-removal prediction (`UP` / `DOWN` / `HOLD`). |
| `faithfulness_score`       | number          | Composite heuristic. In `[0.0, 1.0]`. See *Composite Score*. |
| `verdict`                  | string          | One of `VERDICTS`. See *Verdict*. |
| `temporal_warnings`        | list[string]    | Always present; empty when none. |
| `support_warnings`         | list[string]    | Always present; empty when none. |
| `ablation_warnings`        | list[string]    | Always present; empty when none. Includes `confidence_increased_after_removal` when `confidence_drop < 0`. |
| `per_evidence_results`     | list[dict]      | One dict per cited evidence item. Empty list when no cited evidence. |

### Per-Evidence Result

Each entry in `per_evidence_results` is a dict with the following keys:

| Key                 | Type    | Description |
|---------------------|---------|-------------|
| `evidence_id`       | string  | The cited evidence ID. |
| `news_id`           | string  | The source news ID. |
| `news_time`         | string  | The cited evidence's `news_time`. |
| `expected_direction`| string  | The cited evidence's `expected_direction`. |
| `support_score`     | number  | `evidence_support_score(prediction, expected_direction)`. |
| `is_cited`          | bool    | `True` when the item is in the cited set. |
| `temporal_warning`  | string  | Empty string when valid; the warning message when `news_time > forecast_time`. |

### CSV Row Schema

`FaithfulnessEvaluator.evaluate_batch(reports, *, output_csv_path=None, output_json_path=None) -> list[dict]` writes one CSV row per report using these columns in this order:

```
ticker, forecast_time, prediction, original_confidence,
prediction_after_removal, confidence_after_removal, confidence_drop,
temporal_validity, evidence_support, faithfulness_score,
verdict, warnings
```

The `warnings` column is the JSON-encoded concatenation of the three warning lists. An empty `warnings` column is the literal string `[]`. The default `output_csv_path` SHALL be `outputs/faithfulness_results.csv`. When `output_json_path` is provided, a JSON sibling is written with the full per-record reports.

---

## Metric Formulas

### Temporal Validity (Prediction Level)

```
calculate_prediction_temporal_validity(cited_evidence, forecast_time) -> float:
    if cited_evidence is empty:                   return 1.0
    for item in cited_evidence:
        if news_time_of(item) > forecast_time:    return 0.0
    return 1.0
```

When a cited item has `news_time == forecast_time`, the item is treated as valid (strict inequality is the only failure mode). When `news_time` is missing or unparseable, the item is treated as not-future and the warning `MALFORMED_NEWS_TIME` is appended to `temporal_warnings`.

### Temporal Validity (Dataset Level)

```
calculate_dataset_temporal_validity(records) -> float:
    total = len(records)
    if total == 0:                                return 1.0
    valid = number of records with valid_news_time <= forecast_time
    return valid / total
```

`records` is a list of dicts each carrying `news_time` and `forecast_time`. The function MUST NOT raise on `total = 0` (no division-by-zero). The function MUST treat `news_time == forecast_time` as valid.

### Evidence Support (Per-Item)

```
evidence_support_score(prediction, expected_direction) -> float:
    if prediction == expected_direction:                              return 1.0
    if prediction == "HOLD" or expected_direction == "HOLD":          return 0.5
    return 0.0
```

The HOLD branch is symmetric: either side being HOLD yields `0.5`. The system SHALL treat any `expected_direction` value not in `{UP, DOWN, HOLD}` as `HOLD` for the per-item score (this is a defensive default that matches the Forecast Model's policy of routing unknown values to neutral).

### Evidence Support (Prediction Level)

```
calculate_evidence_support(prediction, cited_evidence) -> float:
    if cited_evidence is empty:                                       return 1.0
    scores = [ evidence_support_score(prediction, e.expected_direction) for e in cited_evidence ]
    return sum(scores) / len(scores)
```

The aggregation is a plain arithmetic mean. When `cited_evidence` is empty, the function returns `1.0` (no cited evidence to contradict).

### Confidence Drop

```
confidence_after_removal_for_original_class(
    original_prediction, original_confidence,
    reduced_prediction, reduced_confidence,
    reduced_class_confidences
) -> float:
    if reduced_class_confidences is not None
       and original_prediction in reduced_class_confidences:
        return reduced_class_confidences[original_prediction]
    if reduced_prediction == original_prediction:
        return reduced_confidence
    return 0.0

calculate_confidence_drop(
    original_confidence, original_prediction,
    reduced_prediction, reduced_confidence,
    reduced_class_confidences=None
) -> float:
    after = confidence_after_removal_for_original_class(...)
    return original_confidence - after
```

`confidence_drop` is signed. Negative values are preserved verbatim and `ablation_warnings` MUST include `"confidence_increased_after_removal"` whenever `confidence_drop < 0`.

### Composite Score

```
calculate_faithfulness_score(temporal_validity, evidence_support, confidence_drop) -> float:
    normalized_drop = min(max(confidence_drop, 0.0) / 0.30, 1.0)
    return 0.35 * temporal_validity
         + 0.30 * evidence_support
         + 0.35 * normalized_drop
```

`faithfulness_score` is in `[0.0, 1.0]`. Negative `confidence_drop` values are clamped to `0.0` for the composite only; the `confidence_drop` field itself retains its signed value. The composite is documented as a V1 dashboard heuristic, not a final scientific metric.

### Verdict

```
classify_faithfulness(
    temporal_validity, evidence_support, confidence_drop,
    prediction, prediction_after_removal
) -> str:
    if temporal_validity < 1.0:                                       return "invalid_temporal_leakage"
    if evidence_support < 0.5:                                        return "unsupported_evidence"
    if prediction_after_removal != prediction:                        return "strong_faithful_candidate"
    if confidence_drop >= 0.20:                                       return "strong_faithful_candidate"
    if confidence_drop >= 0.10:                                       return "moderate_faithful_candidate"
    if confidence_drop >= 0.05:                                       return "weak_faithful_candidate"
    return "decorative_explanation_risk"
```

`VERDICTS` is a fixed set of six labels: `invalid_temporal_leakage`, `unsupported_evidence`, `strong_faithful_candidate`, `moderate_faithful_candidate`, `weak_faithful_candidate`, `decorative_explanation_risk`. The classifier SHALL evaluate the branches in the order shown above and stop at the first match. The classifier SHALL NOT raise; an out-of-range `temporal_validity` or `evidence_support` is clamped to `[0.0, 1.0]` before branching.

---

## Determinism

The system SHALL be deterministic. Identical inputs SHALL produce identical outputs, including the order of items in `per_evidence_results`, the warning lists, and `faithfulness_score` to the precision of the Python `float`. The system SHALL NOT introduce randomness, timestamps, or non-deterministic ordering.

## Exported Constants

The module SHALL expose the following module-level constants:

- `VERDICTS = frozenset({"invalid_temporal_leakage", "unsupported_evidence", "strong_faithful_candidate", "moderate_faithful_candidate", "weak_faithful_candidate", "decorative_explanation_risk"})`
- `FaithfulnessEvaluator.ABLATION_STRATEGIES = ("remove_cited_pro_evidence", "remove_all_cited_evidence")`
- `FaithfulnessEvaluator.CSV_COLUMNS = ("ticker", "forecast_time", "prediction", "original_confidence", "prediction_after_removal", "confidence_after_removal", "confidence_drop", "temporal_validity", "evidence_support", "faithfulness_score", "verdict", "warnings")`
- `FaithfulnessEvaluator.CSV_DEFAULT_PATH = "outputs/faithfulness_results.csv"`
- `FaithfulnessEvaluator.JSON_DEFAULT_PATH = "outputs/faithfulness_results.json"`

The module SHALL re-export `FaithfulnessEvaluator`, `FaithfulnessEvaluatorError`, the public metric functions, and the constants from `src/__init__.py`.

---

## ADDED Requirements

### Requirement: Evaluate Temporal Validity of Cited Evidence

The system SHALL verify that every cited evidence item has `news_time <= forecast_time`, returning `1.0` when the cited evidence is empty or all items pass, `0.0` when any cited item fails, and emitting a warning per failing item.

#### Scenario: All cited evidence is temporally valid

- **WHEN** the cited evidence list contains three items, each with `news_time <= forecast_time`
- **THEN** `temporal_validity` SHALL equal `1.0`
- **AND** `temporal_warnings` SHALL equal `[]`

#### Scenario: At least one cited evidence appears after forecast_time

- **WHEN** the cited evidence list contains three items and one of them has `news_time > forecast_time`
- **THEN** `temporal_validity` SHALL equal `0.0`
- **AND** `temporal_warnings` SHALL contain one entry mentioning the offending `evidence_id`
- **AND** `verdict` SHALL equal `"invalid_temporal_leakage"`

#### Scenario: No cited evidence is available

- **WHEN** the cited evidence list is empty
- **THEN** `temporal_validity` SHALL equal `1.0`
- **AND** `temporal_warnings` SHALL equal `[]`

#### Scenario: Dataset-level temporal validity on an empty batch

- **WHEN** the dataset-level function is called with an empty list of records
- **THEN** the function SHALL return `1.0`
- **AND** the function SHALL NOT raise a division error

---

### Requirement: Evaluate Evidence Support

The system SHALL compare the prediction direction with each cited evidence item's `expected_direction` and return a per-item score and a mean score across the cited set.

#### Scenario: Exact directional match

- **WHEN** the prediction is `"DOWN"` and the cited evidence has `expected_direction = "DOWN"`
- **THEN** the per-item support score SHALL equal `1.0`
- **AND** `evidence_support` SHALL equal `1.0`

#### Scenario: Opposite directional match

- **WHEN** the prediction is `"UP"` and the cited evidence has `expected_direction = "DOWN"`
- **THEN** the per-item support score SHALL equal `0.0`
- **AND** the prediction-level `evidence_support` SHALL equal `0.0`
- **AND** `verdict` SHALL equal `"unsupported_evidence"`

#### Scenario: HOLD partial match

- **WHEN** the prediction is `"UP"` and the cited evidence has `expected_direction = "HOLD"`
- **THEN** the per-item support score SHALL equal `0.5`
- **AND** the prediction-level `evidence_support` SHALL equal `0.5`

#### Scenario: Multiple cited evidence items return the average

- **WHEN** the cited evidence list contains one UP-aligned item, one DOWN-aligned item, and one HOLD-aligned item
- **THEN** `evidence_support` SHALL equal `(1.0 + 0.0 + 0.5) / 3.0 ≈ 0.5`
- **AND** `per_evidence_results` SHALL contain three entries in `evidence_id` ascending order

#### Scenario: Empty cited evidence returns vacuous truth

- **WHEN** the cited evidence list is empty
- **THEN** `evidence_support` SHALL equal `1.0`
- **AND** `support_warnings` SHALL equal `[]`

---

### Requirement: Evaluate Confidence Drop via Ablation

The system SHALL remove the cited evidence items according to the chosen `ablation_strategy`, re-invoke the Forecast Model on the ablated input, and compute `confidence_drop = original_confidence - confidence_after_removal` using the post-removal confidence of the original prediction class.

#### Scenario: Confidence decreases after cited evidence removal

- **WHEN** the original prediction is `"DOWN"` with confidence `0.80` and the post-removal prediction is `"DOWN"` with confidence `0.55`
- **THEN** `confidence_drop` SHALL equal `0.25`
- **AND** `confidence_after_removal` SHALL equal `0.55`

#### Scenario: Confidence stays almost unchanged after cited evidence removal

- **WHEN** the original prediction is `"UP"` with confidence `0.80` and the post-removal prediction is `"UP"` with confidence `0.79`
- **THEN** `confidence_drop` SHALL equal `0.01`
- **AND** `verdict` SHALL equal `"decorative_explanation_risk"`

#### Scenario: Prediction changes after cited evidence removal

- **WHEN** the original prediction is `"UP"` and the post-removal prediction is `"DOWN"`
- **THEN** `prediction_after_removal` SHALL equal `"DOWN"`
- **AND** `confidence_after_removal` SHALL equal `0.0` (fallback for the original class)
- **AND** `confidence_drop` SHALL equal `original_confidence`
- **AND** `verdict` SHALL equal `"strong_faithful_candidate"`

#### Scenario: Confidence increases after cited evidence removal

- **WHEN** the original prediction is `"UP"` with confidence `0.55` and the post-removal prediction is `"UP"` with confidence `0.80`
- **THEN** `confidence_drop` SHALL equal `-0.25`
- **AND** `ablation_warnings` SHALL contain `"confidence_increased_after_removal"`

#### Scenario: Class confidence distribution overrides the scalar confidence

- **WHEN** the post-removal result provides `class_confidences = {"UP": 0.42, "DOWN": 0.50, "HOLD": 0.08}` and the original prediction is `"DOWN"`
- **THEN** `confidence_after_removal` SHALL equal `0.50`
- **AND** `confidence_drop` SHALL equal `original_confidence - 0.50`

---

### Requirement: Produce Faithfulness Report with Composite Score and Verdict

The system SHALL produce a `FaithfulnessReport` containing `temporal_validity`, `evidence_support`, `confidence_drop`, `faithfulness_score`, `verdict`, the three warning lists, and the `per_evidence_results` breakdown.

#### Scenario: A valid faithful candidate produces a high score and a strong verdict

- **WHEN** `temporal_validity = 1.0`, `evidence_support = 1.0`, and `confidence_drop >= 0.20` (with `prediction_after_removal == prediction`)
- **THEN** `faithfulness_score` SHALL be at least `0.85`
- **AND** `verdict` SHALL equal `"strong_faithful_candidate"`

#### Scenario: Temporal leakage produces the invalid verdict

- **WHEN** at least one cited evidence item has `news_time > forecast_time`
- **THEN** `temporal_validity` SHALL equal `0.0`
- **AND** `verdict` SHALL equal `"invalid_temporal_leakage"`
- **AND** `temporal_warnings` SHALL be non-empty

#### Scenario: Unsupported evidence produces the unsupported verdict

- **WHEN** `temporal_validity = 1.0` and `evidence_support < 0.5`
- **THEN** `verdict` SHALL equal `"unsupported_evidence"`
- **AND** `support_warnings` SHALL be non-empty

#### Scenario: Decorative explanation risk is detected when confidence_drop is near zero

- **WHEN** `temporal_validity = 1.0`, `evidence_support >= 0.5`, `prediction_after_removal == prediction`, and `confidence_drop < 0.05`
- **THEN** `verdict` SHALL equal `"decorative_explanation_risk"`
- **AND** `ablation_warnings` SHALL equal `[]`

#### Scenario: Composite score uses the documented weights

- **WHEN** `temporal_validity = 1.0`, `evidence_support = 1.0`, and `confidence_drop = 0.30`
- **THEN** `faithfulness_score` SHALL equal `1.0`
- **WHEN** `temporal_validity = 1.0`, `evidence_support = 1.0`, and `confidence_drop = 0.0`
- **THEN** `faithfulness_score` SHALL equal `0.65`

#### Scenario: Negative confidence_drop is clamped for the composite only

- **WHEN** `confidence_drop = -0.10` (and other metrics pass)
- **THEN** `confidence_drop` SHALL equal `-0.10` in the report
- **AND** `faithfulness_score` SHALL be computed with `normalized_drop = 0.0`

---

### Requirement: Export Batch Results as CSV and JSON

The system SHALL export faithfulness results for multiple predictions into a CSV file (per-row scalar fields) and an optional JSON file (full-fidelity records) that the dashboard can consume directly.

#### Scenario: Multiple forecast rows produce multiple faithfulness rows

- **WHEN** `FaithfulnessEvaluator.evaluate_batch` is called with a list of three reports
- **THEN** the resulting CSV SHALL contain exactly three data rows after the header
- **AND** the rows SHALL be in the same order as the input reports

#### Scenario: Export includes all required columns in the documented order

- **WHEN** `FaithfulnessEvaluator.evaluate_batch` writes a CSV file
- **THEN** the header row SHALL equal `FaithfulnessEvaluator.CSV_COLUMNS` in order
- **AND** every data row SHALL contain values for every column

#### Scenario: Warning fields are encoded as JSON in the warnings column

- **WHEN** a report has `temporal_warnings = ["LEAKAGE_E001"]` and `ablation_warnings = ["confidence_increased_after_removal"]`
- **THEN** the `warnings` column of the CSV row SHALL equal the JSON encoding of `["LEAKAGE_E001", "confidence_increased_after_removal"]`
- **AND** the JSON sibling SHALL contain the three structured warning lists verbatim

#### Scenario: Per-record evaluation errors are recorded but never abort the batch

- **WHEN** one report in the batch triggers a `FaithfulnessEvaluatorError` during `FaithfulnessEvaluator.evaluate_batch`
- **THEN** the function SHALL NOT raise
- **AND** the failing report SHALL be replaced by a row with `verdict = "unsupported_evidence"`
- **AND** the row's `warnings` column SHALL start with `"EVALUATION_ERROR: "`
