## ADDED Requirements

### Requirement: `fetch_real_data.py` builds a schema-compatible real dataset

`scripts/fetch_real_data.py` SHALL build `data/real_dataset.csv` with exactly these 9 columns, in order: `news_id, ticker, forecast_time, news_time, news_text, label, next_day_return, price_5d_return, volume_change`. This SHALL be the only file in the repository that performs network I/O; no module under `src/` SHALL import it or be changed by this capability.

#### Scenario: Output schema matches the pipeline's ingest contract
- **WHEN** `scripts/fetch_real_data.py` runs to completion
- **THEN** `data/real_dataset.csv` has exactly the 9 columns above
- **AND** every row's `ticker`, `forecast_time`, `news_time`, `news_text`, `news_id` are non-empty strings

#### Scenario: Real dataset is a drop-in input for the existing stage chain
- **WHEN** `python -m src.runner --input data/real_dataset.csv --output-dir outputs_real` runs
- **THEN** it completes with exit code `0` and writes all 8 envelope files and 6 result CSVs, with zero changes required in `src/stages/ingest.py` or any other stage module

### Requirement: Label and returns are computed from real close prices only

`next_day_return`, `price_5d_return`, and `label` SHALL be computed strictly from real historical close/volume data fetched for each ticker — never simulated or hashed.

```
next_day_return = (close[forecast_day + 1 session] − close[forecast_day]) / close[forecast_day]
price_5d_return = (close[forecast_day] − close[forecast_day − 5 sessions]) / close[forecast_day − 5 sessions]
label = "UP" if next_day_return > 0.005; "DOWN" if next_day_return < -0.005; else "HOLD"
```

#### Scenario: UP label when return exceeds threshold
- **WHEN** `next_day_return = 0.071` for a row
- **THEN** `label` is `"UP"`

#### Scenario: HOLD label within the neutral band
- **WHEN** `next_day_return = 0.002` for a row
- **THEN** `label` is `"HOLD"`

#### Scenario: DOWN label when return is below negative threshold
- **WHEN** `next_day_return = -0.012` for a row
- **THEN** `label` is `"DOWN"`

### Requirement: No lookahead bias in the news-to-forecast join

`forecast_time` for a news row SHALL always be the next real trading session strictly after that news item's publish date. Rows without at least 5 trading sessions of price history before `forecast_day`, or without a following trading session, SHALL be dropped (logged, not raised).

#### Scenario: forecast_time is strictly after the news publish date
- **WHEN** a news row is published on `2023-01-10`
- **THEN** its `forecast_time` date is the next real trading session after `2023-01-10` (e.g. `2023-01-12` if `2023-01-11` is not a trading day)

#### Scenario: Row dropped when insufficient price history before forecast_day
- **WHEN** a news row's `forecast_day` has fewer than 5 trading sessions of price history preceding it
- **THEN** the row is dropped from `data/real_dataset.csv`, not raised as an error

#### Scenario: Row dropped when no trading session follows forecast_day
- **WHEN** a news row's `forecast_day` is the last available trading session in the fetched price window
- **THEN** the row is dropped from `data/real_dataset.csv`, not raised as an error

### Requirement: Ticker set and normalization

The dataset SHALL cover tickers `AAPL, GOOGL, AMZN, MSFT`. Any news row tagged `GOOG` SHALL be folded into `GOOGL` in the output. `META` SHALL NOT appear (zero rows in the chosen news source; documented substitution with `MSFT` in `data/README.md`).

#### Scenario: GOOG rows are normalized to GOOGL
- **WHEN** a raw news row has `Stock_symbol = "GOOG"`
- **THEN** the corresponding output row has `ticker = "GOOGL"`

#### Scenario: Only the 4 approved tickers appear in the output
- **WHEN** `data/real_dataset.csv` is fully built
- **THEN** `set(df["ticker"])` is a subset of `{"AAPL", "GOOGL", "AMZN", "MSFT"}`

### Requirement: Sampling is content-neutral

Article sampling per ticker (up to 100 rows) SHALL be based only on even date-spacing across the time window, never on whether `news_text` matches the keyword dictionary used by `src/stages/evidence_extractor.py`.

#### Scenario: Sampling does not filter on headline content
- **WHEN** all candidate headlines for a ticker contain no keyword-dictionary matches
- **THEN** `sample_evenly` still returns up to the requested count of rows, unfiltered by content

### Requirement: Meets the C1 rubric volume threshold

The final `data/real_dataset.csv` SHALL contain at least 300 rows across at least 3 distinct tickers.

#### Scenario: Dataset size satisfies the rubric
- **WHEN** `data/real_dataset.csv` is generated with the default date window and ticker set
- **THEN** it has at least 300 rows
- **AND** at least 3 distinct values in the `ticker` column

### Requirement: Credential-gated sources are optional and inert by default

`scripts/data_sources/fetch_alpha_vantage.py` and `scripts/data_sources/fetch_kaggle_news.py` SHALL NOT be imported by `scripts/fetch_real_data.py`, any module under `src/`, or any test collected by the default `pytest` run. They SHALL only execute when invoked directly by a user who has supplied their own credentials via `.env` or environment variables.

#### Scenario: Default pipeline run never touches credential-gated scripts
- **WHEN** `scripts/fetch_real_data.py` runs with no environment variables set
- **THEN** it completes successfully without importing `scripts/data_sources/fetch_alpha_vantage.py` or `scripts/data_sources/fetch_kaggle_news.py`

### Requirement: Raw downloads are cached but never committed

Intermediate downloads (FNSPID Parquet, Yahoo/Stooq JSON) SHALL be written under `data/raw_cache/`, which SHALL be excluded from version control. Only the final `data/real_dataset.csv` SHALL be committed.

#### Scenario: raw_cache is gitignored
- **WHEN** `scripts/fetch_real_data.py` writes cache files under `data/raw_cache/`
- **THEN** `git status` does not list them as untracked (covered by `.gitignore`)

#### Scenario: Re-running the script reuses the cache
- **WHEN** `scripts/fetch_real_data.py` runs a second time with `data/raw_cache/` already populated
- **THEN** it does not re-fetch previously cached price series or FNSPID Parquet files over the network
