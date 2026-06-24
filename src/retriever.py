"""Temporal Retriever.

The first filtering stage in the faithful-evidence-forecasting pipeline.
Given a ``forecast_time`` and a list of news items, it partitions the news
into two non-overlapping groups based on publication time:

- ``valid_news``         — items whose ``news_time <= forecast_time``
- ``invalid_future_news`` — items whose ``news_time >  forecast_time``

When the request specifies a ``ticker`` (non-``None``, non-empty string),
the retriever additionally filters by ticker BEFORE the time filter:
only news items whose own ``ticker`` field equals the request ticker
(case-sensitive string equality) are kept. Items with a mismatched or
missing ``ticker`` are excluded from both time groups and reported in
the structured ``errors`` list with ``reason = "ticker_mismatch"`` or
``reason = "missing_ticker"``. When the request omits ``ticker`` (``None``
or empty string), the ticker filter is skipped entirely and every news
item is passed to the time filter (backward-compatible behavior).

Malformed ``news_time`` values are likewise excluded from both groups
and reported in ``errors`` with ``reason = "missing_or_malformed_news_time"``.
The service is a deterministic, side-effect-free, rule-based pure
function. It has no ML, LLM, network, or external-service dependencies.

Project-local timezone: UTC.
    Naive timestamps (no offset) are interpreted as UTC. Timezone-aware
    timestamps are converted to UTC before comparison. This is the
    project convention per ``design.md`` Decision 5.

Field preservation:
    The retriever copies every input news dict into the response without
    mutation, without renaming fields, and without dropping any key.
    Both ``text`` and ``news_text`` are accepted as the body field;
    whichever the input uses is preserved verbatim in the response.
    Downstream consumers can read either via
    ``item.get("text") or item.get("news_text")``.

Ticker filter semantics:
    The retriever matches on the news item's ``ticker`` field (a single
    string). Case-sensitive, exact-match. The request ``ticker`` is
    echoed as-is in the response, regardless of whether it acted as a
    filter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TemporalValidationError(ValueError):
    """Raised for unrecoverable input problems (e.g. malformed forecast_time)."""


# ---------------------------------------------------------------------------
# Datetime parsing helpers
# ---------------------------------------------------------------------------


def _parse_datetime(value: str) -> datetime:
    """Parse an ISO 8601 timestamp string with either ``T`` or `` `` separator.

    Accepts naive and timezone-aware inputs. Returns a ``datetime`` whose
    ``tzinfo`` is ``None`` for naive inputs and set for aware inputs.

    Raises ``ValueError`` for missing, non-string, or unparseable input.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"timestamp must be a non-empty string, got {value!r}")
    # ``datetime.fromisoformat`` in Python 3.11+ accepts both "T" and " "
    # separators. Normalize " " to "T" for older runtimes.
    normalized = value.strip().replace(" ", "T")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"unparseable timestamp: {value!r}") from exc


