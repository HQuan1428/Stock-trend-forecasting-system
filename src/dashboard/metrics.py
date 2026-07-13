"""Pure aggregation functions for the dashboard.

Every function takes the DataFrames from ``data_loader`` (or plain
values) and returns plain data — no Streamlit, no I/O. The
HIGH/MEDIUM/LOW thresholds live in ``src.export_csv.faithfulness_label``
(already applied by the data loader); this module never redefines them.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pandas as pd

# Normalization ceiling for confidence_drop on the radar — same constant
# FaithfulnessMetrics uses for the composite score.
DROP_NORMALIZATION_CEILING = 0.30

RADAR_AXES = (
    "Temporal Validity",
    "Evidence Support",
    "Confidence Drop (chuẩn hóa)",
    "Sufficiency (B1)",
    "Counterevidence Coverage (B2)",
)

# verdict → (banner_kind, Vietnamese message). banner_kind maps to the
# Streamlit call used by the render layer: success/warning/error.
VERDICT_BANNERS: Dict[str, Tuple[str, str]] = {
    "strong_faithful_candidate": (
        "success",
        "Evidence có dấu hiệu FAITHFUL (mạnh) — bỏ evidence cited làm prediction "
        "đổi hướng hoặc confidence giảm ≥ 0.20.",
    ),
    "moderate_faithful_candidate": (
        "success",
        "Evidence có dấu hiệu FAITHFUL (trung bình) — confidence giảm ≥ 0.10 khi "
        "bỏ evidence cited.",
    ),
    "weak_faithful_candidate": (
        "success",
        "Evidence có dấu hiệu FAITHFUL (yếu) — confidence giảm ≥ 0.05 khi bỏ "
        "evidence cited.",
    ),
    "decorative_explanation_risk": (
        "warning",
        "Evidence có thể chỉ là GIẢI THÍCH TRANG TRÍ — bỏ evidence cited mà "
        "prediction và confidence gần như không đổi.",
    ),
    "invalid_temporal_leakage": (
        "error",
        "VI PHẠM TEMPORAL VALIDITY — có evidence cited xuất hiện sau thời điểm "
        "dự báo; kết quả không đáng tin.",
    ),
    "unsupported_evidence": (
        "error",
        "EVIDENCE KHÔNG ỦNG HỘ PREDICTION — hướng của evidence cited ngược với "
        "dự báo.",
    ),
}


def verdict_banner(verdict: str) -> Tuple[str, str]:
    """Map an internal verdict to (banner_kind, Vietnamese message)."""
    return VERDICT_BANNERS.get(
        verdict,
        ("warning", f"Verdict không xác định: {verdict}"),
    )


def prediction_distribution(samples: pd.DataFrame) -> Dict[str, int]:
    """UP/DOWN/HOLD counts (all three keys always present)."""
    counts = samples["prediction"].value_counts().to_dict()
    return {k: int(counts.get(k, 0)) for k in ("UP", "DOWN", "HOLD")}


def accuracy(samples: pd.DataFrame) -> float:
    """Share of labeled samples where prediction == label (0.0 if none)."""
    labeled = samples[samples["label"] != ""]
    if labeled.empty:
        return 0.0
    return float(labeled["is_correct"].mean())


def accuracy_by_ticker(samples: pd.DataFrame) -> pd.DataFrame:
    """Per-ticker accuracy table (ticker, n_samples, accuracy)."""
    labeled = samples[samples["label"] != ""]
    if labeled.empty:
        return pd.DataFrame(columns=["ticker", "n_samples", "accuracy"])
    grouped = (
        labeled.groupby("ticker")
        .agg(n_samples=("is_correct", "size"), accuracy=("is_correct", "mean"))
        .reset_index()
    )
    return grouped.sort_values("ticker").reset_index(drop=True)


def average_confidence(samples: pd.DataFrame) -> float:
    return float(samples["confidence"].mean()) if not samples.empty else 0.0


def average_confidence_drop(samples: pd.DataFrame) -> float:
    return float(samples["confidence_drop"].mean()) if not samples.empty else 0.0


def normalized_drop(drop: float) -> float:
    """Clamp a signed drop into [0, 1] against the 0.30 ceiling."""
    return min(max(float(drop), 0.0) / DROP_NORMALIZATION_CEILING, 1.0)


def radar_values(samples: pd.DataFrame) -> List[float]:
    """Dataset averages for the five radar axes (all in [0, 1])."""
    if samples.empty:
        return [0.0] * len(RADAR_AXES)
    return [
        float(samples["temporal_validity"].mean()),
        float(samples["evidence_support"].mean()),
        float(samples["confidence_drop"].map(normalized_drop).mean()),
        float(samples["sufficiency_score"].mean()),
        float(samples["counterevidence_coverage"].mean()),
    ]


def leakage_severity(leakage_count: int) -> Tuple[str, str]:
    """(banner_kind, Vietnamese message) for the leakage tab banner."""
    if leakage_count == 0:
        return "success", "OK — không phát hiện tin tương lai nào trong dataset."
    if leakage_count <= 5:
        return (
            "warning",
            f"Warning — {leakage_count} tin tương lai đã bị Temporal Retriever "
            "chặn khỏi input dự báo.",
        )
    return (
        "error",
        f"Critical — {leakage_count} tin tương lai bị chặn. Kiểm tra lại nguồn "
        "dữ liệu đầu vào.",
    )


def faithfulness_label_distribution(samples: pd.DataFrame) -> Dict[str, int]:
    counts = samples["faithfulness_label"].value_counts().to_dict()
    return {k: int(counts.get(k, 0)) for k in ("HIGH", "MEDIUM", "LOW")}


def market_summary(samples: pd.DataFrame) -> Dict[str, Any]:
    """B3 aggregates: consistency rate + regime counts."""
    if samples.empty:
        return {"consistency_rate": 0.0, "regimes": {}}
    regimes = samples["regime"].value_counts().to_dict()
    return {
        "consistency_rate": float(samples["market_consistent"].mean()),
        "regimes": {k: int(v) for k, v in sorted(regimes.items())},
    }


def coverage_summary(samples: pd.DataFrame) -> Dict[str, float]:
    """B2 aggregates: average coverage + share of samples with any counterevidence detected."""
    if samples.empty:
        return {"avg_coverage": 0.0, "detected_rate": 0.0}
    return {
        "avg_coverage": float(samples["counterevidence_coverage"].mean()),
        "detected_rate": float((samples["counterevidence_coverage"] > 0).mean()),
    }


def sufficiency_summary(samples: pd.DataFrame) -> Dict[str, float]:
    """B1 aggregates."""
    if samples.empty:
        return {"avg_sufficiency": 0.0, "avg_counterfactual_delta": 0.0}
    return {
        "avg_sufficiency": float(samples["sufficiency_score"].mean()),
        "avg_counterfactual_delta": float(samples["counterfactual_delta"].mean()),
    }


def sample_choices(samples: pd.DataFrame, ticker: str) -> List[str]:
    """Forecast times available for a ticker (input order preserved)."""
    return samples[samples["ticker"] == ticker]["forecast_time"].tolist()


def find_sample_id(samples: pd.DataFrame, ticker: str, forecast_time: str) -> str:
    """The sample_id for a (ticker, forecast_time) pick in the Live Demo."""
    match = samples[
        (samples["ticker"] == ticker) & (samples["forecast_time"] == forecast_time)
    ]
    if match.empty:
        raise KeyError(f"no sample for ({ticker}, {forecast_time})")
    return str(match.iloc[0]["sample_id"])


__all__ = [
    "DROP_NORMALIZATION_CEILING",
    "RADAR_AXES",
    "VERDICT_BANNERS",
    "accuracy",
    "accuracy_by_ticker",
    "average_confidence",
    "average_confidence_drop",
    "coverage_summary",
    "faithfulness_label_distribution",
    "find_sample_id",
    "leakage_severity",
    "market_summary",
    "normalized_drop",
    "prediction_distribution",
    "radar_values",
    "sample_choices",
    "sufficiency_summary",
    "verdict_banner",
]