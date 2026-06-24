"""Unit tests for the Temporal Retriever."""

from __future__ import annotations

import pytest

from src.retriever import (
    RetrievalResult,
    TemporalValidationError,
    retrieve_valid_news,
)


# ---------------------------------------------------------------------------
# Boundary cases
# ---------------------------------------------------------------------------


def test_past_news_is_treated_as_valid() -> None:
    result = retrieve_valid_news(
        forecast_time="2025-03-12 09:00",
        news=[{"news_id": "n1", "news_time": "2025-03-11 08:30", "text": "Past"}],
    )
    assert len(result.valid_news) == 1
    assert result.valid_news[0]["news_id"] == "n1"
    assert result.invalid_future_news == []


def test_news_at_exactly_forecast_time_is_valid() -> None:
    result = retrieve_valid_news(
        forecast_time="2025-03-12 09:00",
        news=[{"news_id": "n1", "news_time": "2025-03-12 09:00", "text": "Equal"}],
    )
    assert len(result.valid_news) == 1
    assert result.invalid_future_news == []


def test_news_one_second_in_the_future_is_invalid() -> None:
    result = retrieve_valid_news(
        forecast_time="2025-03-12 09:00:00",
        news=[{"news_id": "n1", "news_time": "2025-03-12 09:00:01", "text": "Just after"}],
    )
    assert result.valid_news == []
    assert len(result.invalid_future_news) == 1


def test_news_six_hours_in_the_future_is_invalid() -> None:
    result = retrieve_valid_news(
        forecast_time="2025-03-12 09:00",
        news=[{"news_id": "n1", "news_time": "2025-03-12 15:30", "text": "Future"}],
    )
    assert result.valid_news == []
    assert len(result.invalid_future_news) == 1


# ---------------------------------------------------------------------------
# Group membership and ordering
# ---------------------------------------------------------------------------


def test_mixed_list_partitions_into_non_overlapping_groups() -> None:
    news = [
        {"news_id": "n1", "news_time": "2025-03-11 08:30", "text": "Past"},
        {"news_id": "n2", "news_time": "2025-03-12 09:00", "text": "Equal"},
        {"news_id": "n3", "news_time": "2025-03-12 15:30", "text": "Future"},
    ]
    result = retrieve_valid_news(forecast_time="2025-03-12 09:00", news=news)
    assert [n["news_id"] for n in result.valid_news] == ["n1", "n2"]
    assert [n["news_id"] for n in result.invalid_future_news] == ["n3"]
    # Non-overlapping
    valid_ids = {n["news_id"] for n in result.valid_news}
    future_ids = {n["news_id"] for n in result.invalid_future_news}
    assert valid_ids.isdisjoint(future_ids)


# ---------------------------------------------------------------------------
# Counts and ratios
# ---------------------------------------------------------------------------


def test_counts_and_temporal_validity_reported_correctly() -> None:
    news = [
        {"news_id": f"p{i}", "news_time": "2025-03-11 08:00", "text": "x"}
        for i in range(3)
    ] + [
        {"news_id": "e1", "news_time": "2025-03-12 09:00", "text": "x"},
    ] + [
        {"news_id": f"f{i}", "news_time": "2025-03-12 15:00", "text": "x"}
        for i in range(2)
    ]
    result = retrieve_valid_news(forecast_time="2025-03-12 09:00", news=news)
    assert result.valid_count == 4
    assert result.invalid_future_count == 2
    assert result.total_count == 6
    assert result.temporal_validity == pytest.approx(4 / 6, abs=1e-9)


def test_all_valid_list_has_temporal_validity_of_one() -> None:
    news = [
        {"news_id": "n1", "news_time": "2025-03-10 09:00", "text": "x"},
        {"news_id": "n2", "news_time": "2025-03-11 09:00", "text": "x"},
        {"news_id": "n3", "news_time": "2025-03-12 09:00", "text": "x"},
    ]
    result = retrieve_valid_news(forecast_time="2025-03-12 09:00", news=news)
    assert result.valid_count == 3
    assert result.invalid_future_count == 0
    assert result.temporal_validity == 1.0


def test_all_invalid_list_has_temporal_validity_of_zero() -> None:
    news = [
        {"news_id": "n1", "news_time": "2025-03-13 09:00", "text": "x"},
        {"news_id": "n2", "news_time": "2025-03-14 09:00", "text": "x"},
        {"news_id": "n3", "news_time": "2025-03-15 09:00", "text": "x"},
    ]
    result = retrieve_valid_news(forecast_time="2025-03-12 09:00", news=news)
    assert result.valid_count == 0
    assert result.invalid_future_count == 3
    assert result.temporal_validity == 0.0


