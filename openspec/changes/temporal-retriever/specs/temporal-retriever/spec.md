## ADDED Requirements

### Requirement: Temporal Retriever filters news by publication time

The system SHALL provide a Temporal Retriever module that accepts a `forecast_time` and a list of news items, and partitions the list into two disjoint groups: `valid_news` (items whose `news_time` is less than or equal to `forecast_time`) and `invalid_future_news` (items whose `news_time` is strictly greater than `forecast_time`). The module SHALL be implemented as deterministic, rule-based Python code with no use of ML, LLM, or external services.

#### Scenario: Past news is treated as valid

- **GIVEN** `forecast_time` is `"2025-03-12 09:00"` and a news item with `news_time` `"2025-03-11 08:30"`
- **WHEN** the Temporal Retriever runs
- **THEN** the news item appears in `valid_news`
- **AND** the news item does NOT appear in `invalid_future_news`

#### Scenario: News published exactly at forecast_time is valid

- **GIVEN** `forecast_time` is `"2025-03-12 09:00"` and a news item with `news_time` `"2025-03-12 09:00"`
- **WHEN** the Temporal Retriever runs
- **THEN** the news item appears in `valid_news`
- **AND** the news item does NOT appear in `invalid_future_news`

#### Scenario: News published strictly after forecast_time is invalid

- **GIVEN** `forecast_time` is `"2025-03-12 09:00"` and a news item with `news_time` `"2025-03-12 15:30"`
- **WHEN** the Temporal Retriever runs
- **THEN** the news item appears in `invalid_future_news`
- **AND** the news item does NOT appear in `valid_news`

#### Scenario: Mixed list preserves both groups separately

- **GIVEN** a news list containing one past item (`news_time` `"2025-03-11 08:30"`), one equal item (`news_time` `"2025-03-12 09:00"`), and one future item (`news_time` `"2025-03-12 15:30"`) relative to `forecast_time` `"2025-03-12 09:00"`
- **WHEN** the Temporal Retriever runs
- **THEN** `valid_news` contains exactly the past item and the equal item
- **AND** `invalid_future_news` contains exactly the future item
- **AND** the two output groups are disjoint (no item appears in both)

### Requirement: Temporal Retriever input schema

The Temporal Retriever SHALL accept an input object with the following fields:

- `ticker`: optional string; preserved in the output metadata if present, otherwise `None`.
- `forecast_time`: required datetime string in a supported format (ISO 8601 recommended, e.g. `"2025-03-12 09:00"` or `"2025-03-12T09:00:00"`).
- `news`: required array of news objects, where each news object contains:
  - `news_id`: required string (unique identifier of the news item).
  - `news_time`: required datetime string in a supported format.
  - `title`: optional string.
  - `text` or `news_text`: required string (the body of the news item; either field name is accepted).

The Temporal Retriever SHALL preserve every original field of every news item in the output (no fields are dropped or rewritten).

#### Scenario: All input fields are preserved in output

- **GIVEN** a news item `{"news_id": "n1", "news_time": "2025-03-11 08:30", "title": "Past headline", "text": "Past body", "extra_field": "extra_value"}` and `forecast_time` `"2025-03-12 09:00"`
- **WHEN** the Temporal Retriever runs
- **THEN** the output `valid_news` entry contains the same `news_id`, `news_time`, `title`, `text`, and `extra_field` values verbatim

### Requirement: Temporal Retriever output schema

The Temporal Retriever SHALL return an output object with the following fields:

- `ticker`: the input ticker (or `None` if not provided).
- `forecast_time`: the parsed `forecast_time` echoed back as a string.
- `valid_news`: array of news objects whose `news_time <= forecast_time`.
- `invalid_future_news`: array of news objects whose `news_time > forecast_time`.
- `valid_count`: integer count of `valid_news` items.
- `invalid_future_count`: integer count of `invalid_future_news` items.
- `total_count`: integer count of input news items.
- `temporal_validity`: float equal to `valid_count / total_count` when `total_count > 0`; otherwise `0.0`.
- `errors`: optional array of validation error objects describing items with missing or malformed `news_time` (may be empty).

#### Scenario: Counts and temporal_validity are reported correctly

- **GIVEN** a news list with 3 past items, 1 equal item, and 2 future items relative to `forecast_time` `"2025-03-12 09:00"` (total 6 items)
- **WHEN** the Temporal Retriever runs
- **THEN** `valid_count` is `4`
- **AND** `invalid_future_count` is `2`
- **AND** `total_count` is `6`
- **AND** `temporal_validity` is `4 / 6 ≈ 0.6667` (within `1e-9`)

#### Scenario: Empty input produces zero counts and 0.0 temporal_validity

- **GIVEN** `forecast_time` `"2025-03-12 09:00"` and an empty `news` list
- **WHEN** the Temporal Retriever runs
- **THEN** `valid_news` is an empty array
- **AND** `invalid_future_news` is an empty array
- **AND** `valid_count` is `0`
- **AND** `invalid_future_count` is `0`
- **AND** `total_count` is `0`
- **AND** `temporal_validity` is `0.0`
- **AND** no exception is raised

### Requirement: Datetime comparison rule

