# Forecast Model — Spec (Version 1)

This spec defines the behavior of the **Forecast Model** module in the Faithful Evidence-Centric Financial News Forecasting pipeline. The Forecast Model receives a list of **selected, valid evidence** (already filtered and classified by the upstream pipeline) and emits a single stock-movement prediction (`UP`, `DOWN`, or `HOLD`) with a deterministic confidence score, evidence counts, pro and counter evidence, a template-based rationale, and a warnings list.

Version 1 is **rule-based, deterministic, and traceable**. It does not use any LLM, FinBERT, transformer, logistic regression, deep-learning model, or external API. It does not read price data. It does not generate free-form rationale.

---

## Input Schema

The module SHALL accept a single forecast request with the following fields:

| Field           | Type   | Required | Description |
|-----------------|--------|----------|-------------|
| `sample_id`     | string | yes      | Stable identifier for the sample. Echoed in the response. |
| `ticker`        | string | yes      | Stock ticker the forecast is about. Echoed in the response. Not used as a filter. |
| `forecast_time` | string | yes      | Datetime string at which the forecast is made. Compared to each `evidence[].news_time`. |
| `evidence`      | list   | yes      | List of selected evidence items (see below). May be empty. |
| `label`         | string | no       | Ground-truth label (`UP` / `DOWN` / `HOLD`) for evaluation. **MUST NOT** be read by `predict`. |

Each `evidence` entry MUST contain:

| Field               | Type   | Required | Description |
|---------------------|--------|----------|-------------|
| `evidence_id`       | string | yes      | Stable identifier. Deduplication key. |
| `news_id`           | string | yes      | Stable identifier of the source news. |
| `news_time`         | string | yes      | Datetime string of publication. Compared to `forecast_time`. |
| `evidence_text`     | string | yes      | The matched phrase (preserved verbatim). |
| `polarity`          | string | yes      | One of `"positive"`, `"negative"`, `"neutral"`. |
| `expected_direction`| string | yes      | One of `"UP"`, `"DOWN"`, `"HOLD"`. The only input to voting. |
| `support_score`     | number | optional | Forwarded to output; not used in V1 scoring. |

The model MUST NOT read `news_text`, `title`, or any other raw-news field. The model MUST NOT read `label` during prediction.

---

## Output Schema

The module SHALL return a single result object with the following fields:

| Field                          | Type    | Description |
|--------------------------------|---------|-------------|
| `sample_id`                    | string  | Same as input. |
| `ticker`                       | string  | Same as input. |
| `forecast_time`                | string  | Same as input. |
| `prediction`                   | string  | One of `"UP"`, `"DOWN"`, `"HOLD"`. |
| `confidence`                   | number  | In `[0.5, 0.95]`. See *Confidence*. |
| `score`                        | integer | `positive_count - negative_count`. |
| `positive_count`               | integer | Count of items with `expected_direction = "UP"`. |
| `negative_count`               | integer | Count of items with `expected_direction = "DOWN"`. |
| `neutral_count`                | integer | Count of items with `expected_direction = "HOLD"`. |
| `total_evidence`               | integer | Count of items considered for scoring. |
| `directional_evidence_count`   | integer | `positive_count + negative_count`. |
| `evidence_strength`            | number  | `abs(score) / directional_evidence_count`, or `0.0` if `directional_evidence_count = 0`. |
| `conflict_ratio`               | number  | `min(positive_count, negative_count) / max(positive_count + negative_count, 1)`. |
| `pro_evidence`                 | list    | Items supporting the prediction. See *Pro / Counter Evidence*. Never `null` — `[]` when none. |
| `counter_evidence`             | list    | Items conflicting with the prediction. Never `null`. |
| `up_evidence`                  | list    | All items with `expected_direction = "UP"`. Never `null`. |
| `down_evidence`                | list    | All items with `expected_direction = "DOWN"`. Never `null`. |
| `neutral_evidence`             | list    | All items with `expected_direction = "HOLD"`. Never `null`. |
| `rationale`                    | string  | Template-based; see *Rationale*. Deterministic. |
| `warnings`                     | list    | Structured warning entries. Always present, may be empty. |
| `model_version`                | string  | MUST be the literal `"rule_based_v1"`. |

