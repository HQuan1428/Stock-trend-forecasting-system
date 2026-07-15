"""One-time data-prep script: builds ``data/real_dataset.csv`` from real data.

This is the ONLY file in the repository that performs network I/O. It is not
imported by ``src/pipeline.py`` or any module under ``src/`` — the pipeline
stays fully offline and deterministic. Run this script once (or whenever you
want to refresh the sample), then point the pipeline at its output:

    python3 scripts/fetch_real_data.py
    python -m src.runner --input data/real_dataset.csv --output-dir outputs_real

Data sources (both public, no API key required):

* Prices — Yahoo Finance's public chart API
  (``query1.finance.yahoo.com/v8/finance/chart``). Requires a browser-like
  ``User-Agent`` header; returns real daily OHLCV.
* News — a Nasdaq-100 subset of FNSPID (Zihan Dong et al., "FNSPID: A
  Comprehensive Financial News Dataset in Time Series", KDD 2024,
  arXiv:2402.06698), hosted on Hugging Face at
  ``benstaf/FNSPID-nasdaq-100-1news-per-row-random``. Real article titles
  with real publish timestamps. License: CC BY-NC-4.0 (non-commercial),
  which fits this academic prototype's scope — see ``data/README.md``.

See ``openspec/changes/real-market-data/design.md`` for the full
rationale behind every constant and decision below (ticker substitution,
date window, forecast_time convention, sampling strategy).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "data" / "raw_cache"
OUTPUT_PATH = REPO_ROOT / "data" / "real_dataset.csv"

# D1/D2 (design.md): META has 0 rows in the chosen news mirror, so it is
# replaced with MSFT. GOOG and GOOGL are folded into a single "GOOGL".
TICKERS: Tuple[str, ...] = ("AAPL", "GOOGL", "AMZN", "MSFT")
GOOGLE_ALIASES = {"GOOG", "GOOGL"}

# D3: news window with solid coverage for all 4 tickers; price window padded
# so every news row has >=5 trading days of history and >=1 trading day after.
NEWS_START = "2022-01-01"
NEWS_END = "2023-12-31"
PRICE_START = "2021-12-01"
PRICE_END = "2024-01-15"

MAX_ARTICLES_PER_TICKER = 100
UP_DOWN_THRESHOLD = 0.005  # ChuDe1.md Sec 7.2

FNSPID_PARQUET_URLS = (
    "https://huggingface.co/datasets/benstaf/FNSPID-nasdaq-100-1news-per-row-random/"
    "resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet",
    "https://huggingface.co/datasets/benstaf/FNSPID-nasdaq-100-1news-per-row-random/"
    "resolve/refs%2Fconvert%2Fparquet/default/train/0001.parquet",
)

REAL_DATASET_COLUMNS = (
    "news_id",
    "ticker",
    "forecast_time",
    "news_time",
    "news_text",
    "label",
    "next_day_return",
    "price_5d_return",
    "volume_change",
)

_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"


# ---------------------------------------------------------------------------
# 1. Price data (Yahoo Finance chart API)
# ---------------------------------------------------------------------------


class PriceSeries:
    """Real daily close/volume for one ticker, indexed by trading date."""

    def __init__(self, dates: List[str], closes: List[float], volumes: List[float]):
        self.dates = dates  # sorted ascending, e.g. "2023-01-03"
        self._close_by_date: Dict[str, float] = dict(zip(dates, closes))
        self._volume_by_date: Dict[str, float] = dict(zip(dates, volumes))

    def index_of(self, date_str: str) -> Optional[int]:
        # first trading date >= date_str (binary search would be nicer; N is small)
        for i, d in enumerate(self.dates):
            if d >= date_str:
                return i
        return None

    def close_at(self, idx: int) -> float:
        return self._close_by_date[self.dates[idx]]

    def volume_at(self, idx: int) -> float:
        return self._volume_by_date[self.dates[idx]]

    def __len__(self) -> int:
        return len(self.dates)


def fetch_price_series(ticker: str, start: str, end: str) -> PriceSeries:
    """Fetch real daily OHLCV for ``ticker`` from Yahoo Finance's chart API.

    No API key needed; a browser User-Agent header is required (the bare
    endpoint returns HTTP 429 without one).
    """
    p1 = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    p2 = int(datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?period1={p1}&period2={p2}&interval=1d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)

    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    closes = quote["close"]
    volumes = quote["volume"]

    dates: List[str] = []
    clean_closes: List[float] = []
    clean_volumes: List[float] = []
    for ts, close, vol in zip(timestamps, closes, volumes):
        if close is None or vol is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        dates.append(d)
        clean_closes.append(float(close))
        clean_volumes.append(float(vol))

    return PriceSeries(dates, clean_closes, clean_volumes)


def fetch_all_price_series(cache_dir: Path) -> Dict[str, PriceSeries]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    result: Dict[str, PriceSeries] = {}
    for ticker in TICKERS:
        cache_file = cache_dir / f"price_{ticker}.json"
        if cache_file.exists():
            raw = json.loads(cache_file.read_text())
            result[ticker] = PriceSeries(raw["dates"], raw["closes"], raw["volumes"])
            continue
        series = fetch_price_series(ticker, PRICE_START, PRICE_END)
        cache_file.write_text(
            json.dumps(
                {
                    "dates": series.dates,
                    "closes": [series.close_at(i) for i in range(len(series))],
                    "volumes": [series.volume_at(i) for i in range(len(series))],
                }
            )
        )
        result[ticker] = series
    return result


# ---------------------------------------------------------------------------
# 2. News data (FNSPID Nasdaq-100 subset, Hugging Face)
# ---------------------------------------------------------------------------


def download_fnspid_parquet(cache_dir: Path) -> List[Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, url in enumerate(FNSPID_PARQUET_URLS):
        dest = cache_dir / f"fnspid_part{i}.parquet"
        if not dest.exists():
            req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(req, timeout=300) as resp, open(dest, "wb") as f:
                f.write(resp.read())
        paths.append(dest)
    return paths


def normalize_ticker(symbol: str) -> str:
    """Fold every Google share-class symbol into a single ``GOOGL`` (D2)."""
    return "GOOGL" if symbol in GOOGLE_ALIASES else symbol


def load_news(cache_dir: Path) -> pd.DataFrame:
    """Load, normalize, and window-filter real news headlines.

    Applies D2 (GOOG/GOOGL -> GOOGL) and D3 (date window) from design.md.
    Does NOT filter or rank by keyword content (D5) — sampling is neutral.
    """
    paths = download_fnspid_parquet(cache_dir)
    frames = [pd.read_parquet(p, columns=["Date", "Article_title", "Stock_symbol"]) for p in paths]
    df = pd.concat(frames, ignore_index=True)

    df["ticker"] = df["Stock_symbol"].map(normalize_ticker)
    df = df[df["ticker"].isin(TICKERS)].copy()

    df["news_time_parsed"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
    df = df.dropna(subset=["news_time_parsed"])
    df = df[(df["news_time_parsed"] >= NEWS_START) & (df["news_time_parsed"] <= NEWS_END + " 23:59:59")]

    df["Article_title"] = df["Article_title"].astype(str).str.strip()
    df = df[df["Article_title"].str.len() > 0]
    df = df.drop_duplicates(subset=["ticker", "Article_title"])

    return df.sort_values(["ticker", "news_time_parsed"]).reset_index(drop=True)


def sample_evenly(df: pd.DataFrame, n_per_ticker: int = MAX_ARTICLES_PER_TICKER) -> pd.DataFrame:
    """Deterministically pick up to ``n_per_ticker`` rows per ticker, spread
    across the date window (D5) — no randomness, no keyword-based filtering.
    """
    parts = []
    for ticker, group in df.groupby("ticker"):
        group = group.reset_index(drop=True)
        if len(group) <= n_per_ticker:
            parts.append(group)
            continue
        idx = np.linspace(0, len(group) - 1, n_per_ticker).round().astype(int)
        idx = sorted(set(idx.tolist()))
        parts.append(group.iloc[idx])
    return pd.concat(parts, ignore_index=True).sort_values(["ticker", "news_time_parsed"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 3. Join: news + price -> real_dataset.csv rows (D4)
# ---------------------------------------------------------------------------


def build_dataset(news_df: pd.DataFrame, price_by_ticker: Dict[str, PriceSeries]) -> pd.DataFrame:
    rows = []
    dropped_edge = 0
    for i, row in news_df.iterrows():
        ticker = row["ticker"]
        series = price_by_ticker[ticker]
        news_date = row["news_time_parsed"].strftime("%Y-%m-%d")

        forecast_idx = series.index_of(news_date)
        # advance to the first trading day strictly AFTER the news calendar date
        while forecast_idx is not None and series.dates[forecast_idx] <= news_date:
            forecast_idx += 1
            if forecast_idx >= len(series):
                forecast_idx = None
                break

        if forecast_idx is None or forecast_idx - 5 < 0 or forecast_idx + 1 >= len(series):
            dropped_edge += 1
            continue

        close_t = series.close_at(forecast_idx)
        close_t1 = series.close_at(forecast_idx + 1)
        close_t_minus_5 = series.close_at(forecast_idx - 5)
        vol_t = series.volume_at(forecast_idx)
        vol_t_minus_1 = series.volume_at(forecast_idx - 1)

        next_day_return = (close_t1 - close_t) / close_t
        price_5d_return = (close_t - close_t_minus_5) / close_t_minus_5
        volume_change = (vol_t - vol_t_minus_1) / vol_t_minus_1 if vol_t_minus_1 else 0.0

        if next_day_return > UP_DOWN_THRESHOLD:
            label = "UP"
        elif next_day_return < -UP_DOWN_THRESHOLD:
            label = "DOWN"
        else:
            label = "HOLD"

        rows.append(
            {
                "news_id": f"R{i:04d}",
                "ticker": ticker,
                "forecast_time": f"{series.dates[forecast_idx]} 09:00",
                "news_time": row["news_time_parsed"].strftime("%Y-%m-%d %H:%M"),
                "news_text": row["Article_title"],
                "label": label,
                "next_day_return": round(next_day_return, 4),
                "price_5d_return": round(price_5d_return, 4),
                "volume_change": round(volume_change, 4),
            }
        )

    print(f"  dropped (insufficient price history/future at window edge): {dropped_edge}")
    out = pd.DataFrame(rows, columns=list(REAL_DATASET_COLUMNS))
    out["news_id"] = [f"R{i:04d}" for i in range(len(out))]  # re-number sequentially post-drop
    return out


# ---------------------------------------------------------------------------
# 4. Orchestration
# ---------------------------------------------------------------------------


def main() -> None:
    print(f"[1/4] Fetching real prices for {TICKERS} from Yahoo Finance...")
    price_by_ticker = fetch_all_price_series(CACHE_DIR)
    for ticker, series in price_by_ticker.items():
        print(f"  {ticker}: {len(series)} trading days")

    print("[2/4] Downloading + loading FNSPID Nasdaq-100 news subset (Hugging Face)...")
    news_df = load_news(CACHE_DIR)
    print(f"  candidate rows in window {NEWS_START}..{NEWS_END}: {len(news_df)}")
    for ticker in TICKERS:
        print(f"    {ticker}: {(news_df['ticker'] == ticker).sum()}")

    print(f"[3/4] Sampling up to {MAX_ARTICLES_PER_TICKER} articles/ticker (evenly spaced, no keyword filtering)...")
    sampled = sample_evenly(news_df)
    print(f"  sampled rows: {len(sampled)}")

    print("[4/4] Joining news with real returns and writing data/real_dataset.csv...")
    dataset = build_dataset(sampled, price_by_ticker)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(OUTPUT_PATH, index=False)

    print(f"\nWrote {len(dataset)} rows to {OUTPUT_PATH}")
    print(f"  tickers: {sorted(dataset['ticker'].unique().tolist())}")
    print(f"  label distribution: {dataset['label'].value_counts().to_dict()}")
    print(f"  date range (news_time): {dataset['news_time'].min()} .. {dataset['news_time'].max()}")


if __name__ == "__main__":
    main()
