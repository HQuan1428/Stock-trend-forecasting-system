"""Regression suite for the temporal leakage guarantee.

These tests assert the single, hard guarantee of the Temporal Retriever:
no news item with ``news_time > forecast_time`` may ever appear in
``valid_news``. If any of these tests fail, the leakage contract is
broken and downstream consumers can no longer trust the retriever.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.retriever import retrieve_valid_news


FORECAST = datetime(2025, 3, 12, 9, 0, 0)


@pytest.mark.parametrize(
    "delta",
    [
        timedelta(seconds=1),
        timedelta(minutes=1),
        timedelta(hours=6),
        timedelta(days=1),
        timedelta(weeks=1),
    ],
)
def test_future_news_never_leaks_into_valid_news(delta: timedelta) -> None:
    forecast_time = FORECAST.isoformat()
    future_time = (FORECAST + delta).isoformat()
    result = retrieve_valid_news(
        forecast_time=forecast_time,
        news=[{"news_id": "f1", "news_time": future_time, "text": "future"}],
    )
    assert result.valid_news == [], (
        f"Leakage at offset {delta}: future item appeared in valid_news"
    )
    assert len(result.invalid_future_news) == 1


@pytest.mark.parametrize(
    "delta",
    [
        timedelta(seconds=1),
        timedelta(minutes=1),
        timedelta(hours=6),
        timedelta(days=1),
        timedelta(weeks=1),
    ],
)
def test_future_news_preserved_in_invalid_future_news(delta: timedelta) -> None:
    forecast_time = FORECAST.isoformat()
    future_time = (FORECAST + delta).isoformat()
    result = retrieve_valid_news(
        forecast_time=forecast_time,
        news=[{"news_id": "f1", "news_time": future_time, "text": "future"}],
    )
    # Future item must NOT be silently dropped.
    assert len(result.invalid_future_news) == 1
    assert result.invalid_future_news[0]["news_id"] == "f1"


@pytest.mark.parametrize(
    "delta",
    [
        timedelta(seconds=1),
        timedelta(minutes=1),
        timedelta(hours=6),
        timedelta(days=1),
        timedelta(weeks=1),
    ],
)
def test_future_news_never_leaks_when_ticker_filter_matches(delta: timedelta) -> None:
    """Ticker-matched future items must also be excluded from valid_news.

    Regression: the ticker filter runs BEFORE the time filter, so a
    ticker match alone does not let a future item slip through.
    """
    forecast_time = FORECAST.isoformat()
    future_time = (FORECAST + delta).isoformat()
    result = retrieve_valid_news(
        forecast_time=forecast_time,
        ticker="AAPL",
        news=[
            {
                "news_id": "f1",
                "news_time": future_time,
                "text": "future",
                "ticker": "AAPL",
            }
        ],
    )
    assert result.valid_news == [], (
        f"Leakage at offset {delta} with ticker filter on: future item appeared in valid_news"
    )
    assert len(result.invalid_future_news) == 1
    assert result.errors == []


def test_ticker_mismatch_does_not_leak_future_into_valid_news() -> None:
    """Ticker mismatch + future must NOT route the item to valid_news.

    The item should land in ``errors`` (ticker filter runs first), not
    ``invalid_future_news`` (time filter never runs).
    """
    forecast_time = FORECAST.isoformat()
    result = retrieve_valid_news(
        forecast_time=forecast_time,
        ticker="AAPL",
        news=[
            {
                "news_id": "f1",
                "news_time": "2025-03-12 15:30",  # future
                "text": "future",
                "ticker": "GOOGL",  # mismatch
            }
        ],
    )
    assert result.valid_news == []
    assert result.invalid_future_news == []
    assert len(result.errors) == 1
    assert result.errors[0]["reason"] == "ticker_mismatch"


def test_equal_timestamp_is_valid_not_invalid() -> None:
    # Boundary: 0 seconds in the future is still considered valid.
    result = retrieve_valid_news(
        forecast_time=FORECAST.isoformat(),
        news=[{"news_id": "e1", "news_time": FORECAST.isoformat(), "text": "equal"}],
    )
    assert len(result.valid_news) == 1
    assert result.invalid_future_news == []


def test_no_future_item_in_large_mixed_input() -> None:
    """A bulkier check: 100 items with mixed timestamps, none future-leak."""
    news = []
    for i in range(50):
        news.append(
            {
                "news_id": f"past{i}",
                "news_time": (FORECAST - timedelta(hours=i + 1)).isoformat(),
                "text": "x",
            }
        )
    for i in range(50):
        news.append(
            {
                "news_id": f"future{i}",
                "news_time": (FORECAST + timedelta(hours=i + 1)).isoformat(),
                "text": "x",
            }
        )
    result = retrieve_valid_news(forecast_time=FORECAST.isoformat(), news=news)
    # Every item in valid_news must have news_time <= forecast_time.
    forecast_dt = FORECAST
    for item in result.valid_news:
        news_dt = datetime.fromisoformat(item["news_time"].replace(" ", "T"))
        assert news_dt <= forecast_dt, f"Leakage: {item['news_id']}"
    # Invariant
    assert (
        len(result.valid_news) + len(result.invalid_future_news) + len(result.errors)
        == result.total_count
    )
