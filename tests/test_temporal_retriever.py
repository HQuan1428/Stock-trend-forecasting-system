"""Unit tests for the Temporal Retriever."""

from __future__ import annotations

import pytest

from src.stages.retriever import RetrievalResult, TemporalRetriever, TemporalValidationError

_retriever = TemporalRetriever()


# ---------------------------------------------------------------------------
# Boundary cases
# ---------------------------------------------------------------------------


def test_past_news_is_treated_as_valid() -> None:
    result = _retriever.retrieve(
        forecast_time="2025-03-12 09:00",
        news=[{"news_id": "n1", "news_time": "2025-03-11 08:30", "text": "Past"}],
    )
    assert len(result.valid_news) == 1
    assert result.valid_news[0]["news_id"] == "n1"
    assert result.invalid_future_news == []


def test_news_at_exactly_forecast_time_is_valid() -> None:
    result = _retriever.retrieve(
        forecast_time="2025-03-12 09:00",
        news=[{"news_id": "n1", "news_time": "2025-03-12 09:00", "text": "Equal"}],
    )
    assert len(result.valid_news) == 1
    assert result.invalid_future_news == []


def test_news_one_second_in_the_future_is_invalid() -> None:
    result = _retriever.retrieve(
        forecast_time="2025-03-12 09:00:00",
        news=[{"news_id": "n1", "news_time": "2025-03-12 09:00:01", "text": "Just after"}],
    )
    assert result.valid_news == []
    assert len(result.invalid_future_news) == 1


def test_news_six_hours_in_the_future_is_invalid() -> None:
    result = _retriever.retrieve(
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
    result = _retriever.retrieve(forecast_time="2025-03-12 09:00", news=news)
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
    result = _retriever.retrieve(forecast_time="2025-03-12 09:00", news=news)
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
    result = _retriever.retrieve(forecast_time="2025-03-12 09:00", news=news)
    assert result.valid_count == 3
    assert result.invalid_future_count == 0
    assert result.temporal_validity == 1.0


def test_all_invalid_list_has_temporal_validity_of_zero() -> None:
    news = [
        {"news_id": "n1", "news_time": "2025-03-13 09:00", "text": "x"},
        {"news_id": "n2", "news_time": "2025-03-14 09:00", "text": "x"},
        {"news_id": "n3", "news_time": "2025-03-15 09:00", "text": "x"},
    ]
    result = _retriever.retrieve(forecast_time="2025-03-12 09:00", news=news)
    assert result.valid_count == 0
    assert result.invalid_future_count == 3
    assert result.temporal_validity == 0.0


def test_empty_list_produces_zero_counts_and_zero_validity() -> None:
    result = _retriever.retrieve(forecast_time="2025-03-12 09:00", news=[])
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
    result = _retriever.retrieve(forecast_time="2025-03-12 09:00", news=[item])
    assert result.valid_news[0] == item


def test_news_text_input_is_preserved_as_is() -> None:
    item = {
        "news_id": "n2",
        "news_time": "2025-03-11 08:30",
        "news_text": "Body under the news_text key",
    }
    result = _retriever.retrieve(forecast_time="2025-03-12 09:00", news=[item])
    # Field name preserved verbatim — no synthetic 'text' created.
    assert "news_text" in result.valid_news[0]
    assert result.valid_news[0]["news_text"] == "Body under the news_text key"
    assert "text" not in result.valid_news[0]


# ---------------------------------------------------------------------------
# Ticker echo
# ---------------------------------------------------------------------------


def test_ticker_is_echoed_when_provided() -> None:
    result = _retriever.retrieve(
        forecast_time="2025-03-12 09:00",
        ticker="AAPL",
        news=[{"news_id": "n1", "news_time": "2025-03-11 08:00", "text": "x"}],
    )
    assert result.ticker == "AAPL"
    # Ticker is NOT used as a filter.
    assert result.valid_count == 1


def test_ticker_defaults_to_none_when_absent() -> None:
    result = _retriever.retrieve(
        forecast_time="2025-03-12 09:00",
        news=[{"news_id": "n1", "news_time": "2025-03-11 08:00", "text": "x"}],
    )
    assert result.ticker is None

    result2 = _retriever.retrieve(
        forecast_time="2025-03-12 09:00",
        ticker=None,
        news=[{"news_id": "n1", "news_time": "2025-03-11 08:00", "text": "x"}],
    )
    assert result2.ticker is None


# ---------------------------------------------------------------------------
# forecast_time validation
# ---------------------------------------------------------------------------


def test_missing_forecast_time_raises_temporal_validation_error() -> None:
    with pytest.raises(TemporalValidationError):
        _retriever.retrieve(forecast_time="", news=[])


def test_malformed_forecast_time_raises_temporal_validation_error() -> None:
    with pytest.raises(TemporalValidationError):
        _retriever.retrieve(forecast_time="not-a-date", news=[])


def test_forecast_time_is_echoed_verbatim() -> None:
    raw = "2025-03-12 09:00"
    result = _retriever.retrieve(
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
    result = _retriever.retrieve(forecast_time="2025-03-12 09:00", news=news)
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
    result = _retriever.retrieve(
        forecast_time="2025-03-12 09:00",
        news=[{"news_id": "n1", "news_time": "2025-03-12 08:30+00:00", "text": "x"}],
    )
    assert result.valid_count == 1
    assert result.invalid_future_count == 0


def test_offset_aware_timestamp_is_normalized_to_utc() -> None:
    # 17:00 in UTC+7 == 10:00 UTC. forecast is naive 09:00 UTC → 10:00 > 09:00 → future.
    result = _retriever.retrieve(
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
    r1 = _retriever.retrieve(**payload)
    r2 = _retriever.retrieve(**payload)
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
    result = _retriever.retrieve(forecast_time="2025-03-12 09:00", news=news)
    assert (
        len(result.valid_news) + len(result.invalid_future_news) + len(result.errors)
        == result.total_count
    )


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


def test_returns_retrieval_result_instance() -> None:
    result = _retriever.retrieve(forecast_time="2025-03-12 09:00", news=[])
    assert isinstance(result, RetrievalResult)
