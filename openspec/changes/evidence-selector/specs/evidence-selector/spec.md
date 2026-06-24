# Evidence Selector — Spec (Version 1)

This spec defines the behavior of the **Evidence Selector** module in the Faithful Evidence-Centric Financial News Forecasting pipeline. The Evidence Selector receives a forecast prediction (UP / DOWN / HOLD) and a list of evidence candidates produced by the Evidence Extractor, and classifies each candidate as `pro_evidence`, `counterevidence`, or `neutral_evidence` relative to the prediction.

Version 1 is **rule-based, deterministic, and testable**. It does not use any LLM, FinBERT, transformer, or external NLP model.

---

## Input Schema

The module SHALL accept a single prediction request with the following fields:

| Field                 | Type   | Required | Description |
|-----------------------|--------|----------|-------------|
| `ticker`              | string | yes      | Stock ticker the prediction is about. Echoed in the response. |
| `forecast_time`       | string | yes      | Datetime string at which the forecast is made. Echoed in the response. |
| `prediction`          | string | yes      | One of `"UP"`, `"DOWN"`, `"HOLD"`. |
| `confidence`          | number | yes      | Forecast model confidence. Echoed in the response. |
| `evidence_candidates` | list   | yes      | List of evidence candidate objects (see below). May be empty. |

Each `evidence_candidates` entry MUST contain:

| Field               | Type   | Required | Description |
|---------------------|--------|----------|-------------|
| `news_id`           | string | yes      | Stable identifier of the news item. |
| `ticker`            | string | yes      | Stock ticker (preserved verbatim). |
| `news_time`         | string | yes      | Datetime string of publication. Compared against `forecast_time` for future-evidence protection. |
| `evidence_text`     | string | yes      | The matched phrase (preserved verbatim). |
| `polarity`          | string | yes      | One of `"positive"`, `"negative"`, `"neutral"`. |
| `expected_direction`| string | yes      | One of `"UP"`, `"DOWN"`, `"HOLD"`. The key input to the classification table. |
| `extractor_score`   | number | yes      | Score produced by the Evidence Extractor; used as `selector_score` in V1. |

Extra fields on a candidate (including a `label` or `ground_truth_label`) SHALL be ignored for classification and SHALL NOT be read.

---

## Output Schema

The module SHALL return a single result object with the following fields:

| Field                     | Type    | Description |
|---------------------------|---------|-------------|
| `ticker`                  | string  | Same as input. |
| `forecast_time`           | string  | Same as input. |
| `prediction`              | string  | Same as input. |
| `confidence`              | number  | Same as input. |
| `pro_evidence`            | list    | List of evidence items that support the prediction. Never `null` — empty list when none. |
| `counterevidence`         | list    | List of evidence items that conflict with the prediction. Never `null`. |
| `neutral_evidence`        | list    | List of evidence items that are neither clearly supportive nor conflicting. Never `null`. |
| `invalid_future_evidence` | list    | List of candidates whose `news_time > forecast_time`. Always present, possibly empty. |
| `summary`                 | object  | Counts and `counterevidence_ratio` (see below). |
| `selection_method`        | string  | MUST be the literal `"rule_based"`. |

### Evidence Item (output)

Each output evidence item SHALL contain the following fields:

| Field               | Type   | Description |
|---------------------|--------|-------------|
| `news_id`           | string | Same as input candidate. |
| `ticker`            | string | Same as input candidate. |
| `news_time`         | string | Same as input candidate. |
| `evidence_text`     | string | Same as input candidate. |
| `polarity`          | string | Same as input candidate. |
| `expected_direction`| string | Same as input candidate. |
| `extractor_score`   | number | Same as input candidate. |
| `selector_label`    | string | One of `"pro"`, `"counter"`, `"neutral"`. |
| `selector_score`    | number | The candidate's `extractor_score` in V1. |
| `reason`            | string | Human-readable explanation of the classification (see *Classification Reason Table*). |

### Summary Object

| Field                   | Type    | Description |
|-------------------------|---------|-------------|
| `pro_count`             | integer | Count of items in `pro_evidence` BEFORE `top_k_pro` truncation. |
| `counter_count`         | integer | Count of items in `counterevidence` BEFORE `top_k_counter` truncation. |
| `neutral_count`         | integer | Count of items in `neutral_evidence` BEFORE `top_k_neutral` truncation. |
| `has_counterevidence`   | boolean | `true` iff `counter_count > 0`. |
| `counterevidence_ratio` | number  | `counter_count / (pro_count + counter_count)` when the denominator is positive; otherwise `0.0`. |

### Invalid Future Evidence Item

| Field      | Type   | Description |
|------------|--------|-------------|
| `news_id`  | string | The candidate's `news_id`. |
| `news_time`| string | The candidate's `news_time` (verbatim). |
| `reason`   | string | MUST be `"future_evidence"`. |

