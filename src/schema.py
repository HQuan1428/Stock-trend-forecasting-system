"""Shared data contracts for the end-to-end forecasting pipeline.

These dataclasses document the cross-stage data flow:

    NewsRecord  ─►  EvidenceItem  ─►  ForecastResult  ─►  FaithfulnessResult
                                                          │
                                                          ▼
                                                       PipelineResult

The fields are intentionally a superset of what every existing module
emits; the pipeline does the field-level mapping so each upstream
function can keep its existing API contract.

The dataclasses are NOT used as runtime types — the existing modules
take and return plain ``dict``\\s. They exist to make the integration
explicit in one place and to give readers (and tests) a single document
to look at.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class NewsRecord:
    """One raw row from the input CSV.

    Mirrors the schema of ``data/sample_dataset.csv``:
    ``news_id, ticker, forecast_time, news_time, news_text, label``.
    """

    news_id: str
    ticker: str
    forecast_time: str
    news_time: str
    news_text: str
    label: str = ""


@dataclass
class EvidenceItem:
    """One piece of evidence produced by the Evidence Extractor and
    classified by the Evidence Selector.

    ``evidence_role`` is one of ``"pro"``, ``"counter"``, ``"neutral"``
    (or ``"uncited"`` if the item is in the neutral bucket and was not
    cited by the Forecast Model).
    """

    evidence_id: str
    news_id: str
    news_time: str
    evidence_text: str
    polarity: str
    expected_direction: str
    support_score: float
    evidence_role: str = "neutral"
    is_cited: bool = False


@dataclass
class ForecastResult:
    """The Forecast Model's output for one (ticker, forecast_time) group.

    Field names match the public Forecast Model API. ``pro_evidence`` /
    ``counter_evidence`` are the lists actually used by the model; they
    are populated by the pipeline from the Evidence Selector output.
    """

    prediction: str
    confidence: float
    score: int
    positive_count: int
    negative_count: int
    neutral_count: int
    rationale: str
    warnings: List[str] = field(default_factory=list)


@dataclass
class FaithfulnessResult:
    """The Faithfulness Evaluator's output for one prediction."""

    temporal_validity: float
    evidence_support: float
    confidence_drop: float
    faithfulness_label: str


@dataclass
class PipelineResult:
    """The full result of running the pipeline on one input CSV.

    One ``PipelineResult`` aggregates all groups produced from the input
    rows. The four CSV writers each pull their rows from this object.
    """

    ticker: str
    forecast_time: str
    prediction: str
    faithfulness_label: str
    valid_news_count: int
    invalid_future_news_count: int


__all__ = [
    "NewsRecord",
    "EvidenceItem",
    "ForecastResult",
    "FaithfulnessResult",
    "PipelineResult",
]