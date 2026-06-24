## ADDED Requirements

### Requirement: Temporal Retriever filters news by publication time

The system SHALL expose a Temporal Retriever service that accepts a `forecast_time` and a list of news items, and partitions the list into two non-overlapping groups: `valid_news` (items whose `news_time` is less than or equal to `forecast_time`) and `invalid_future_news` (items whose `news_time` is strictly greater than `forecast_time`). The service SHALL be implemented as a deterministic, rule-based, side-effect-free pure function with no ML, LLM, network, or external service dependencies.

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

#### Scenario: Mixed list partitions into non-overlapping groups

- **GIVEN** a news list containing one past item (`news_time` `"2025-03-11 08:30"`), one equal item (`news_time` `"2025-03-12 09:00"`), and one future item (`news_time` `"2025-03-12 15:30"`) relative to `forecast_time` `"2025-03-12 09:00"`
- **WHEN** the Temporal Retriever runs
- **THEN** `valid_news` contains exactly the past item and the equal item
- **AND** `invalid_future_news` contains exactly the future item
- **AND** the two output groups are non-overlapping (no item appears in both)

### Requirement: Temporal Retriever request schema

The Temporal Retriever SHALL accept a request payload with the following fields:

- `ticker`: optional string. When non-`None` and non-empty, the retriever SHALL treat it as a filter and keep only news items whose own `ticker` field equals this value (string-equality, case-sensitive). When `None` or empty, the ticker filter SHALL be skipped and every news item SHALL be passed through to the time filter. The value is echoed as-is in the response.
- `forecast_time`: required timestamp string in ISO 8601 format (e.g. `"2025-03-12 09:00"` or `"2025-03-12T09:00:00"`); naive values are interpreted as UTC.
- `news`: required array of news objects, where each news object contains:
  - `news_id`: required string (unique identifier of the news item).
  - `news_time`: required timestamp string in a supported format.
  - `ticker`: optional string. Required only when the request specifies a `ticker` filter; if missing or non-matching, the item is routed to `errors`.
  - `title`: optional string.
  - `text` or `news_text`: required string (the body of the news item; either field name is accepted and preserved as-is in the response).

The Temporal Retriever SHALL preserve every original field of every news item in the response — no field is dropped, renamed, or rewritten. The response is immutable from the caller's perspective.

#### Scenario: All input fields are preserved in output

- **GIVEN** a news item `{"news_id": "n1", "news_time": "2025-03-11 08:30", "title": "Past headline", "text": "Past body", "extra_field": "extra_value"}` and `forecast_time` `"2025-03-12 09:00"`
- **WHEN** the Temporal Retriever runs
- **THEN** the output `valid_news` entry contains the same `news_id`, `news_time`, `title`, `text`, and `extra_field` values verbatim

#### Scenario: news_text input is preserved as-is (no normalization)

- **GIVEN** a news item `{"news_id": "n2", "news_time": "2025-03-11 08:30", "news_text": "Body under the news_text key"}` and `forecast_time` `"2025-03-12 09:00"`
- **WHEN** the Temporal Retriever runs
- **THEN** the output `valid_news` entry contains the field `news_text` with the same value
- **AND** no synthetic `text` field is created

### Requirement: Temporal Retriever response schema

The Temporal Retriever SHALL return a response object with the following fields:

