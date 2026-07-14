"""Regression suite for the temporal leakage guarantee.

These tests assert the single, hard guarantee of the Temporal Retriever:
no news item with ``news_time > forecast_time`` may ever appear in
``valid_news``. If any of these tests fail, the leakage contract is
broken and downstream consumers can no longer trust the retriever.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.stages.retriever import TemporalRetriever

_retriever = TemporalRetriever()

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
    result = _retriever.retrieve(
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
    result = _retriever.retrieve(
        forecast_time=forecast_time,
        news=[{"news_id": "f1", "news_time": future_time, "text": "future"}],
    )
    # Future item must NOT be silently dropped.
    assert len(result.invalid_future_news) == 1
    assert result.invalid_future_news[0]["news_id"] == "f1"


def test_equal_timestamp_is_valid_not_invalid() -> None:
    # Boundary: 0 seconds in the future is still considered valid.
    result = _retriever.retrieve(
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
    result = _retriever.retrieve(forecast_time=FORECAST.isoformat(), news=news)
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