The Temporal Retriever SHALL parse `forecast_time` and each `news_time` into comparable timezone-aware datetime values when timezone information is present, and SHALL compare them using the rule `news_time <= forecast_time` for `valid_news` and `news_time > forecast_time` for `invalid_future_news`. If both timestamps carry the same timezone offset, they SHALL be compared directly. If only one timestamp carries timezone information, the implementation SHALL either reject the mismatch with a validation error or normalize to a common reference, as documented in `design.md`.

#### Scenario: Equal timestamps compare as valid

- **GIVEN** `forecast_time` `"2025-03-12 09:00"` and `news_time` `"2025-03-12 09:00"`
- **WHEN** the Temporal Retriever compares them
- **THEN** the comparison evaluates to `news_time <= forecast_time` (i.e. valid)

#### Scenario: Future timestamp compares as invalid

- **GIVEN** `forecast_time` `"2025-03-12 09:00"` and `news_time` `"2025-03-12 15:30"`
- **WHEN** the Temporal Retriever compares them
- **THEN** the comparison evaluates to `news_time > forecast_time` (i.e. invalid)

### Requirement: Edge cases are handled deterministically

The Temporal Retriever SHALL handle the following edge cases deterministically:

- `news_time` exactly equal to `forecast_time` → placed in `valid_news`.
- Empty news list → `valid_news` and `invalid_future_news` are empty; counts are `0`; `temporal_validity` is `0.0`.
- All news valid → `invalid_future_news` is empty; `valid_count == total_count`; `temporal_validity == 1.0`.
- All news invalid (all future) → `valid_news` is empty; `invalid_future_count == total_count`; `temporal_validity == 0.0`.
- Mixed valid and future → both groups populated, counts correct.
- Missing or malformed `news_time` → handled as documented in `design.md` (validation error raised, OR the item is placed in an error list and excluded from both groups).
- Timezone-aware timestamps → compared correctly when offsets match.
- Timezone-naive timestamps → interpreted as project-local time (or rejected) as documented in `design.md`.

#### Scenario: All-valid list produces temporal_validity of 1.0

- **GIVEN** a news list with 3 items all having `news_time <= forecast_time`
- **WHEN** the Temporal Retriever runs
- **THEN** `valid_count` is `3`
- **AND** `invalid_future_count` is `0`
- **AND** `temporal_validity` is `1.0`

#### Scenario: All-invalid list produces temporal_validity of 0.0

- **GIVEN** a news list with 3 items all having `news_time > forecast_time`
- **WHEN** the Temporal Retriever runs
- **THEN** `valid_count` is `0`
- **AND** `invalid_future_count` is `3`
- **AND** `temporal_validity` is `0.0`

#### Scenario: Malformed news_time is reported clearly

- **GIVEN** a news list with one item whose `news_time` is `null`, missing, or not a parseable datetime string
- **WHEN** the Temporal Retriever runs
- **THEN** the item is either excluded from both groups and a structured validation error is added to the output `errors` list, OR a clear `TemporalValidationError` exception is raised
- **AND** the chosen behavior SHALL be documented in `design.md`

### Requirement: Temporal leakage prevention is explicit

The Temporal Retriever SHALL guarantee that no news item with `news_time > forecast_time` can be returned inside `valid_news`. This guarantee is the core of temporal leakage prevention and SHALL be enforced by the implementation and verified by regression tests.

#### Scenario: Future news never leaks into valid_news (temporal leakage regression)

- **GIVEN** `forecast_time` `"2025-03-12 09:00"` and a news list with one item at `news_time` `"2025-03-12 15:30"` (6 hours in the future)
- **WHEN** the Temporal Retriever runs
- **THEN** the future item appears in `invalid_future_news`
- **AND** the future item is NOT present anywhere in `valid_news`
- **AND** no future item is silently dropped from the output (it MUST remain in `invalid_future_news` for audit and dashboard warning)

#### Scenario: 1-second-in-the-future news is treated as invalid

- **GIVEN** `forecast_time` `"2025-03-12 09:00:00"` and a news item with `news_time` `"2025-03-12 09:00:01"`
- **WHEN** the Temporal Retriever runs
- **THEN** the news item appears in `invalid_future_news`
- **AND** the news item does NOT appear in `valid_news`

### Requirement: Auditability and dashboard observability

The Temporal Retriever SHALL preserve every input news item in the output (either in `valid_news` or in `invalid_future_news`, or in `errors` for malformed items). The module SHALL NOT silently drop any item. Downstream modules and the future dashboard SHALL be able to inspect `invalid_future_news` to surface warnings when future news was filtered out.

#### Scenario: No news item is silently dropped

- **GIVEN** a news list with 5 items (any mix of past, equal, future, or malformed)
- **WHEN** the Temporal Retriever runs
- **THEN** the sum of `len(valid_news) + len(invalid_future_news) + len(errors)` equals `total_count`
- **AND** no item from the input is missing from the output

### Requirement: Determinism and simplicity

The Temporal Retriever SHALL be deterministic: identical inputs SHALL produce identical outputs. The module SHALL NOT use any ML model, LLM, network call, database, or external service. The implementation SHALL be readable by a student and SHALL fit in a single small Python module.

#### Scenario: Identical inputs produce identical outputs

- **GIVEN** the same input object (`forecast_time`, `ticker`, `news`) is provided twice
- **WHEN** the Temporal Retriever runs twice in succession
- **THEN** both outputs are equal field-by-field (including counts, group membership, and `temporal_validity`)