### Evidence Item (output)

Each output evidence item SHALL preserve the input fields (`evidence_id`, `news_id`, `news_time`, `evidence_text`, `polarity`, `expected_direction`, `support_score`) and SHALL NOT add a ground-truth `label` field.

### Warning Entry

Each entry in `warnings` SHALL be a JSON object with at least:

| Field          | Type   | Description |
|----------------|--------|-------------|
| `code`         | string | One of `TEMPORAL_LEAKAGE_BLOCKED`, `INVALID_EVIDENCE`, `DUPLICATE_EVIDENCE_ID`, `MALFORMED_NEWS_TIME`, `INPUT_ERROR`. |
| `evidence_id`  | string | The offending evidence ID, when applicable. |
| `message`      | string | Human-readable detail. |

---

## Voting Algorithm

The system SHALL compute the score and prediction as:

```
positive_count = |{ e : e.expected_direction == "UP" }|
negative_count = |{ e : e.expected_direction == "DOWN" }|
neutral_count  = |{ e : e.expected_direction == "HOLD" }|
score          = positive_count - negative_count

if score  > 0: prediction = "UP"
elif score < 0: prediction = "DOWN"
else:           prediction = "HOLD"
```

`score` is an integer. Neutral evidence does not contribute to the score. `directional_evidence_count = positive_count + negative_count`.

## Confidence

The system SHALL compute confidence as:

```
if directional_evidence_count == 0:
    confidence = 0.5
else:
    confidence = 0.5 + min(abs(score) * 0.1, 0.45)
    confidence = max(0.5, min(0.95, confidence))
```

`confidence` SHALL be in `[0.5, 0.95]`. The default formula is `0.5 + min(abs(score) * 0.1, 0.45)`. The alternative `abs(score) / total_evidence` MUST NOT be used as the default because it overstates confidence when there is a single piece of evidence. If the implementation documents an alternative, it SHALL be opt-in and clearly marked as non-default.

## Evidence Strength and Conflict Ratio

The system SHALL compute:

```
evidence_strength = abs(score) / directional_evidence_count   (0.0 when denominator is 0)
conflict_ratio    = min(positive_count, negative_count)
                    / max(positive_count + negative_count, 1)
```

`evidence_strength = 1.0` means every directional evidence item points the same way. `conflict_ratio = 0.5` means directional evidence is perfectly balanced. Both values are in `[0.0, 1.0]`.

## Pro / Counter Evidence

The system SHALL populate `pro_evidence` and `counter_evidence` as follows:

| `prediction` | `pro_evidence`           | `counter_evidence`       |
|--------------|--------------------------|--------------------------|
| `UP`         | items with `expected_direction = "UP"`   | items with `expected_direction = "DOWN"` |
| `DOWN`       | items with `expected_direction = "DOWN"` | items with `expected_direction = "UP"`   |
| `HOLD`       | `[]`                     | `[]`                     |

The three raw groups (`up_evidence`, `down_evidence`, `neutral_evidence`) SHALL always be populated regardless of `prediction`. All four evidence lists SHALL be sorted by `evidence_id` ascending.

## Rationale

The rationale SHALL be selected from a fixed set of templates. The implementation MUST NOT call any LLM. The system SHALL use the following templates:

| Branch | Template |
|--------|----------|
| `prediction = UP`   | `"Prediction UP because positive evidence count ({positive_count}) is greater than negative evidence count ({negative_count})."` |
| `prediction = DOWN` | `"Prediction DOWN because negative evidence count ({negative_count}) is greater than positive evidence count ({positive_count})."` |
| `prediction = HOLD`, `directional_evidence_count == 0` | `"Prediction HOLD because positive and negative evidence are balanced or no valid directional evidence is available."` |
| `prediction = HOLD`, `directional_evidence_count > 0` | `"Prediction HOLD because positive and negative evidence are balanced."` |

`{positive_count}` and `{negative_count}` SHALL be replaced with their integer values from the same result.

## Temporal Safety

The system SHALL defensively validate each evidence `news_time` against `forecast_time`:

