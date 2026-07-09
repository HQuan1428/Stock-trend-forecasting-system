## Why

Financial forecasting models that consume news data are vulnerable to **temporal leakage**: if the system uses an article published *after* the forecast cutoff to predict the market at that cutoff, the resulting accuracy and explainability metrics are misleading and invalid. For an evidence-centric prototype that promotes faithfulness, the first module in the pipeline must guarantee that no future news can reach the Evidence Extractor or Forecast Model. This change introduces the Temporal Retriever as that guarantee.

## What Changes

- Add a new module `src/retriever.py` exposing `TemporalRetriever.retrieve(forecast_time, news, ticker=None)` (or an equivalent pure function with the same contract).
- Define a deterministic, rule-based temporal filter that splits the input `news` list into `valid_news` and `invalid_future_news` based on `news_time <= forecast_time`.
- Return a structured result object containing both groups plus counts (`valid_count`, `invalid_future_count`, `total_count`) and a derived `temporal_validity` ratio.
- Preserve every input news item — including future news — in the output for auditability and dashboard warning; never silently drop items.
- Define an explicit behavior for malformed or missing `news_time` (validation error vs. error list) and document it in `design.md`.
- Add unit tests covering past, equal, future, mixed, empty, and malformed timestamp cases.
- Add a small sample dataset that includes rows with valid, equal, and future timestamps to make leakage scenarios reproducible.

## Capabilities

### New Capabilities

- `temporal-retriever`: Rule-based filtering of financial news by publication time. Splits input news into `valid_news` (news published at or before `forecast_time`) and `invalid_future_news` (news published strictly after `forecast_time`), reports counts, and preserves all input fields so downstream modules never see future news.

### Modified Capabilities

_None._ This change introduces a new capability and does not modify the requirements of existing specs.

## Impact

- New code: `src/retriever.py`, plus helpers for datetime parsing and dataclasses for input/output.
- New tests: `tests/test_temporal_retriever.py` (unit tests), `tests/test_temporal_leakage.py` (regression tests for leakage scenarios).
- New sample data: extend `data/sample_dataset.csv` with rows that include valid, equal, and future timestamps.
- Downstream consumers (`evidence_extractor.py`, `forecast_model.py`, `pipeline.py`, `dashboard.py` in later changes) will read from `valid_news` only; the current change does **not** implement those modules.
- Public API: a single Python function is added to `src.retriever`. No external service, network, or model dependency is introduced.