def test_empty_list_produces_zero_counts_and_zero_validity() -> None:
    result = retrieve_valid_news(forecast_time="2025-03-12 09:00", news=[])
    assert result.valid_news == []
    assert result.invalid_future_news == []
    assert result.valid_count == 0
    assert result.invalid_future_count == 0
    assert result.total_count == 0
    assert result.temporal_validity == 0.0
    assert result.errors == []


# ---------------------------------------------------------------------------
# Field preservation
# ---------------------------------------------------------------------------


def test_all_input_fields_are_preserved_verbatim() -> None:
    item = {
        "news_id": "n1",
        "news_time": "2025-03-11 08:30",
        "title": "Past headline",
        "text": "Past body",
        "extra_field": "extra_value",
    }
    result = retrieve_valid_news(forecast_time="2025-03-12 09:00", news=[item])
    assert result.valid_news[0] == item


def test_news_text_input_is_preserved_as_is() -> None:
    item = {
        "news_id": "n2",
        "news_time": "2025-03-11 08:30",
        "news_text": "Body under the news_text key",
    }
    result = retrieve_valid_news(forecast_time="2025-03-12 09:00", news=[item])
    # Field name preserved verbatim — no synthetic 'text' created.
    assert "news_text" in result.valid_news[0]
    assert result.valid_news[0]["news_text"] == "Body under the news_text key"
    assert "text" not in result.valid_news[0]


# ---------------------------------------------------------------------------
# Ticker filter (Decision 7)
# ---------------------------------------------------------------------------


def test_ticker_is_echoed_when_provided() -> None:
    result = retrieve_valid_news(
        forecast_time="2025-03-12 09:00",
        ticker="AAPL",
        news=[
            {
                "news_id": "n1",
                "news_time": "2025-03-11 08:00",
                "text": "x",
                "ticker": "AAPL",
            }
        ],
    )
    assert result.ticker == "AAPL"


def test_ticker_defaults_to_none_when_absent() -> None:
    result = retrieve_valid_news(
        forecast_time="2025-03-12 09:00",
        news=[{"news_id": "n1", "news_time": "2025-03-11 08:00", "text": "x"}],
    )
    assert result.ticker is None

    result2 = retrieve_valid_news(
        forecast_time="2025-03-12 09:00",
        ticker=None,
        news=[{"news_id": "n1", "news_time": "2025-03-11 08:00", "text": "x"}],
    )
    assert result2.ticker is None


def test_ticker_filter_keeps_only_matching_items() -> None:
    """When ticker is set, only items whose ticker matches reach the time filter."""
    news = [
        {
            "news_id": "a1",
            "news_time": "2025-03-11 08:00",
            "text": "Apple past",
            "ticker": "AAPL",
        },
        {
            "news_id": "g1",
            "news_time": "2025-03-11 08:30",
            "text": "Google past",
            "ticker": "GOOGL",
        },
        {
            "news_id": "a2",
            "news_time": "2025-03-11 09:00",
            "text": "Apple past 2",
            "ticker": "AAPL",
        },
    ]
    result = retrieve_valid_news(forecast_time="2025-03-12 09:00", ticker="AAPL", news=news)
    # The two AAPL items are past the forecast -> valid.
    assert result.valid_count == 2
    assert result.invalid_future_count == 0
    assert {n["news_id"] for n in result.valid_news} == {"a1", "a2"}
    # The GOOGL item is excluded by the ticker filter, NOT silently dropped.
    assert len(result.errors) == 1
    err = result.errors[0]
    assert err["news_id"] == "g1"
    assert err["reason"] == "ticker_mismatch"
    assert err["raw_value"] == "GOOGL"
    # Partition invariant still holds.
    assert (
        len(result.valid_news)
        + len(result.invalid_future_news)
        + len(result.errors)
        == result.total_count
    )


def test_ticker_filter_is_case_sensitive() -> None:
    """Ticker match is case-sensitive: 'aapl' != 'AAPL'."""
    result = retrieve_valid_news(
        forecast_time="2025-03-12 09:00",
        ticker="AAPL",
        news=[
            {
                "news_id": "n1",
                "news_time": "2025-03-11 08:00",
                "text": "x",
                "ticker": "aapl",
            }
        ],
    )
    assert result.valid_count == 0
    assert result.invalid_future_count == 0
    assert len(result.errors) == 1
    err = result.errors[0]
    assert err["reason"] == "ticker_mismatch"
    assert err["raw_value"] == "aapl"


