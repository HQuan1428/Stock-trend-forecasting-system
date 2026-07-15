# Credential-gated data sources (manual runbook)

`ChuDe1.md` §7.1 lists several real-data sources for the C1 bonus. Two are
already wired into `scripts/fetch_real_data.py` and need no account: **Yahoo
Finance** and **Stooq** for prices, **FNSPID** (Hugging Face) for news. This
folder covers the remaining sources named in `ChuDe1.md` that need an
account/API key only you can create, so these scripts are written and ready
but **not executed** by this project. Nothing here is imported by
`scripts/fetch_real_data.py`, `src/pipeline.py`, or any test.

No paid tier is used or required by any script below.

## Nasdaq Data Link (`fetch_nasdaq_data_link.py`)

- **Sign up (free)**: https://data.nasdaq.com/sign-up
- **Env var**: `NASDAQ_DATA_LINK_API_KEY`
- **Honest caveat**: the free "WIKI Prices" end-of-day equity dataset was
  **retired in April 2018**. Most equity price datasets on the platform
  today require a paid subscription. This script can fetch any dataset
  code your account has access to (e.g. free macro datasets like
  `FRED/GDP`), but it does **not** reproduce the AAPL/GOOGL/AMZN/MSFT
  price coverage `scripts/fetch_real_data.py` already gets for free from
  Yahoo Finance/Stooq. Treat this source as optional/exploratory, not a
  drop-in replacement.
- **Run**:
  ```bash
  export NASDAQ_DATA_LINK_API_KEY=your_key_here
  python3 -m scripts.data_sources.fetch_nasdaq_data_link FRED/GDP
  ```
- **Output**: `data/raw_cache/nasdaq_data_link/<dataset>.json` (gitignored).

## Kaggle (`fetch_kaggle_news.py`)

- **Sign up (free)**: https://www.kaggle.com/settings → Account → "Create
  New API Token" → downloads `kaggle.json`.
- **Credentials**: place the file at `~/.kaggle/kaggle.json` (`chmod 600`),
  or set `KAGGLE_USERNAME` + `KAGGLE_KEY` environment variables.
- **Also required**: `pip install kaggle`, and — Kaggle-specific — open
  the target dataset's page on kaggle.com **at least once** and accept its
  terms; the API refuses some downloads otherwise even with a valid token.
- **Run**:
  ```bash
  python3 -m scripts.data_sources.fetch_kaggle_news
  # or a different dataset you've accepted the terms of:
  python3 -m scripts.data_sources.fetch_kaggle_news some-other/dataset-slug
  ```
- **Output**: unzipped into `data/raw_cache/kaggle/` (gitignored).

## Reuters — explicitly out of scope

Real Reuters financial-news archives (as opposed to the public FNSPID
Nasdaq-100 subset already used) are typically Refinitiv-licensed and not
available for free. No fetcher is provided for Reuters, and none is
planned — pursuing it would mean either a paid license or scope outside
what this academic prototype needs. See `data/README.md` for the news
source that *is* used (FNSPID, CC BY-NC-4.0).
