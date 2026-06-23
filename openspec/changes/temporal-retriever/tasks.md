# Tasks: Temporal Retriever

## 1. Data Models

- [x] 1.1 Add a `NewsItem` dataclass (or `TypedDict`) in `src/retriever.py` with fields: `news_id: str`, `news_time: str`, `title: Optional[str]`, `text: str`, and pass-through support for arbitrary extra fields.
- [x] 1.2 Add a `RetrievalResult` dataclass in `src/retriever.py` with fields: `ticker: Optional[str]`, `forecast_time: str`, `valid_news: List[Dict]`, `invalid_future_news: List[Dict]`, `valid_count: int`, `invalid_future_count: int`, `total_count: int`, `temporal_validity: float`, `errors: List[Dict]`.
- [x] 1.3 Document in the module docstring that the **project-local timezone is UTC** and that naive timestamps are interpreted as UTC.

## 2. Datetime Parsing Helper

- [x] 2.1 Implement `_parse_datetime(value: str) -> datetime` that accepts ISO 8601 strings (with `"T"` or `" "` separator) and rejects everything else with a `ValueError`.
- [x] 2.2 Implement `_normalize_to_utc(dt: datetime) -> datetime` that converts any timezone-aware datetime to UTC and attaches the UTC offset to any naive datetime (per Decision 5: project-local timezone is UTC).
- [x] 2.3 Skip a separate `_compare` helper — use Python's native `<=` / `>` directly inside `retrieve_valid_news`. The helper would be a thin wrapper that adds a layer without adding behavior.

## 3. Core Filter Function

- [x] 3.1 Implement `retrieve_valid_news(forecast_time: str, news: List[Dict], ticker: Optional[str] = None) -> RetrievalResult` in `src/retriever.py`.
- [x] 3.2 Parse `forecast_time` once at the start; raise `TemporalValidationError` if it is missing or unparseable.
- [x] 3.3 For each news item, parse `news_time`; on parse failure, append `{"news_id": ..., "reason": "missing_or_malformed_news_time", "raw_value": ...}` to `errors` and skip.
- [x] 3.4 Compare each parsed `news_dt` against `forecast_dt` using the rule `news_dt <= forecast_dt` for `valid_news` and `news_dt > forecast_dt` for `invalid_future_news`. Preserve input order in both lists.
- [x] 3.5 Compute `valid_count`, `invalid_future_count`, `total_count`, and `temporal_validity = valid_count / total_count if total_count > 0 else 0.0`.
- [x] 3.6 Define and document a `TemporalValidationError` exception class for unrecoverable input problems (e.g. malformed `forecast_time`).

## 4. Output Preservation, Metadata, and Invariants

- [x] 4.1 Output preserves every field of every news item **including the field name** (true preserve). The implementation copies each input dict into the response without mutation, without renaming `text` ↔ `news_text`, and without dropping any key. Both `text` and `news_text` are accepted as the body field; whichever the input uses is preserved verbatim in the response. Downstream consumers can read either via `item.get("text") or item.get("news_text")`. Document this in the module docstring.
- [x] 4.2 Return a `RetrievalResult` instance that includes `ticker` (echoed as-is or `None`), `forecast_time` (echoed as-is), counts, `temporal_validity`, and `errors` (always present, possibly empty).
- [x] 4.3 Verify with a unit test that the invariant `len(valid_news) + len(invalid_future_news) + len(errors) == total_count` holds for any input, including inputs with malformed items.

## 5. Unit Tests

- [x] 5.1 Add `tests/test_temporal_retriever.py` with the following cases:
  - Past news is placed in `valid_news`.
  - News at exactly `forecast_time` is placed in `valid_news` (equal-timestamp boundary).
  - News 1 second in the future is placed in `invalid_future_news` (leakage boundary).
  - News 6 hours in the future is placed in `invalid_future_news` (named leakage regression).
  - Mixed list produces non-overlapping groups and correct counts.
  - All-valid list: `temporal_validity == 1.0`.
  - All-invalid list: `temporal_validity == 0.0`.
  - Empty list: `temporal_validity == 0.0`, counts are zero, no exception.
  - Malformed `news_time` populates `errors` with the documented shape (`news_id`, `reason`, `raw_value`) and the item is excluded from both groups; processing continues for the remaining items.
  - Missing or malformed `forecast_time` raises `TemporalValidationError` (no partial response).
  - Identical requests produce identical responses (idempotency).
  - `ticker` provided on the request is echoed as-is in the response.
  - `ticker` absent from the request yields `ticker is None` in the response.
  - A news item using `news_text` (instead of `text`) is preserved verbatim — no synthetic `text` field is created.
  - A naive `news_time` (`"2025-03-12 08:30+00:00"` vs naive `"2025-03-12 09:00"`) is interpreted as UTC and compared correctly.
- [x] 5.2 Add `tests/test_temporal_leakage.py` as a dedicated regression suite asserting that no future news ever appears in `valid_news`, using parametrized pytest cases over several forecast/news combinations (covering 1-second, 1-minute, 6-hour, 1-day, and 1-week offsets).
- [x] 5.3 Run `pytest tests/ -v` and confirm all new tests pass.

## 6. Sample Dataset Reference

- [x] 6.1 Verify that `data/sample_dataset.csv` already contains rows covering the three temporal scenarios relative to each row's `forecast_time`. The existing rows `news_id=1` (past), `news_id=2` (future), and `news_id=3` (equal) are sufficient for demo and regression use. No CSV extension is needed; do not modify the dataset.
- [x] 6.2 Add `data/README.md` describing the dataset, listing the column schema (`news_id, ticker, forecast_time, news_time, news_text, label`), and mapping `news_id` values to their temporal scenario (`1=valid, 2=invalid_future, 3=equal`) for downstream and human reference.

## 7. Documentation

- [x] 7.1 Update `README.md` (or a new `docs/temporal_retriever.md`) with a short usage example:

  ```python
  from src.retriever import retrieve_valid_news

  result = retrieve_valid_news(
      forecast_time="2025-03-12 09:00",  # naive → interpreted as UTC
      ticker="AAPL",
      news=[
          {"news_id": "n1", "news_time": "2025-03-11 08:00", "text": "Past headline"},
          {"news_id": "n2", "news_time": "2025-03-12 15:30", "text": "Future headline"},
      ],
  )
  assert result.valid_count == 1
  assert result.invalid_future_count == 1
  assert result.temporal_validity == 0.5
  assert result.ticker == "AAPL"
  ```
- [x] 7.2 Note in the README that downstream consumers must consume `valid_news` only and must never see `invalid_future_news`.

## 8. Validation

- [x] 8.1 Run `pytest tests/ -v` and confirm a green run.
- [x] 8.2 Run `openspec validate temporal-retriever` and resolve any reported issues. (If the local `openspec` CLI supports a `--strict` flag, prefer that; otherwise the plain command is acceptable.)
- [x] 8.3 Run `openspec status --change temporal-retriever` and confirm the change is ready to apply.

## 9. Cleanup

- [x] 9.1 Confirm `src/__init__.py` re-exports `retrieve_valid_news` and `RetrievalResult` for ergonomic imports.
- [x] 9.2 Confirm no future-dated news can leak by running the leakage regression test one final time.