def test_news_item_missing_ticker_is_excluded_with_missing_ticker_reason() -> None:
    """When the request sets a ticker, items without a ticker go to errors."""
    result = retrieve_valid_news(
        forecast_time="2025-03-12 09:00",
        ticker="AAPL",
        news=[
            {
                "news_id": "n1",
                "news_time": "2025-03-11 08:00",
                "text": "x",
                "ticker": "AAPL",
            },
            {
                "news_id": "n2",
                "news_time": "2025-03-11 08:30",
                "text": "y",
                # No ticker field at all.
            },
            {
                "news_id": "n3",
                "news_time": "2025-03-11 09:00",
                "text": "z",
                "ticker": None,
            },
            {
                "news_id": "n4",
                "news_time": "2025-03-11 09:30",
                "text": "w",
                "ticker": "",
            },
        ],
    )
    assert result.valid_count == 1
    assert result.valid_news[0]["news_id"] == "n1"
    assert len(result.errors) == 3
    for err in result.errors:
        assert err["reason"] == "missing_ticker"


def test_ticker_none_skips_the_ticker_filter() -> None:
    """When ticker=None, the ticker filter is skipped and all items reach the time filter."""
    news = [
        {
            "news_id": "a1",
            "news_time": "2025-03-11 08:00",
            "text": "x",
            "ticker": "AAPL",
        },
        {
            "news_id": "g1",
            "news_time": "2025-03-11 08:30",
            "text": "y",
            "ticker": "GOOGL",
        },
        {
            "news_id": "n3",
            "news_time": "2025-03-11 09:00",
            "text": "z",
            # No ticker.
        },
    ]
    result = retrieve_valid_news(forecast_time="2025-03-12 09:00", ticker=None, news=news)
    # All three items are past the forecast -> all valid, no errors.
    assert result.valid_count == 3
    assert result.invalid_future_count == 0
    assert result.errors == []


def test_ticker_empty_string_is_treated_as_none() -> None:
    """When ticker="", the filter is skipped and ticker is echoed as-is."""
    news = [
        {
            "news_id": "a1",
            "news_time": "2025-03-11 08:00",
            "text": "x",
            "ticker": "AAPL",
        },
        {
            "news_id": "g1",
            "news_time": "2025-03-11 08:30",
            "text": "y",
            "ticker": "GOOGL",
        },
    ]
    result = retrieve_valid_news(forecast_time="2025-03-12 09:00", ticker="", news=news)
    # Filter skipped -> both items reach the time filter.
    assert result.valid_count == 2
    assert result.errors == []
    # Echoed as-is.
    assert result.ticker == ""


def test_partition_invariant_holds_under_ticker_filtering() -> None:
    """All three error reasons coexist; invariant still holds."""
    news = [
        {
            "news_id": "n1",
            "news_time": "2025-03-11 08:00",
            "text": "valid",
            "ticker": "AAPL",
        },
        {
            "news_id": "n2",
            "news_time": "2025-03-12 15:00",
            "text": "future",
            "ticker": "AAPL",
        },
        {
            "news_id": "n3",
            "news_time": "2025-03-12 08:00",
            "text": "wrong ticker",
            "ticker": "GOOGL",
        },
        {
            "news_id": "n4",
            "news_time": "2025-03-12 08:00",
            "text": "no ticker",
            # No ticker.
        },
        {
            "news_id": "n5",
            "news_time": "bad",
            "text": "bad time",
            "ticker": "AAPL",
        },
    ]
    result = retrieve_valid_news(forecast_time="2025-03-12 09:00", ticker="AAPL", news=news)
    # n1 -> valid, n2 -> invalid_future, n3 -> ticker_mismatch, n4 -> missing_ticker,
    # n5 -> missing_or_malformed_news_time
    assert result.valid_count == 1
    assert result.invalid_future_count == 1
    assert len(result.errors) == 3
    reasons = sorted(err["reason"] for err in result.errors)
    assert reasons == [
        "missing_or_malformed_news_time",
        "missing_ticker",
        "ticker_mismatch",
    ]
    assert (
        len(result.valid_news)
        + len(result.invalid_future_news)
        + len(result.errors)
        == result.total_count
    )


# ---------------------------------------------------------------------------
# forecast_time validation
# ---------------------------------------------------------------------------


def test_missing_forecast_time_raises_temporal_validation_error() -> None:
    with pytest.raises(TemporalValidationError):
        retrieve_valid_news(forecast_time="", news=[])


