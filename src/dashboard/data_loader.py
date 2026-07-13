"""Load the final envelope into dashboard view-models.

Pure data layer: reads ``08_market.json``, validates every sample with
the same validator the stage boundaries use, and flattens the envelope
into three pandas DataFrames (samples / evidence / leakage) that the
metrics and chart layers consume. No Streamlit imports here — this
module is fully testable with plain pytest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from src.export_csv import compute_leakage_minutes, faithfulness_label
from src.core.schema import validate_sample

DEFAULT_ENVELOPE_PATH = "outputs/08_market.json"

RUN_HINT = (
    "Chưa có dữ liệu. Hãy chạy pipeline trước: "
    "`python -m src.runner --input data/sample_dataset.csv --output-dir outputs`"
)


class DashboardDataError(Exception):
    """Raised when the envelope is missing, unparseable, or invalid."""


def _load_envelope(path: str) -> Dict[str, Any]:
    path_obj = Path(path)
    if not path_obj.exists():
        raise DashboardDataError(f"Không tìm thấy {path}. {RUN_HINT}")
    try:
        data = json.loads(path_obj.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DashboardDataError(
            f"{path} không phải JSON hợp lệ ({exc}). {RUN_HINT}"
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("samples"), list):
        raise DashboardDataError(
            f'{path} không đúng định dạng envelope ("samples" list). {RUN_HINT}'
        )
    errors: List[str] = []
    for sample in data["samples"]:
        errors.extend(validate_sample(sample, "export_csv"))
    if errors:
        raise DashboardDataError(
            "Envelope không qua được schema validation:\n" + "\n".join(errors)
        )
    return data


def _sample_row(sample: Dict[str, Any]) -> Dict[str, Any]:
    forecast = sample["forecast"]
    report = sample["faithfulness"]
    suff = sample["sufficiency"]
    market = sample["market"]
    coverage = sample["coverage"]
    drop = float(report["confidence_drop"])
    temporal_validity = float(report["temporal_validity"])
    label = sample.get("label", "")
    return {
        "sample_id": sample["sample_id"],
        "ticker": sample["ticker"],
        "forecast_time": sample["forecast_time"],
        "label": label,
        "prediction": forecast["prediction"],
        "confidence": float(forecast["confidence"]),
        "is_correct": bool(label != "" and label == forecast["prediction"]),
        "rationale": forecast["rationale"],
        "valid_news_count": len(sample["valid_news"]),
        "invalid_future_news_count": len(sample["invalid_future_news"]),
        "confidence_after_removal": float(report["confidence_after_removal"]),
        "prediction_after_removal": report["prediction_after_removal"],
        "confidence_drop": drop,
        "temporal_validity": temporal_validity,
        "evidence_support": float(report["evidence_support"]),
        "verdict": report["verdict"],
        "faithfulness_label": faithfulness_label(drop, temporal_validity),
        "counterevidence_coverage": float(coverage["counterevidence_coverage"]),
        "sufficiency_score": float(suff["sufficiency_score"]),
        "counterfactual_delta": float(suff["counterfactual_delta"]),
        "market_consistent": bool(market["market_consistent"]),
        "regime": market["regime"],
        "next_day_return": float(market["next_day_return"]),
        "price_5d_return": float(market["price_5d_return"]),
    }


def _evidence_rows(sample: Dict[str, Any]) -> List[Dict[str, Any]]:
    selection = sample["selection"]
    role_by_news: Dict[str, str] = {}
    for e in selection["pro_evidence"]:
        role_by_news[e["news_id"]] = "pro"
    for e in selection["counterevidence"]:
        role_by_news[e["news_id"]] = "counter"
    for e in selection["neutral_evidence"]:
        role_by_news.setdefault(e["news_id"], "neutral")
    cited = {
        e["news_id"]
        for e in selection["pro_evidence"] + selection["counterevidence"]
    }
    return [
        {
            "sample_id": sample["sample_id"],
            "ticker": sample["ticker"],
            "forecast_time": sample["forecast_time"],
            "news_id": ev["news_id"],
            "news_time": ev["news_time"],
            "evidence_text": ev.get("evidence_text", ""),
            "polarity": ev.get("polarity", "neutral"),
            "expected_direction": ev.get("expected_direction", "HOLD"),
            "evidence_role": role_by_news.get(ev["news_id"], "neutral"),
            "is_cited": ev["news_id"] in cited,
        }
        for ev in sample["evidence"]
    ]


def _leakage_rows(sample: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "sample_id": sample["sample_id"],
            "ticker": sample["ticker"],
            "forecast_time": sample["forecast_time"],
            "news_id": n["news_id"],
            "news_time": n["news_time"],
            "news_text": n.get("news_text", n.get("text", "")),
            "leakage_minutes": compute_leakage_minutes(
                str(n["news_time"]), sample["forecast_time"]
            ),
        }
        for n in sample["invalid_future_news"]
    ]


class DashboardData:
    """The three flattened views plus the raw samples (for Live Demo)."""

    def __init__(
        self,
        samples: pd.DataFrame,
        evidence: pd.DataFrame,
        leakage: pd.DataFrame,
        raw_samples: List[Dict[str, Any]],
    ) -> None:
        self.samples = samples
        self.evidence = evidence
        self.leakage = leakage
        self.raw_samples = raw_samples

    def raw_sample(self, sample_id: str) -> Dict[str, Any]:
        for sample in self.raw_samples:
            if sample["sample_id"] == sample_id:
                return sample
        raise KeyError(sample_id)


def load_dashboard_data(path: str = DEFAULT_ENVELOPE_PATH) -> DashboardData:
    """Envelope file → :class:`DashboardData`.

    Raises:
        DashboardDataError: missing file, bad JSON, or schema violation —
            the message tells the user how to (re)generate the envelope.
    """
    envelope = _load_envelope(path)
    raw = envelope["samples"]
    sample_rows = [_sample_row(s) for s in raw]
    evidence_rows = [row for s in raw for row in _evidence_rows(s)]
    leakage_rows = [row for s in raw for row in _leakage_rows(s)]
    leakage = pd.DataFrame(leakage_rows)
    if not leakage.empty:
        leakage = leakage.sort_values(
            "leakage_minutes", ascending=False
        ).reset_index(drop=True)
    return DashboardData(
        samples=pd.DataFrame(sample_rows),
        evidence=pd.DataFrame(evidence_rows),
        leakage=leakage,
        raw_samples=raw,
    )


__all__ = [
    "DEFAULT_ENVELOPE_PATH",
    "DashboardData",
    "DashboardDataError",
    "load_dashboard_data",
]