---

## Classification Table

The system SHALL apply the following fixed classification:

| `prediction` | `evidence.expected_direction` | `selector_label` |
|--------------|-------------------------------|------------------|
| `UP`         | `UP`                          | `pro`            |
| `UP`         | `DOWN`                        | `counter`        |
| `UP`         | `HOLD`                        | `neutral`        |
| `DOWN`       | `DOWN`                        | `pro`            |
| `DOWN`       | `UP`                          | `counter`        |
| `DOWN`       | `HOLD`                        | `neutral`        |
| `HOLD`       | `HOLD`                        | `pro`            |
| `HOLD`       | `UP`                          | `counter`        |
| `HOLD`       | `DOWN`                        | `counter`        |

### Classification Reason Table

| `prediction` | `expected_direction` | `reason`                                                                  |
|--------------|---------------------|---------------------------------------------------------------------------|
| `UP`         | `UP`                | `"Evidence expected direction UP matches prediction UP"`                   |
| `UP`         | `DOWN`              | `"Evidence expected direction DOWN conflicts with prediction UP"`          |
| `UP`         | `HOLD`              | `"Evidence expected direction HOLD is not directional for prediction UP"` |
| `DOWN`       | `DOWN`              | `"Evidence expected direction DOWN matches prediction DOWN"`               |
| `DOWN`       | `UP`                | `"Evidence expected direction UP conflicts with prediction DOWN"`         |
| `DOWN`       | `HOLD`              | `"Evidence expected direction HOLD is not directional for prediction DOWN"`|
| `HOLD`       | `HOLD`              | `"Evidence expected direction HOLD matches prediction HOLD"`               |
| `HOLD`       | `UP`                | `"Evidence expected direction UP conflicts with prediction HOLD"`          |
| `HOLD`       | `DOWN`              | `"Evidence expected direction DOWN conflicts with prediction HOLD"`        |

---

## ADDED Requirements

### Requirement: The Evidence Selector classifies evidence candidates by prediction and expected direction

The system SHALL classify each evidence candidate into exactly one of `pro_evidence`, `counterevidence`, or `neutral_evidence` according to the **Classification Table**. The classification SHALL be based solely on the candidate's `expected_direction` and the request's `prediction`; the system MUST NOT read a ground-truth label, an `actual` field, or any other signal that would constitute label leakage.

#### Scenario: Classify pro evidence for UP prediction

- **WHEN** the request's `prediction` is `"UP"` and a candidate's `expected_direction` is `"UP"`
- **THEN** the candidate SHALL appear in `pro_evidence` with `selector_label = "pro"`
- **AND** the item's `reason` SHALL equal `"Evidence expected direction UP matches prediction UP"`

#### Scenario: Classify counterevidence for UP prediction

- **WHEN** the request's `prediction` is `"UP"` and a candidate's `expected_direction` is `"DOWN"`
- **THEN** the candidate SHALL appear in `counterevidence` with `selector_label = "counter"`
- **AND** the item's `reason` SHALL equal `"Evidence expected direction DOWN conflicts with prediction UP"`

#### Scenario: Classify pro evidence for DOWN prediction

- **WHEN** the request's `prediction` is `"DOWN"` and a candidate's `expected_direction` is `"DOWN"`
- **THEN** the candidate SHALL appear in `pro_evidence` with `selector_label = "pro"`
- **AND** the item's `reason` SHALL equal `"Evidence expected direction DOWN matches prediction DOWN"`

#### Scenario: Classify counterevidence for DOWN prediction

- **WHEN** the request's `prediction` is `"DOWN"` and a candidate's `expected_direction` is `"UP"`
- **THEN** the candidate SHALL appear in `counterevidence` with `selector_label = "counter"`
- **AND** the item's `reason` SHALL equal `"Evidence expected direction UP conflicts with prediction DOWN"`

#### Scenario: Classify neutral evidence for directional prediction

- **WHEN** the request's `prediction` is `"UP"` (or `"DOWN"`) and a candidate's `expected_direction` is `"HOLD"`
- **THEN** the candidate SHALL appear in `neutral_evidence` with `selector_label = "neutral"`
- **AND** the item's `reason` SHALL contain the literal `"HOLD is not directional for prediction"`

#### Scenario: Classify pro evidence for HOLD prediction

- **WHEN** the request's `prediction` is `"HOLD"` and a candidate's `expected_direction` is `"HOLD"`
- **THEN** the candidate SHALL appear in `pro_evidence` with `selector_label = "pro"`
- **AND** the item's `reason` SHALL equal `"Evidence expected direction HOLD matches prediction HOLD"`

#### Scenario: Classify counterevidence for HOLD prediction with directional evidence