def _normalize_to_utc(dt: datetime) -> datetime:
    """Normalize a datetime to UTC.

    - Timezone-aware datetimes are converted to UTC.
    - Naive datetimes are interpreted as UTC (per Decision 5:
      project-local timezone is UTC) by attaching ``timezone.utc``.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetrievalResult:
    """Immutable response from :func:`retrieve_valid_news`.

    The ``valid_news`` and ``invalid_future_news`` lists contain the
    original input news dicts (deep-copied) — no field is dropped,
    renamed, or rewritten. ``errors`` is always present and may be empty.
    """

    ticker: Optional[str]
    forecast_time: str
    valid_news: List[Dict[str, Any]]
    invalid_future_news: List[Dict[str, Any]]
    valid_count: int
    invalid_future_count: int
    total_count: int
    temporal_validity: float
    errors: List[Dict[str, Any]] = field(default_factory=list)


# ``NewsItem`` is documented as a contract; the retriever itself accepts
# generic dicts so callers can pass arbitrary extra fields. We expose a
# TypedDict for static-typing convenience without enforcing it at runtime.
try:
    from typing import TypedDict  # Python 3.8+
except ImportError:  # pragma: no cover
    TypedDict = None  # type: ignore[assignment]

if TypedDict is not None:

    class NewsItem(TypedDict, total=False):
        """Contract for a news item accepted by ``retrieve_valid_news``.

        All fields except ``news_id`` and ``news_time`` are optional in the
        sense that they may be absent, but the body must be present under
        either ``text`` or ``news_text``. Extra fields are allowed and
        passed through unchanged.
        """

        news_id: str
        news_time: str
        title: Optional[str]
        text: str
        news_text: str


# ---------------------------------------------------------------------------
# Core filter
# ---------------------------------------------------------------------------


def retrieve_valid_news(
    forecast_time: str,
    news: List[Dict[str, Any]],
    ticker: Optional[str] = None,
) -> RetrievalResult:
    """Partition ``news`` into valid / invalid groups relative to ``forecast_time``.

    When ``ticker`` is provided (non-``None``, non-empty string), the
    retriever first keeps only news items whose own ``ticker`` field
    equals ``ticker`` (case-sensitive string equality). Items with a
    mismatched or missing ``ticker`` are routed to ``errors`` and do
    NOT reach the time filter.

    Args:
        forecast_time: ISO 8601 timestamp string. Naive values are
            interpreted as UTC. Required.
        news: List of news dicts. Each dict must contain ``news_id`` and
            ``news_time``; the body must be under ``text`` or
            ``news_text``. Each dict may carry a ``ticker`` field; if
            the request specifies a ticker filter, items whose ``ticker``
            does not match are excluded. Extra fields are passed
            through unchanged.
        ticker: Optional ticker symbol. When non-``None`` and non-empty,
            it acts as a case-sensitive exact-match filter on each
            news item's ``ticker`` field. When ``None`` or empty, the
            ticker filter is skipped. Echoed as-is in the response.

    Returns:
        A :class:`RetrievalResult` with non-overlapping ``valid_news``
        and ``invalid_future_news`` groups, counts, ``temporal_validity``
        ratio, and any structured ``errors`` for ticker-mismatched,
        ticker-missing, or malformed-time items.

    Raises:
        TemporalValidationError: if ``forecast_time`` is missing, null,
            or not a parseable timestamp.
    """
    # --- 1. Validate and parse forecast_time (hard fail) -----------------
    if forecast_time is None or not isinstance(forecast_time, str) or not forecast_time.strip():
        raise TemporalValidationError(
            f"forecast_time must be a non-empty string, got {forecast_time!r}"
        )
    try:
        forecast_dt = _normalize_to_utc(_parse_datetime(forecast_time))
    except ValueError as exc:
        raise TemporalValidationError(
            f"forecast_time is not a parseable timestamp: {forecast_time!r}"
        ) from exc

    # --- 2. Ticker filter (per Decision 7) -------------------------------
    # ``ticker_filter_on`` is True only when the request specifies a
    # non-empty ticker. ``None`` and "" both skip the filter.
    ticker_filter_on = isinstance(ticker, str) and bool(ticker.strip())

    # --- 3. Partition each news item -------------------------------------
    valid_news: List[Dict[str, Any]] = []
    invalid_future_news: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for item in news:
        # Copy without mutation; the copy preserves all original keys.
        item_copy: Dict[str, Any] = dict(item)
        news_id = item.get("news_id")

        # --- 3a. Ticker filter (runs before the time filter) -------------
        if ticker_filter_on:
            item_ticker = item.get("ticker")
            if not isinstance(item_ticker, str) or not item_ticker.strip():
                # Missing ticker (None, empty string, or non-string).
                errors.append(
                    {
                        "news_id": news_id,
                        "reason": "missing_ticker",
                    }
                )
                continue
            if item_ticker != ticker:
                # Ticker is present but does not match the request.
                errors.append(
                    {
                        "news_id": news_id,
                        "reason": "ticker_mismatch",
                        "raw_value": item_ticker,
                    }
                )
                continue

        # --- 3b. Time filter ------------------------------------------
        raw_news_time = item.get("news_time")
        if raw_news_time is None or not isinstance(raw_news_time, str) or not raw_news_time.strip():
            errors.append(
                {
                    "news_id": news_id,
                    "reason": "missing_or_malformed_news_time",
                    "raw_value": raw_news_time,
                }
            )
            continue
        try:
            news_dt = _normalize_to_utc(_parse_datetime(raw_news_time))
        except ValueError:
            errors.append(
                {
                    "news_id": news_id,
                    "reason": "missing_or_malformed_news_time",
                    "raw_value": raw_news_time,
                }
            )
            continue

        if news_dt <= forecast_dt:
            valid_news.append(item_copy)
        else:
            invalid_future_news.append(item_copy)

    # --- 4. Counts and temporal_validity --------------------------------
    valid_count = len(valid_news)
    invalid_future_count = len(invalid_future_news)
    total_count = len(news)
    temporal_validity = (valid_count / total_count) if total_count > 0 else 0.0

    return RetrievalResult(
        ticker=ticker,
        forecast_time=forecast_time,  # echoed as-is per spec
        valid_news=valid_news,
        invalid_future_news=invalid_future_news,
        valid_count=valid_count,
        invalid_future_count=invalid_future_count,
        total_count=total_count,
        temporal_validity=temporal_validity,
        errors=errors,
    )