- If `news_time > forecast_time` (strict inequality), the item SHALL be excluded from scoring, SHALL NOT appear in any evidence list, and the result SHALL include a `TEMPORAL_LEAKAGE_BLOCKED` warning with the offending `evidence_id`.
- If `news_time == forecast_time`, the item SHALL be included normally.
- If `news_time` is missing or unparseable, the item SHALL be treated as not-future and a `MALFORMED_NEWS_TIME` warning SHALL be emitted.
- If `forecast_time` is missing or unparseable, the system SHALL raise a typed error and SHALL NOT return a partial response.

The system SHALL use the same UTC-naive normalization used by the Temporal Retriever (naive timestamps interpreted as UTC) when comparing datetimes.

## Defensive Handling of Bad Evidence

The system SHALL handle the following conditions without aborting the batch (default `strict = False`):

- A missing or non-`{UP, DOWN, HOLD}` `expected_direction` value SHALL cause the item to be ignored and SHALL emit an `INVALID_EVIDENCE` warning.
- A duplicate `evidence_id` SHALL keep the first occurrence; subsequent occurrences SHALL be dropped and reported as `DUPLICATE_EVIDENCE_ID` warnings.
- A missing or unparseable `news_time` SHALL be treated as not-future and SHALL emit a `MALFORMED_NEWS_TIME` warning.

When `strict = True`, an `INVALID_EVIDENCE` condition SHALL raise a typed error instead of being skipped. `TEMPORAL_LEAKAGE_BLOCKED` and `DUPLICATE_EVIDENCE_ID` are NEVER raised; they are always warnings.

## Faithfulness Support

The system SHALL expose a `predict_without_evidence(input_data, removed_evidence_ids) -> ForecastResult` method that runs the same algorithm as `predict` after filtering out the items whose `evidence_id` is in `removed_evidence_ids`. The result SHALL include `prediction`, `confidence`, `score`, and evidence counts so the Faithfulness Evaluator can compute:

```
confidence_drop = original.confidence - reduced.confidence
```

The system MUST NOT raise when `removed_evidence_ids` is empty or when none of the IDs match; in those cases the function behaves exactly like `predict`.

## Batch API

The system SHALL expose `predict_batch(records, *, output_csv_path=None) -> list[ForecastResult]` that:

- Iterates `records` in input order and calls `predict` on each.
- Returns one result per input record, in input order.
- When `output_csv_path` is provided, writes the per-row scalar fields (`sample_id`, `ticker`, `forecast_time`, `prediction`, `confidence`, `score`, `positive_count`, `negative_count`, `neutral_count`, `total_evidence`, `directional_evidence_count`, `evidence_strength`, `conflict_ratio`, `label`, `model_version`) as a CSV. The default `output_csv_path` SHALL be `outputs/prediction_results.csv`.
- A record that raises a typed error SHALL be caught, replaced with a default result (`prediction = "HOLD"`, `confidence = 0.5`, evidence counts zero), and the result SHALL include an `INPUT_ERROR` warning. The batch never raises.

The system SHALL expose `compute_accuracy_and_confusion(results, *, label_key="label") -> dict` that:

- Accepts a list of result dicts (each MUST carry `label` or be paired with its input record).
- Returns `{ "accuracy": float, "confusion_matrix": {"labels": ["UP","DOWN","HOLD"], "matrix": [[...]]}, "per_class": {...}, "n_samples": int }`.
- A 3×3 confusion matrix is built with rows = predicted, columns = actual, in the order `["UP", "DOWN", "HOLD"]`.
- For an empty input list, returns `n_samples = 0`, `accuracy = 0.0`, and an all-zero matrix. For a non-empty input where every record is missing a label, the function SHALL raise `ValueError` (defensive default against a misconfigured pipeline).

## Determinism

The system SHALL be deterministic. Identical inputs SHALL produce identical outputs, including the order of items in every evidence list, the rationale string, the warnings list, and `model_version`. The system SHALL NOT introduce randomness, timestamps, or non-deterministic ordering.

## Model Version

Every result SHALL include `model_version = "rule_based_v1"`. Downstream consumers MAY filter by this string.

---

## ADDED Requirements

### Requirement: The Forecast Model produces a UP/DOWN/HOLD prediction from selected evidence