def test_malformed_forecast_time_raises_temporal_validation_error() -> None:
    with pytest.raises(TemporalValidationError):
        retrieve_valid_news(forecast_time="not-a-date", news=[])


def test_forecast_time_is_echoed_verbatim() -> None:
    raw = "2025-03-12 09:00"
    result = retrieve_valid_news(
        forecast_time=raw, news=[{"news_id": "n1", "news_time": "2025-03-11 08:00", "text": "x"}]
    )
    assert result.forecast_time == raw


# ---------------------------------------------------------------------------
# news_time validation
# ---------------------------------------------------------------------------


def test_malformed_news_time_populates_errors_list() -> None:
    news = [
        {"news_id": "n1", "news_time": "2025-03-11 08:00", "text": "valid"},
        {"news_id": "n2", "news_time": None, "text": "missing"},
        {"news_id": "n3", "news_time": "not-a-date", "text": "bad"},
        {"news_id": "n4", "news_time": "2025-03-12 15:00", "text": "future"},
    ]
    result = retrieve_valid_news(forecast_time="2025-03-12 09:00", news=news)
    assert result.valid_count == 1
    assert result.invalid_future_count == 1
    assert len(result.errors) == 2
    for err in result.errors:
        assert err["reason"] == "missing_or_malformed_news_time"
        assert "news_id" in err
        assert "raw_value" in err
    # The malformed items are NOT silently dropped — invariant holds.
    assert (
        len(result.valid_news) + len(result.invalid_future_news) + len(result.errors)
        == result.total_count
    )


# ---------------------------------------------------------------------------
# Timezone handling
# ---------------------------------------------------------------------------


def test_naive_timestamp_is_interpreted_as_utc() -> None:
    # forecast_time is naive (09:00 UTC). news_time is timezone-aware 08:30 UTC.
    # Naive 09:00 is later than aware 08:30 → news is valid.
    result = retrieve_valid_news(
        forecast_time="2025-03-12 09:00",
        news=[{"news_id": "n1", "news_time": "2025-03-12 08:30+00:00", "text": "x"}],
    )
    assert result.valid_count == 1
    assert result.invalid_future_count == 0


def test_offset_aware_timestamp_is_normalized_to_utc() -> None:
    # 17:00 in UTC+7 == 10:00 UTC. forecast is naive 09:00 UTC → 10:00 > 09:00 → future.
    result = retrieve_valid_news(
        forecast_time="2025-03-12 09:00",
        news=[{"news_id": "n1", "news_time": "2025-03-12T17:00:00+07:00", "text": "x"}],
    )
    assert result.valid_count == 0
    assert result.invalid_future_count == 1


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_identical_requests_produce_identical_responses() -> None:
    payload = {
        "forecast_time": "2025-03-12 09:00",
        "ticker": "AAPL",
        "news": [
            {"news_id": "n1", "news_time": "2025-03-11 08:00", "text": "x"},
            {"news_id": "n2", "news_time": "2025-03-12 15:30", "text": "y"},
            {"news_id": "n3", "news_time": "garbage", "text": "z"},
        ],
    }
    r1 = retrieve_valid_news(**payload)
    r2 = retrieve_valid_news(**payload)
    # Compare every observable field.
    assert r1.valid_news == r2.valid_news
    assert r1.invalid_future_news == r2.invalid_future_news
    assert r1.errors == r2.errors
    assert r1.valid_count == r2.valid_count
    assert r1.invalid_future_count == r2.invalid_future_count
    assert r1.total_count == r2.total_count
    assert r1.temporal_validity == r2.temporal_validity
    assert r1.forecast_time == r2.forecast_time
    assert r1.ticker == r2.ticker


# ---------------------------------------------------------------------------
# Invariant
# ---------------------------------------------------------------------------


def test_partition_invariant_holds_with_malformed_items() -> None:
    news = [
        {"news_id": "n1", "news_time": "2025-03-11 08:00", "text": "valid"},
        {"news_id": "n2", "news_time": "2025-03-12 15:00", "text": "future"},
        {"news_id": "n3", "news_time": "bad", "text": "malformed"},
    ]
    result = retrieve_valid_news(forecast_time="2025-03-12 09:00", news=news)
    assert (
        len(result.valid_news) + len(result.invalid_future_news) + len(result.errors)
        == result.total_count
    )


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


def test_returns_retrieval_result_instance() -> None:
    result = retrieve_valid_news(forecast_time="2025-03-12 09:00", news=[])
    assert isinstance(result, RetrievalResult)
