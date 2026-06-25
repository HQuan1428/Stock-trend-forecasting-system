"""Temporal Retriever.

The first filtering stage in the faithful-evidence-forecasting pipeline.
Given a ``forecast_time`` and a list of news items, it partitions the news
into two non-overlapping groups based on publication time:

- ``valid_news``         — items whose ``news_time <= forecast_time``
- ``invalid_future_news`` — items whose ``news_time >  forecast_time``

Malformed ``news_time`` values are excluded from both groups and reported
in a structured ``errors`` list. The service is a deterministic,
side-effect-free, rule-based pure function. It has no ML, LLM, network,
or external-service dependencies.

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

    Args:
        forecast_time: ISO 8601 timestamp string. Naive values are
            interpreted as UTC. Required.
        news: List of news dicts. Each dict must contain ``news_id`` and
            ``news_time``; the body must be under ``text`` or
            ``news_text``. Extra fields are passed through unchanged.
        ticker: Optional ticker symbol. Echoed in the response as-is; it
            is NOT used as a filter.

    Returns:
        A :class:`RetrievalResult` with non-overlapping ``valid_news``
        and ``invalid_future_news`` groups, counts, ``temporal_validity``
        ratio, and any structured ``errors`` for malformed items.

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

    # --- 2. Partition each news item -------------------------------------
    valid_news: List[Dict[str, Any]] = []
    invalid_future_news: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for item in news:
        # Copy without mutation; the copy preserves all original keys.
        item_copy: Dict[str, Any] = dict(item)

        raw_news_time = item.get("news_time")
        news_id = item.get("news_id")
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

    # --- 3. Counts and temporal_validity --------------------------------
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