The system SHALL compute a stock-movement prediction (`UP`, `DOWN`, or `HOLD`) from the input `evidence` list using a deterministic, rule-based voting algorithm. The system SHALL NOT read raw `news_text` or any other raw-news field. The system SHALL NOT call any LLM, FinBERT, transformer model, logistic regression, deep-learning model, or external API.

#### Scenario: Predict UP from positive-dominant evidence

- **WHEN** the input `evidence` list contains 3 items with `expected_direction = "UP"` and 1 item with `expected_direction = "DOWN"`
- **THEN** `prediction` SHALL equal `"UP"`
- **AND** `score` SHALL equal `2`
- **AND** `confidence` SHALL equal `0.7`
- **AND** `positive_count` SHALL equal `3`
- **AND** `negative_count` SHALL equal `1`
- **AND** `directional_evidence_count` SHALL equal `4`
- **AND** `evidence_strength` SHALL equal `0.5`
- **AND** `conflict_ratio` SHALL equal `0.25`
- **AND** `pro_evidence` SHALL contain the 3 UP items
- **AND** `counter_evidence` SHALL contain the 1 DOWN item
- **AND** `rationale` SHALL equal `"Prediction UP because positive evidence count (3) is greater than negative evidence count (1)."`
- **AND** `warnings` SHALL equal `[]`
- **AND** `model_version` SHALL equal `"rule_based_v1"`

#### Scenario: Predict DOWN from negative-dominant evidence

- **WHEN** the input `evidence` list contains 1 item with `expected_direction = "UP"` and 3 items with `expected_direction = "DOWN"`
- **THEN** `prediction` SHALL equal `"DOWN"`
- **AND** `score` SHALL equal `-2`
- **AND** `confidence` SHALL equal `0.7`
- **AND** `rationale` SHALL equal `"Prediction DOWN because negative evidence count (3) is greater than positive evidence count (1)."`

#### Scenario: Predict HOLD from balanced evidence

- **WHEN** the input `evidence` list contains 2 items with `expected_direction = "UP"` and 2 items with `expected_direction = "DOWN"`
- **THEN** `prediction` SHALL equal `"HOLD"`
- **AND** `score` SHALL equal `0`
- **AND** `confidence` SHALL equal `0.5`
- **AND** `rationale` SHALL equal `"Prediction HOLD because positive and negative evidence are balanced."`
- **AND** `positive_count` SHALL equal `2`
- **AND** `negative_count` SHALL equal `2`

#### Scenario: Predict HOLD from neutral-only evidence

- **WHEN** the input `evidence` list contains only items with `expected_direction = "HOLD"` (e.g., 3 HOLD items, no UP and no DOWN)
- **THEN** `prediction` SHALL equal `"HOLD"`
- **AND** `score` SHALL equal `0`
- **AND** `confidence` SHALL equal `0.5`
- **AND** `directional_evidence_count` SHALL equal `0`
- **AND** `evidence_strength` SHALL equal `0.0`
- **AND** `neutral_count` SHALL equal `3`
- **AND** `up_evidence` SHALL equal `[]`
- **AND** `down_evidence` SHALL equal `[]`
- **AND** `neutral_evidence` SHALL contain the 3 HOLD items
- **AND** `pro_evidence` SHALL equal `[]`
- **AND** `counter_evidence` SHALL equal `[]`
- **AND** `rationale` SHALL equal `"Prediction HOLD because positive and negative evidence are balanced or no valid directional evidence is available."`

#### Scenario: Predict HOLD from empty evidence

- **WHEN** the input `evidence` list is empty (`[]`)
- **THEN** `prediction` SHALL equal `"HOLD"`
- **AND** `score` SHALL equal `0`
- **AND** `confidence` SHALL equal `0.5`
- **AND** `total_evidence` SHALL equal `0`
- **AND** `positive_count` SHALL equal `0`
- **AND** `negative_count` SHALL equal `0`
- **AND** `neutral_count` SHALL equal `0`
- **AND** `evidence_strength` SHALL equal `0.0`
- **AND** `conflict_ratio` SHALL equal `0.0`
- **AND** `pro_evidence`, `counter_evidence`, `up_evidence`, `down_evidence`, `neutral_evidence` SHALL each equal `[]`
- **AND** `rationale` SHALL equal `"Prediction HOLD because positive and negative evidence are balanced or no valid directional evidence is available."`
- **AND** `warnings` SHALL equal `[]`

