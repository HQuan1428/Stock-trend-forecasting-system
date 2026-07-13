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


# ---------------------------------------------------------------------------
# Envelope sample validation (stage boundary contracts)
# ---------------------------------------------------------------------------
#
# ``REQUIRED_SAMPLE_KEYS`` maps a stage name to the keys (and types) every
# sample must already carry BEFORE that stage runs. The chain order is:
#
#   ingest → retriever → evidence_extractor → forecast_model
#          → evidence_selector → faithfulness_evaluator
#          → sufficiency_evaluator → market_analyzer → export_csv
#
# Each stage inherits the requirements of the previous one, so the tables
# below are cumulative. ``validate_sample`` is the single validator used by
# ``stage_io.load_envelope`` at every CLI boundary.

_BASE_KEYS: Dict[str, type] = {
    "sample_id": str,
    "ticker": str,
    "forecast_time": str,
    "news": list,
}

_AFTER_RETRIEVER: Dict[str, type] = {
    **_BASE_KEYS,
    "valid_news": list,
    "invalid_future_news": list,
}

_AFTER_EXTRACTOR: Dict[str, type] = {**_AFTER_RETRIEVER, "evidence": list}

_AFTER_FORECAST: Dict[str, type] = {**_AFTER_EXTRACTOR, "forecast": dict}

_AFTER_SELECTOR: Dict[str, type] = {
    **_AFTER_FORECAST,
    "selection": dict,
    "coverage": dict,
}

_AFTER_FAITHFULNESS: Dict[str, type] = {**_AFTER_SELECTOR, "faithfulness": dict}

_AFTER_SUFFICIENCY: Dict[str, type] = {**_AFTER_FAITHFULNESS, "sufficiency": dict}

_AFTER_MARKET: Dict[str, type] = {**_AFTER_SUFFICIENCY, "market": dict}

REQUIRED_SAMPLE_KEYS: Dict[str, Dict[str, type]] = {
    # keys a sample must have BEFORE the named stage runs
    "retriever": _BASE_KEYS,
    "evidence_extractor": _AFTER_RETRIEVER,
    "forecast_model": _AFTER_EXTRACTOR,
    "evidence_selector": _AFTER_FORECAST,
    "faithfulness_evaluator": _AFTER_SELECTOR,
    "sufficiency_evaluator": _AFTER_FAITHFULNESS,
    "market_analyzer": _AFTER_SUFFICIENCY,
    "export_csv": _AFTER_MARKET,
}


def validate_sample(sample: Any, stage: str) -> List[str]:
    """Return a list of error messages for ``sample`` entering ``stage``.

    An empty list means the sample is valid. Each message names the
    offending ``sample_id`` (or its position placeholder) and key so CLI
    users can locate the problem in the envelope file. ``stage`` must be
    a key of :data:`REQUIRED_SAMPLE_KEYS`.
    """
    if stage not in REQUIRED_SAMPLE_KEYS:
        raise ValueError(f"unknown stage: {stage!r}")
    if not isinstance(sample, dict):
        return [f"sample is not a dict (got {type(sample).__name__})"]
    sid = sample.get("sample_id", "<missing sample_id>")
    errors: List[str] = []
    for key, expected_type in REQUIRED_SAMPLE_KEYS[stage].items():
        if key not in sample:
            errors.append(f"sample {sid!r}: missing required key {key!r}")
        elif not isinstance(sample[key], expected_type):
            errors.append(
                f"sample {sid!r}: key {key!r} must be {expected_type.__name__}, "
                f"got {type(sample[key]).__name__}"
            )
    return errors


__all__ = [
    "NewsRecord",
    "EvidenceItem",
    "ForecastResult",
    "FaithfulnessResult",
    "PipelineResult",
    "REQUIRED_SAMPLE_KEYS",
    "validate_sample",
]