- **WHEN** the request's `prediction` is `"HOLD"` and a candidate's `expected_direction` is `"UP"` or `"DOWN"`
- **THEN** the candidate SHALL appear in `counterevidence` with `selector_label = "counter"`
- **AND** the item's `reason` SHALL contain the literal `"conflicts with prediction HOLD"`

### Requirement: Output evidence groups are sorted by selector_score descending

The system SHALL sort each of `pro_evidence`, `counterevidence`, and `neutral_evidence` by `selector_score` descending. Ties SHALL be broken by the order the items appeared in the input list (stable sort). For V1, `selector_score` SHALL equal the candidate's `extractor_score`.

#### Scenario: Ranking by selector_score descending

- **WHEN** the request's `evidence_candidates` contains three items in the same group with `extractor_score` values `0.5`, `0.9`, and `0.7`
- **THEN** the output group's items SHALL appear in the order `0.9`, `0.7`, `0.5`

#### Scenario: Stable sort on equal selector_score

- **WHEN** the request's `evidence_candidates` contains two items in the same group with equal `extractor_score`
- **THEN** the output group's items SHALL appear in the same relative order as in the input

### Requirement: Per-group top_k truncation

The system SHALL accept an optional `top_k_pro`, `top_k_counter`, and `top_k_neutral` parameter (default values: `3`, `3`, `3`). The system SHALL truncate each output group to its respective `top_k` cap AFTER sorting. The `summary` counts SHALL reflect the FULL pre-truncation counts so the dashboard can show "5 of 12 shown" affordances.

#### Scenario: top_k counter caps the counterevidence list

- **WHEN** the request classifies 5 candidates as counterevidence and `top_k_counter = 3`
- **THEN** `counterevidence` SHALL contain at most 3 items (the highest-scoring 3)
- **AND** `summary.counter_count` SHALL equal 5 (the pre-truncation count)

#### Scenario: top_k defaults when not specified

- **WHEN** the request omits `top_k_pro`, `top_k_counter`, and `top_k_neutral`
- **THEN** the system SHALL use the default values `3`, `3`, `3` respectively

### Requirement: Summary metrics

The system SHALL compute the following `summary` fields:

- `pro_count = len(pro_evidence)` BEFORE truncation.
- `counter_count = len(counterevidence)` BEFORE truncation.
- `neutral_count = len(neutral_evidence)` BEFORE truncation.
- `has_counterevidence = (counter_count > 0)`.
- `counterevidence_ratio = counter_count / (pro_count + counter_count)` when `pro_count + counter_count > 0`; otherwise `0.0`.

#### Scenario: counterevidence_ratio with both pro and counter

- **WHEN** `pro_count = 3` and `counter_count = 1`
- **THEN** `summary.counterevidence_ratio` SHALL equal `0.25`

#### Scenario: counterevidence_ratio with no pro or counter

- **WHEN** `pro_count = 0` and `counter_count = 0`
- **THEN** `summary.counterevidence_ratio` SHALL equal `0.0`
- **AND** the system SHALL NOT raise a division-by-zero error

#### Scenario: has_counterevidence is true when at least one counter exists

- **WHEN** at least one candidate is classified as counterevidence
- **THEN** `summary.has_counterevidence` SHALL equal `true`

#### Scenario: has_counterevidence is false when no counter exists

- **WHEN** no candidate is classified as counterevidence
- **THEN** `summary.has_counterevidence` SHALL equal `false`

### Requirement: Empty evidence_candidates

The system SHALL return empty `pro_evidence`, `counterevidence`, and `neutral_evidence` arrays (NOT `null`) when `evidence_candidates` is empty. All `summary` counts SHALL be `0`; `has_counterevidence` SHALL be `false`; `counterevidence_ratio` SHALL be `0.0`. The system SHALL NOT raise an exception.

#### Scenario: Empty evidence list returns empty groups and zero counts

- **WHEN** the request's `evidence_candidates` is `[]`
- **THEN** `pro_evidence` SHALL equal `[]`
- **AND** `counterevidence` SHALL equal `[]`
- **AND** `neutral_evidence` SHALL equal `[]`
- **AND** `summary.pro_count = 0`, `summary.counter_count = 0`, `summary.neutral_count = 0`
- **AND** `summary.has_counterevidence = false`
- **AND** `summary.counterevidence_ratio = 0.0`

### Requirement: Future-evidence protection

The system SHALL compare each candidate's `news_time` to the request's `forecast_time`. A candidate whose `news_time > forecast_time` SHALL NOT be placed in `pro_evidence`, `counterevidence`, or `neutral_evidence`. It SHALL be appended to `invalid_future_evidence` with `reason = "future_evidence"`. The `summary` counts SHALL exclude invalid-future items.