### Requirement: Defensive validation against future evidence

The system SHALL defensively compare each evidence `news_time` to the request's `forecast_time`. Evidence with `news_time > forecast_time` SHALL NOT be used for scoring and SHALL produce a `TEMPORAL_LEAKAGE_BLOCKED` warning.

#### Scenario: Block future evidence with a warning

- **WHEN** `forecast_time` is `"2025-03-12 09:00"`
- **AND** the input `evidence` list contains one item with `news_time = "2025-03-12 15:30"` and `expected_direction = "UP"`
- **THEN** that item SHALL NOT be counted in `positive_count` or `score`
- **AND** that item SHALL NOT appear in `up_evidence`, `pro_evidence`, or any other evidence list
- **AND** `warnings` SHALL contain an entry with `code = "TEMPORAL_LEAKAGE_BLOCKED"` whose `evidence_id` matches the offending item
- **AND** if all other items are absent, `prediction` SHALL equal `"HOLD"`

#### Scenario: Equal-timestamp evidence is not blocked

- **WHEN** `forecast_time` is `"2025-03-12 09:00"`
- **AND** the input `evidence` list contains one item with `news_time = "2025-03-12 09:00"`
- **THEN** the item SHALL be included normally
- **AND** `warnings` SHALL NOT contain a `TEMPORAL_LEAKAGE_BLOCKED` entry for that item

#### Scenario: Missing news_time is treated as not-future

- **WHEN** an evidence item is missing `news_time` (or it is unparseable)
- **THEN** the item SHALL be included normally
- **AND** `warnings` SHALL contain a `MALFORMED_NEWS_TIME` entry for that item

### Requirement: Faithfulness support through evidence removal

The system SHALL expose a `predict_without_evidence` method that re-runs the same algorithm after filtering out one or more cited `evidence_id`s. The result SHALL include all standard output fields so the Faithfulness Evaluator can compute `confidence_drop = original.confidence - reduced.confidence`.

#### Scenario: Removing all pro evidence drops confidence

- **WHEN** an original prediction has `prediction = "UP"`, `confidence = 0.8`, and 3 UP items
- **AND** `predict_without_evidence` is called with `removed_evidence_ids` containing those 3 UP IDs
- **THEN** the new result SHALL be returned with the same output schema
- **AND** the new result SHALL have `prediction` re-computed from the remaining items
- **AND** the new `confidence` SHALL be lower than the original `confidence`
- **AND** the Faithfulness Evaluator SHALL be able to compute `confidence_drop` as a non-negative number

#### Scenario: Empty removed_evidence_ids behaves like predict

- **WHEN** `predict_without_evidence` is called with `removed_evidence_ids = []`
- **THEN** the result SHALL be byte-equal to `predict(input_data)` on the same input

#### Scenario: removed_evidence_ids that do not match any item behaves like predict

- **WHEN** `predict_without_evidence` is called with `removed_evidence_ids` that contain no `evidence_id` present in the input
- **THEN** the result SHALL be byte-equal to `predict(input_data)` on the same input

### Requirement: Template-based rationale

The system SHALL generate the `rationale` string from a fixed set of templates (one per branch). The system SHALL NOT generate free-form rationale and SHALL NOT call any LLM.

#### Scenario: UP rationale includes both counts

- **WHEN** `prediction = "UP"` and `positive_count = 3` and `negative_count = 1`
- **THEN** `rationale` SHALL equal `"Prediction UP because positive evidence count (3) is greater than negative evidence count (1)."`

#### Scenario: DOWN rationale includes both counts

- **WHEN** `prediction = "DOWN"` and `negative_count = 3` and `positive_count = 1`
- **THEN** `rationale` SHALL equal `"Prediction DOWN because negative evidence count (3) is greater than positive evidence count (1)."`

#### Scenario: HOLD rationale does not invent external reasons

- **WHEN** `prediction = "HOLD"`
- **THEN** `rationale` SHALL be one of the two HOLD templates listed in *Rationale*
- **AND** `rationale` SHALL NOT mention any external reason not present in the evidence (e.g., market conditions, macro events, prior sessions)

