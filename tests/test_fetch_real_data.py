"""Unit tests for scripts/fetch_real_data.py.

These tests exercise only the pure join/label/sampling logic with small
in-memory fixtures. No network access happens in this test file — the
network-touching functions (fetch_price_series, download_fnspid_parquet)
are exercised manually via `python3 scripts/fetch_real_data.py`, not here.
"""

import pandas as pd
import pytest

from scripts.fetch_real_data import (
    REAL_DATASET_COLUMNS,
    PriceSeries,
    build_dataset,
    normalize_ticker,
    sample_evenly,
)


def _make_series(dates, closes, volumes):
    return PriceSeries(dates, closes, volumes)


def _make_news_row(ticker, news_time):
    return {
        "ticker": ticker,
        "news_time_parsed": pd.Timestamp(news_time, tz="UTC"),
        "Article_title": f"{ticker} headline at {news_time}",
    }


class TestNormalizeTicker:
    def test_goog_and_googl_fold_to_googl(self):
        assert normalize_ticker("GOOG") == "GOOGL"
        assert normalize_ticker("GOOGL") == "GOOGL"

    def test_other_tickers_pass_through(self):
        assert normalize_ticker("AAPL") == "AAPL"
        assert normalize_ticker("MSFT") == "MSFT"


class TestBuildDataset:
    # 7 trading days, indices 0..6. A news article published ON a trading
    # date d[k] resolves to forecast_idx = k+1 (see build_dataset: it always
    # advances past the news's own calendar date). Using k=4 (d[4]) gives
    # forecast_idx=5, which satisfies both edge constraints for a 7-day
    # series (5-5=0 >= 0, and 5+1=6 <= len-1=6).
    _DATES7 = ["2023-01-02", "2023-01-04", "2023-01-06", "2023-01-08", "2023-01-10",
               "2023-01-12", "2023-01-14"]

    def _series_10_days(self):
        # 10 consecutive trading days, used only for the two drop scenarios
        # below (they don't depend on the exact close values).
        dates = [f"2023-01-{d:02d}" for d in range(2, 21, 2)]  # 02,04,...,20 (10 days)
        closes = [100.0, 101.0, 102.0, 100.0, 99.0, 98.0, 105.0, 106.0, 90.0, 91.0]
        volumes = [1000.0] * 10
        return _make_series(dates, closes, volumes)

    def _series_up(self):
        # forecast_idx=5 close=98.0 -> next idx=6 close=105.0 => +7.1% (UP)
        closes = [100.0, 100.0, 100.0, 100.0, 100.0, 98.0, 105.0]
        return _make_series(self._DATES7, closes, [1000.0] * 7)

    def _series_hold(self):
        # forecast_idx=5 close=100.0 -> next idx=6 close=100.2 => +0.2% (HOLD)
        closes = [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.2]
        return _make_series(self._DATES7, closes, [1000.0] * 7)

    def test_schema_matches_pipeline_contract(self):
        series = self._series_up()
        news_df = pd.DataFrame([_make_news_row("AAPL", "2023-01-10")])
        out = build_dataset(news_df, {"AAPL": series})
        assert list(out.columns) == list(REAL_DATASET_COLUMNS)
        assert len(out) == 1

    def test_forecast_time_is_strictly_after_news_date(self):
        series = self._series_up()
        news_df = pd.DataFrame([_make_news_row("AAPL", "2023-01-10")])
        out = build_dataset(news_df, {"AAPL": series})
        forecast_date = out.iloc[0]["forecast_time"].split(" ")[0]
        assert forecast_date > "2023-01-10"
        assert forecast_date == "2023-01-12"

    def test_label_up_when_return_above_threshold(self):
        series = self._series_up()
        news_df = pd.DataFrame([_make_news_row("AAPL", "2023-01-10")])
        out = build_dataset(news_df, {"AAPL": series})
        row = out.iloc[0]
        expected_return = (105.0 - 98.0) / 98.0
        assert row["next_day_return"] == pytest.approx(expected_return, abs=1e-4)
        assert row["label"] == "UP"

    def test_label_hold_within_threshold_band(self):
        series = self._series_hold()
        news_df = pd.DataFrame([_make_news_row("AAPL", "2023-01-10")])
        out = build_dataset(news_df, {"AAPL": series})
        row = out.iloc[0]
        assert row["next_day_return"] == pytest.approx(0.002, abs=1e-4)
        assert row["label"] == "HOLD"

    def test_drops_row_with_insufficient_history_before(self):
        series = self._series_10_days()
        # news on the very first trading day: forecast_idx would be 1,
        # which needs 5 days of history before it (1 - 5 < 0) -> dropped.
        news_df = pd.DataFrame([_make_news_row("AAPL", "2023-01-02")])
        out = build_dataset(news_df, {"AAPL": series})
        assert len(out) == 0

    def test_drops_row_with_no_future_trading_day(self):
        series = self._series_10_days()
        # news on the last trading day: no trading day exists after it.
        news_df = pd.DataFrame([_make_news_row("AAPL", "2023-01-20")])
        out = build_dataset(news_df, {"AAPL": series})
        assert len(out) == 0

    def test_news_id_prefix_and_uniqueness(self):
        series = self._series_10_days()
        news_df = pd.DataFrame(
            [_make_news_row("AAPL", "2023-01-06"), _make_news_row("AAPL", "2023-01-08")]
        )
        out = build_dataset(news_df, {"AAPL": series})
        assert all(nid.startswith("R") for nid in out["news_id"])
        assert out["news_id"].nunique() == len(out)


class TestSampleEvenly:
    def test_caps_rows_per_ticker(self):
        rows = []
        for i in range(50):
            rows.append(_make_news_row("AAPL", f"2023-01-{(i % 27) + 1:02d}"))
        df = pd.DataFrame(rows)
        out = sample_evenly(df, n_per_ticker=10)
        assert len(out) == 10

    def test_keeps_all_rows_when_under_cap(self):
        rows = [_make_news_row("AAPL", "2023-01-01"), _make_news_row("AAPL", "2023-01-02")]
        df = pd.DataFrame(rows)
        out = sample_evenly(df, n_per_ticker=10)
        assert len(out) == 2

    def test_does_not_filter_by_headline_content(self):
        # sample_evenly must be content-agnostic (D5) — it only looks at
        # date spacing, never at Article_title text.
        rows = []
        for i in range(20):
            row = _make_news_row("AAPL", f"2023-01-{(i % 27) + 1:02d}")
            row["Article_title"] = "irrelevant listicle with no keywords"
            rows.append(row)
        df = pd.DataFrame(rows)
        out = sample_evenly(df, n_per_ticker=5)
        assert len(out) == 5
        assert (out["Article_title"] == "irrelevant listicle with no keywords").all()
