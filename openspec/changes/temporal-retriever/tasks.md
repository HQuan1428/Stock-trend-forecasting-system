# Tasks: Temporal Retriever

## 1. Data Models

- [ ] 1.1 Add a `NewsItem` dataclass (or `TypedDict`) in `src/retriever.py` with fields: `news_id: str`, `news_time: str`, `title: Optional[str]`, `text: str`, and pass-through support for arbitrary extra fields.
- [ ] 1.2 Add a `RetrievalResult` dataclass in `src/retriever.py` with fields: `ticker: Optional[str]`, `forecast_time: str`, `valid_news: List[Dict]`, `invalid_future_news: List[Dict]`, `valid_count: int`, `invalid_future_count: int`, `total_count: int`, `temporal_validity: float`, `errors: List[Dict]`.
- [ ] 1.3 Document in the module docstring that the project-local timezone is assumed for naive timestamps.

## 2. Datetime Parsing Helper

- [ ] 2.1 Implement `_parse_datetime(value: str) -> datetime` that accepts ISO 8601 strings (with `"T"` or `" "` separator) and rejects everything else with a `ValueError`.
- [ ] 2.2 Implement `_normalize_to_aware(dt: datetime, reference: Optional[datetime]) -> datetime` that attaches the reference's timezone (or the project-local timezone) to a naive datetime, and raises on mixed offsets that cannot be reconciled.
- [ ] 2.3 Add a helper `_compare(news_dt: datetime, forecast_dt: datetime) -> int` that returns `-1`, `0`, `+1` exactly like a normal datetime comparison; this centralizes the comparison rule for unit testing.

## 3. Core Filter Function

- [ ] 3.1 Implement `retrieve_valid_news(forecast_time: str, news: List[Dict], ticker: Optional[str] = None) -> RetrievalResult` in `src/retriever.py`.
- [ ] 3.2 Parse `forecast_time` once at the start; raise `TemporalValidationError` if it is missing or unparseable.
- [ ] 3.3 For each news item, parse `news_time`; on parse failure, append `{"news_id": ..., "reason": "missing_or_malformed_news_time", "raw_value": ...}` to `errors` and skip.
- [ ] 3.4 Compare each parsed `news_dt` against `forecast_dt` using the rule `news_dt <= forecast_dt` for `valid_news` and `news_dt > forecast_dt` for `invalid_future_news`. Preserve input order in both lists.
- [ ] 3.5 Compute `valid_count`, `invalid_future_count`, `total_count`, and `temporal_validity = valid_count / total_count if total_count > 0 else 0.0`.
- [ ] 3.6 Define and document a `TemporalValidationError` exception class for unrecoverable input problems (e.g. malformed `forecast_time`).

## 4. Output Preservation and Metadata

- [ ] 4.1 Ensure the retriever copies each news item into the output **without mutation** (no field stripping, no field renaming). Accept both `text` and `news_text` as the body field; normalize to `text` in the output if needed for downstream consistency, and document this in the module docstring.
- [ ] 4.2 Return a `RetrievalResult` instance that includes `ticker`, `forecast_time` (echoed), counts, `temporal_validity`, and `errors`.
- [ ] 4.3 Verify with a unit test that the sum `len(valid_news) + len(invalid_future_news) + len(errors) == total_count` for any input.

## 5. Unit Tests

- [ ] 5.1 Add `tests/test_temporal_retriever.py` with the following cases:
  - Past news is placed in `valid_news`.
  - News at exactly `forecast_time` is placed in `valid_news` (equal-timestamp boundary).
  - News 1 second in the future is placed in `invalid_future_news` (leakage boundary).
  - News 6 hours in the future is placed in `invalid_future_news` (named leakage regression).
  - Mixed list produces disjoint groups and correct counts.
  - All-valid list: `temporal_validity == 1.0`.
  - All-invalid list: `temporal_validity == 0.0`.
  - Empty list: `temporal_validity == 0.0`, counts are zero, no exception.
  - Malformed `news_time` populates `errors` and the item is not silently dropped.
  - Missing `forecast_time` raises `TemporalValidationError`.
  - Identical inputs produce identical outputs (determinism).
- [ ] 5.2 Add `tests/test_temporal_leakage.py` as a dedicated regression suite asserting that no future news ever appears in `valid_news`, using parameterised pytest cases over several forecast/ news combinations.
- [ ] 5.3 Run `pytest tests/ -v` and confirm all new tests pass.

## 6. Sample Dataset Extension

- [ ] 6.1 Extend `data/sample_dataset.csv` with at least one new row for each scenario: past, equal, and future. Keep the existing columns (`new_id, ticker, forecast_time, news_time, news_text, label`).
- [ ] 6.2 Add a brief comment in the dataset (or a sibling `data/README.md`) describing which rows are valid, equal, and future for demo purposes.

## 7. Documentation

- [ ] 7.1 Update `README.md` (or a new `docs/temporal_retriever.md`) with a short usage example:

  ```python
  from src.retriever import retrieve_valid_news

  result = retrieve_valid_news(
      forecast_time="2025-03-12 09:00",
      ticker="AAPL",
      news=[
          {"news_id": "n1", "news_time": "2025-03-11 08:00", "text": "Past headline"},
          {"news_id": "n2", "news_time": "2025-03-12 15:30", "text": "Future headline"},
      ],
  )
  assert result.valid_count == 1
  assert result.invalid_future_count == 1
  assert result.temporal_validity == 0.5
  ```
- [ ] 7.2 Note in the README that downstream modules must consume `valid_news` only and must never see `invalid_future_news`.

## 8. Validation

- [ ] 8.1 Run `pytest tests/ -v` and confirm a green run.
- [ ] 8.2 Run `openspec validate temporal-retriever --strict` (or the equivalent command for this repository) and resolve any reported issues.
- [ ] 8.3 Run `openspec status --change temporal-retriever` and confirm the change is ready to apply.

## 9. Cleanup

- [ ] 9.1 Confirm `src/__init__.py` re-exports `retrieve_valid_news` for ergonomic imports.
- [ ] 9.2 Confirm no future-dated news can leak by running the leakage regression test one final time.
