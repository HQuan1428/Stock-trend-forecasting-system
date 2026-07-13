"""Tests for src.dashboard.metrics (pure aggregations)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.dashboard import metrics


@pytest.fixture()
def samples() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sample_id": "S1", "ticker": "AAPL", "forecast_time": "t1",
                "label": "UP", "prediction": "UP", "is_correct": True,
                "confidence": 0.7, "confidence_drop": 0.45,
                "temporal_validity": 1.0, "evidence_support": 1.0,
                "faithfulness_label": "HIGH", "verdict": "strong_faithful_candidate",
                "sufficiency_score": 0.9, "counterfactual_delta": 0.2,
                "counterevidence_coverage": 1.0,
                "market_consistent": True, "regime": "bull",
            },
            {
                "sample_id": "S2", "ticker": "AAPL", "forecast_time": "t2",
                "label": "DOWN", "prediction": "HOLD", "is_correct": False,
                "confidence": 0.5, "confidence_drop": 0.0,
                "temporal_validity": 1.0, "evidence_support": 0.5,
                "faithfulness_label": "LOW", "verdict": "decorative_explanation_risk",
                "sufficiency_score": 0.5, "counterfactual_delta": 0.0,
                "counterevidence_coverage": 0.0,
                "market_consistent": False, "regime": "sideways",
            },
            {
                "sample_id": "S3", "ticker": "GOOGL", "forecast_time": "t1",
                "label": "", "prediction": "DOWN", "is_correct": False,
                "confidence": 0.6, "confidence_drop": 0.15,
                "temporal_validity": 1.0, "evidence_support": 1.0,
                "faithfulness_label": "MEDIUM", "verdict": "moderate_faithful_candidate",
                "sufficiency_score": 0.7, "counterfactual_delta": 0.1,
                "counterevidence_coverage": 0.5,
                "market_consistent": True, "regime": "bear",
            },
        ]
    )


def test_prediction_distribution(samples: pd.DataFrame) -> None:
    assert metrics.prediction_distribution(samples) == {"UP": 1, "DOWN": 1, "HOLD": 1}


def test_accuracy_ignores_unlabeled(samples: pd.DataFrame) -> None:
    # only S1, S2 labeled; S1 correct
    assert metrics.accuracy(samples) == pytest.approx(0.5)


def test_accuracy_by_ticker(samples: pd.DataFrame) -> None:
    table = metrics.accuracy_by_ticker(samples)
    assert table["ticker"].tolist() == ["AAPL"]  # GOOGL has no label
    assert table.iloc[0]["accuracy"] == pytest.approx(0.5)


def test_normalized_drop_clamps() -> None:
    assert metrics.normalized_drop(-0.1) == 0.0
    assert metrics.normalized_drop(0.15) == pytest.approx(0.5)
    assert metrics.normalized_drop(0.9) == 1.0


def test_radar_values_in_unit_range(samples: pd.DataFrame) -> None:
    values = metrics.radar_values(samples)
    assert len(values) == len(metrics.RADAR_AXES)
    assert all(0.0 <= v <= 1.0 for v in values)


def test_radar_values_empty() -> None:
    assert metrics.radar_values(pd.DataFrame()) == [0.0] * len(metrics.RADAR_AXES)


def test_verdict_banner_kinds() -> None:
    assert metrics.verdict_banner("strong_faithful_candidate")[0] == "success"
    assert metrics.verdict_banner("decorative_explanation_risk")[0] == "warning"
    assert metrics.verdict_banner("invalid_temporal_leakage")[0] == "error"
    assert metrics.verdict_banner("unsupported_evidence")[0] == "error"
    kind, msg = metrics.verdict_banner("???")
    assert kind == "warning" and "???" in msg


def test_leakage_severity_levels() -> None:
    assert metrics.leakage_severity(0)[0] == "success"
    assert metrics.leakage_severity(3)[0] == "warning"
    assert metrics.leakage_severity(21)[0] == "error"


def test_faithfulness_label_distribution(samples: pd.DataFrame) -> None:
    assert metrics.faithfulness_label_distribution(samples) == {
        "HIGH": 1, "MEDIUM": 1, "LOW": 1,
    }


def test_market_summary(samples: pd.DataFrame) -> None:
    summary = metrics.market_summary(samples)
    assert summary["consistency_rate"] == pytest.approx(2 / 3)
    assert summary["regimes"] == {"bear": 1, "bull": 1, "sideways": 1}


def test_coverage_and_sufficiency_summaries(samples: pd.DataFrame) -> None:
    cov = metrics.coverage_summary(samples)
    assert cov["avg_coverage"] == pytest.approx(0.5)
    assert cov["detected_rate"] == pytest.approx(2 / 3)
    suff = metrics.sufficiency_summary(samples)
    assert suff["avg_sufficiency"] == pytest.approx((0.9 + 0.5 + 0.7) / 3)


def test_sample_choices_and_find(samples: pd.DataFrame) -> None:
    assert metrics.sample_choices(samples, "AAPL") == ["t1", "t2"]
    assert metrics.find_sample_id(samples, "GOOGL", "t1") == "S3"
    with pytest.raises(KeyError):
        metrics.find_sample_id(samples, "TSLA", "t1")