### Requirement: Batch evaluation output

The system SHALL expose `predict_batch` and `compute_accuracy_and_confusion` so the dataset can be evaluated end-to-end.

#### Scenario: Batch outputs one result per input

- **WHEN** `predict_batch` is called with 5 input records
- **THEN** the returned list SHALL contain exactly 5 `ForecastResult` dicts in input order
- **AND** the result list SHALL be JSON-serializable

#### Scenario: CSV file is written with per-row scalar fields

- **WHEN** `predict_batch` is called with a non-empty `records` list and an `output_csv_path`
- **THEN** the CSV file SHALL exist at the given path
- **AND** the CSV SHALL have one row per record
- **AND** the CSV header SHALL include `sample_id`, `ticker`, `forecast_time`, `prediction`, `confidence`, `score`, `positive_count`, `negative_count`, `neutral_count`, `total_evidence`, `directional_evidence_count`, `evidence_strength`, `conflict_ratio`, `label`, `model_version`

#### Scenario: Confusion matrix supports accuracy and per-class metrics

- **WHEN** `compute_accuracy_and_confusion` is called with a list of result dicts each carrying a `label`
- **THEN** the returned object SHALL include `accuracy` in `[0.0, 1.0]`
- **AND** the returned `confusion_matrix.matrix` SHALL be 3×3
- **AND** the returned `per_class` object SHALL include `precision`, `recall`, `f1`, and `support` for each of `UP`, `DOWN`, `HOLD`
- **AND** the returned `n_samples` SHALL equal the number of input results with a non-null `label`

### Requirement: Defensive handling of malformed evidence

The system SHALL be resilient to one malformed evidence item in a batch and SHALL NOT abort the prediction because of a single bad item. The system SHALL deduplicate evidence by `evidence_id`, keep the first occurrence, and report subsequent occurrences as `DUPLICATE_EVIDENCE_ID` warnings.

#### Scenario: Duplicate evidence_id is deduplicated

- **WHEN** the input `evidence` list contains two items with the same `evidence_id = "N001_E001"`
- **THEN** only the first item SHALL be counted in the score and in the evidence lists
- **AND** `warnings` SHALL contain a `DUPLICATE_EVIDENCE_ID` entry for the second occurrence

#### Scenario: Invalid expected_direction is ignored with a warning

- **WHEN** an evidence item has `expected_direction = "INVALID"`
- **THEN** the item SHALL NOT be counted in the score
- **AND** the item SHALL NOT appear in any evidence list
- **AND** `warnings` SHALL contain an `INVALID_EVIDENCE` entry for that item
- **AND** the system SHALL NOT raise an exception (default `strict = False`)

#### Scenario: strict mode raises on invalid expected_direction

- **WHEN** `strict = True` and an evidence item has `expected_direction = "INVALID"`
- **THEN** the system SHALL raise a typed error and SHALL NOT return a partial response

#### Scenario: One malformed item does not abort the batch

- **WHEN** the input `evidence` list contains one well-formed item and one item with `expected_direction = "INVALID"`
- **THEN** the well-formed item SHALL be scored normally
- **AND** the result SHALL include an `INVALID_EVIDENCE` warning for the bad item
- **AND** the system SHALL NOT raise an exception

### Requirement: Determinism and reproducibility

The system SHALL be deterministic. Given identical inputs, the system SHALL produce byte-equal outputs (after JSON normalization), including the rationale string, the warnings list, and the order of items within every evidence list.

#### Scenario: Identical inputs produce identical outputs

- **WHEN** the same input record is provided twice to `predict`
- **THEN** the two result dicts SHALL be field-by-field equal
- **AND** the rationale string SHALL be byte-equal
- **AND** the order of items in `pro_evidence`, `counter_evidence`, `up_evidence`, `down_evidence`, and `neutral_evidence` SHALL be byte-equal

#### Scenario: No randomness or external calls

- **WHEN** the system runs in an offline environment
- **THEN** it SHALL produce a complete, correct response without contacting any external service
- **AND** the response SHALL NOT contain timestamps, random IDs, or non-deterministic ordering