- `ticker`: the input `ticker` returned as-is, or `None` if the request omitted it.
- `forecast_time`: the input `forecast_time` returned as-is (no re-serialization, no offset injection).
- `valid_news`: array of news objects whose `news_time <= forecast_time`.
- `invalid_future_news`: array of news objects whose `news_time > forecast_time`.
- `valid_count`: integer count of `valid_news` items.
- `invalid_future_count`: integer count of `invalid_future_news` items.
- `total_count`: integer count of input news items (the request payload's `news` length, including items that land in `errors`).
- `temporal_validity`: float equal to `valid_count / total_count` when `total_count > 0`; otherwise `0.0`.
- `errors`: array of validation error objects; always present, empty array if every item parsed successfully AND matched the ticker filter. Each error has the shape `{"news_id": str, "reason": str, ...}` where `reason` is one of:
  - `"missing_or_malformed_news_time"` — `news_time` was missing, `None`, or not a parseable timestamp; the entry also carries `raw_value: str | None` echoing the unparseable value.
  - `"ticker_mismatch"` — the request specified a `ticker` filter and the news item had a `ticker` that did not match (case-sensitive string equality).
  - `"missing_ticker"` — the request specified a `ticker` filter and the news item had no `ticker` field (missing, `None`, or empty string).

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

#### Scenario: ticker is echoed when provided

- **GIVEN** `ticker="AAPL"` and any non-empty news list
- **WHEN** the Temporal Retriever runs
- **THEN** the response `ticker` is `"AAPL"`

#### Scenario: ticker defaults to None when absent

- **GIVEN** the request omits `ticker` (or passes `ticker=None`) and any non-empty news list
- **WHEN** the Temporal Retriever runs
- **THEN** the response `ticker` is `None`
- **AND** the ticker filter is skipped (every news item is passed to the time filter)

#### Scenario: ticker filter keeps only matching items

- **GIVEN** `ticker="AAPL"` and a news list with three items: one with `ticker="AAPL"`, one with `ticker="GOOGL"`, one with `ticker="AAPL"`
- **WHEN** the Temporal Retriever runs
- **THEN** the GOOGL item is excluded from `valid_news` and `invalid_future_news`
- **AND** a structured error object with `reason = "ticker_mismatch"` and `news_id` of the GOOGL item is appended to `errors`
- **AND** the two AAPL items are processed by the time filter normally

#### Scenario: ticker filter is case-sensitive

- **GIVEN** `ticker="AAPL"` and a news item with `ticker="aapl"`
- **WHEN** the Temporal Retriever runs
- **THEN** the item is NOT placed in `valid_news` or `invalid_future_news` based on ticker match
- **AND** a structured error object with `reason = "ticker_mismatch"` is appended to `errors`

#### Scenario: news item missing the ticker field is excluded when ticker filter is on

- **GIVEN** `ticker="AAPL"` and a news item with no `ticker` field
- **WHEN** the Temporal Retriever runs
- **THEN** the item is excluded from `valid_news` and `invalid_future_news`
- **AND** a structured error object with `reason = "missing_ticker"` is appended to `errors`

#### Scenario: ticker=None skips the ticker filter

- **GIVEN** `ticker=None` and a news list with mixed-ticker items (e.g. one `"AAPL"`, one `"GOOGL"`, one with no ticker)
- **WHEN** the Temporal Retriever runs
- **THEN** all three items are processed by the time filter (no ticker-based exclusion)
- **AND** no `errors` entries are produced for ticker reasons

#### Scenario: ticker="" (empty string) is treated the same as None

- **GIVEN** `ticker=""` and a news list with mixed-ticker items
- **WHEN** the Temporal Retriever runs
- **THEN** the ticker filter is skipped
- **AND** the response `ticker` is `""` (echoed as-is)

### Requirement: Datetime comparison rule

The Temporal Retriever SHALL normalize `forecast_time` and every `news_time` to UTC (Coordinated Universal Time) before comparison. Naive datetimes (no offset) are treated as UTC. A naive timestamp on one side and a timezone-aware timestamp on the other are made directly comparable by attaching the UTC offset to the naive side. Comparison then uses the rule `news_time <= forecast_time` for `valid_news` and `news_time > forecast_time` for `invalid_future_news`.

#### Scenario: Equal timestamps compare as valid

- **GIVEN** `forecast_time` `"2025-03-12 09:00"` and `news_time` `"2025-03-12 09:00"`
- **WHEN** the Temporal Retriever compares them
- **THEN** the comparison evaluates to `news_time <= forecast_time` (i.e. valid)

#### Scenario: Future timestamp compares as invalid

- **GIVEN** `forecast_time` `"2025-03-12 09:00"` and `news_time` `"2025-03-12 15:30"`
- **WHEN** the Temporal Retriever compares them
- **THEN** the comparison evaluates to `news_time > forecast_time` (i.e. invalid)

#### Scenario: Naive timestamp is interpreted as UTC

- **GIVEN** `forecast_time` `"2025-03-12 09:00"` (naive) and a news item with `news_time` `"2025-03-12 08:30+00:00"` (timezone-aware UTC)
- **WHEN** the Temporal Retriever runs
- **THEN** the news item appears in `valid_news` (naive `09:00` UTC is later than aware `08:30` UTC)

### Requirement: Edge cases are handled deterministically

The Temporal Retriever SHALL handle the following edge cases deterministically:

- `news_time` exactly equal to `forecast_time` → placed in `valid_news`.
- Empty news list → `valid_news` and `invalid_future_news` are empty; counts are `0`; `temporal_validity` is `0.0`; `errors` is empty; no exception is raised.
- All news valid → `invalid_future_news` is empty; `valid_count == total_count`; `temporal_validity == 1.0`.
- All news invalid (all future) → `valid_news` is empty; `invalid_future_count == total_count`; `temporal_validity == 0.0`.
- Mixed valid and future → both groups populated, counts correct.
- Missing or malformed `news_time` → the item is excluded from both `valid_news` and `invalid_future_news`; a structured error object is appended to `errors` with `reason = "missing_or_malformed_news_time"`; the request continues processing other items.
- Ticker filter specified and news item `ticker` does not match → the item is excluded from both `valid_news` and `invalid_future_news`; a structured error object is appended to `errors` with `reason = "ticker_mismatch"`; the request continues processing other items.
- Ticker filter specified and news item has no `ticker` field → the item is excluded from both `valid_news` and `invalid_future_news`; a structured error object is appended to `errors` with `reason = "missing_ticker"`; the request continues processing other items.
- Malformed `forecast_time` (missing, null, or not a parseable timestamp) → a `TemporalValidationError` is raised; no partial response is returned.
- Timezone-aware timestamps → compared correctly when offsets match; both are first normalized to UTC.
- Timezone-naive timestamps → interpreted as UTC (the project-local timezone).

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

#### Scenario: Malformed news_time populates the errors list

- **GIVEN** a news list with one item whose `news_time` is `null`, missing, or not a parseable timestamp string
- **WHEN** the Temporal Retriever runs
- **THEN** the item is excluded from both `valid_news` and `invalid_future_news`
- **AND** a structured error object is appended to `errors` with `reason = "missing_or_malformed_news_time"` and `raw_value` echoing the unparseable value
- **AND** processing of the remaining items continues

#### Scenario: Malformed forecast_time raises TemporalValidationError

- **GIVEN** `forecast_time` is missing, null, or not a parseable timestamp string
- **WHEN** the Temporal Retriever runs
- **THEN** a `TemporalValidationError` is raised
- **AND** no partial response is returned

### Requirement: Temporal leakage prevention is explicit

The Temporal Retriever SHALL guarantee that no news item with `news_time > forecast_time` can be returned inside `valid_news`. This guarantee is the core of temporal leakage prevention and SHALL be enforced by the implementation and verified by regression tests.

#### Scenario: Future news never leaks into valid_news (temporal leakage regression)

- **GIVEN** `forecast_time` `"2025-03-12 09:00"` and a news list with one item at `news_time` `"2025-03-12 15:30"` (6 hours in the future)
- **WHEN** the Temporal Retriever runs
- **THEN** the future item appears in `invalid_future_news`
- **AND** the future item is NOT present anywhere in `valid_news`
- **AND** no future item is silently dropped from the output (it MUST remain in `invalid_future_news` for traceability and dashboard warning)

#### Scenario: 1-second-in-the-future news is treated as invalid

- **GIVEN** `forecast_time` `"2025-03-12 09:00:00"` and a news item with `news_time` `"2025-03-12 09:00:01"`
- **WHEN** the Temporal Retriever runs
- **THEN** the news item appears in `invalid_future_news`
- **AND** the news item does NOT appear in `valid_news`

### Requirement: Traceability and observability

The Temporal Retriever SHALL preserve every input news item in the response — every item lands in exactly one of `valid_news`, `invalid_future_news`, or `errors`. The service SHALL NOT silently drop any item. Downstream consumers and the dashboard (a later change) SHALL be able to inspect `invalid_future_news` to surface warnings when future news was filtered out.

#### Scenario: Every input news item is preserved in the response

- **GIVEN** a news list with 5 items (any mix of past, equal, future, malformed, ticker-matched, or ticker-mismatched)
- **WHEN** the Temporal Retriever runs
- **THEN** the sum of `len(valid_news) + len(invalid_future_news) + len(errors)` equals `total_count`
- **AND** every input item is present in exactly one of those three collections

### Requirement: Determinism and simplicity

The Temporal Retriever SHALL be deterministic and idempotent: identical requests SHALL produce identical responses field-by-field (including counts, group membership, `temporal_validity`, and `errors`). The service SHALL NOT call any ML model, LLM, network endpoint, database, or external service. The implementation SHALL be readable by a student and SHALL fit in a single small Python module.

#### Scenario: Identical requests produce identical responses (idempotency)

- **GIVEN** the same request payload (`forecast_time`, `ticker`, `news`) is provided twice in succession
- **WHEN** the Temporal Retriever runs twice
- **THEN** both responses are equal field-by-field (including counts, group membership, `temporal_validity`, and `errors`)