#### Scenario: Future evidence is flagged, not classified

- **WHEN** a candidate has `news_time` strictly greater than `forecast_time`
- **THEN** the candidate SHALL appear in `invalid_future_evidence` with `reason = "future_evidence"`
- **AND** the candidate SHALL NOT appear in `pro_evidence`, `counterevidence`, or `neutral_evidence`
- **AND** `summary.counter_count` (and all other counts) SHALL exclude it

#### Scenario: Equal-timestamp evidence is not future

- **WHEN** a candidate has `news_time` equal to `forecast_time`
- **THEN** the candidate SHALL be classified normally (it is not future)

#### Scenario: Missing or unparseable news_time is treated as not-future

- **WHEN** a candidate's `news_time` is missing, `null`, or not a parseable timestamp
- **THEN** the candidate SHALL be classified normally (defensive default; do not block the rest of the batch on a parse error)

### Requirement: Field preservation

The system SHALL preserve the following input fields on every output evidence item: `news_id`, `ticker`, `news_time`, `evidence_text`, `polarity`, `expected_direction`, and `extractor_score`. The system SHALL add `selector_label`, `selector_score`, and `reason` to each output evidence item. The system SHALL NOT add a ground-truth `label` field to the output.

#### Scenario: All input evidence fields are echoed in the output

- **WHEN** a candidate has `news_id = "N001"`, `ticker = "AAPL"`, `news_time = "..."`, `evidence_text = "..."`, `polarity = "positive"`, `expected_direction = "UP"`, `extractor_score = 0.9`
- **THEN** the corresponding output evidence item SHALL contain every one of those fields with the same values
- **AND** the output item SHALL also contain `selector_label`, `selector_score`, and `reason`

### Requirement: Determinism

The system SHALL be deterministic: identical input requests SHALL produce identical output objects field-by-field (including group membership, group ordering, summary counts, and `counterevidence_ratio`). The system SHALL NOT introduce randomness, timestamps, or non-deterministic ordering.

#### Scenario: Identical requests produce identical responses

- **WHEN** the same request is provided twice in succession
- **THEN** both responses SHALL be equal field-by-field, including the order of items within each group

### Requirement: Invalid inputs do not abort the batch

The system SHALL classify every well-formed candidate in the batch even when one or more candidates are malformed. A single bad candidate SHALL NOT prevent other candidates from being classified. The system SHALL raise a top-level error only for unrecoverable input problems (e.g., missing `prediction`, missing `evidence_candidates`).

#### Scenario: One bad candidate does not abort the batch

- **WHEN** the request contains one well-formed candidate and one candidate missing `expected_direction`
- **THEN** the well-formed candidate SHALL be classified normally
- **AND** the malformed candidate SHALL be reported in an `invalid_candidates` list with a `reason` describing the problem
- **AND** the system SHALL NOT raise an exception

#### Scenario: Top-level validation failures raise an error

- **WHEN** the request is missing `prediction`, or `prediction` is not one of `{"UP","DOWN","HOLD"}`
- **THEN** the system SHALL raise a typed error and SHALL NOT return a partial response

### Requirement: No ground-truth label leakage

The system SHALL classify evidence purely on `prediction` and `expected_direction`. The system MUST NOT read a `label`, `ground_truth_label`, `actual`, or any other field that would constitute label leakage from a held-out evaluation label. If such a field is present on a candidate, it SHALL be ignored for classification and SHALL NOT be echoed in the output.

#### Scenario: An extra label field on a candidate is ignored

- **WHEN** a candidate has an extra `ground_truth_label = "DOWN"` field and the request's `prediction` is `"UP"`
- **THEN** the candidate SHALL be classified solely on its `expected_direction` (not on `ground_truth_label`)
- **AND** the output evidence item SHALL NOT contain a `ground_truth_label` field

### Requirement: Empty groups are returned as empty arrays, not null

The system SHALL always return `pro_evidence`, `counterevidence`, `neutral_evidence`, and `invalid_future_evidence` as lists. The system SHALL return `[]` (an empty array), not `null`, when there are no items in a group.

#### Scenario: Empty groups are returned as empty arrays

- **WHEN** no candidates are classified as pro and the request's `prediction` is `"UP"`
- **THEN** `pro_evidence` SHALL equal `[]` (NOT `null`)

### Requirement: The system is rule-based

The system SHALL be implemented as a deterministic, rule-based pure function. The system SHALL NOT call any LLM, FinBERT, transformer model, network endpoint, database, or external service. The system SHALL be readable in a single small Python module and SHALL NOT require GPU, model downloads, or a network connection at runtime.

#### Scenario: No external dependencies

- **WHEN** the system runs in an offline environment
- **THEN** the system SHALL produce a complete, correct response without contacting any external service
