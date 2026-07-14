"""Tests for src.dashboard.data_loader (pure, no Streamlit)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.dashboard.data_loader import (
    DashboardData,
    DashboardDataError,
    load_dashboard_data,
)


def make_sample(
    sample_id: str = "AAPL_2025-03-12_0900",
    ticker: str = "AAPL",
    prediction: str = "UP",
    label: str = "UP",
    verdict: str = "strong_faithful_candidate",
    confidence_drop: float = 0.45,
    invalid_future_news: list | None = None,
) -> dict:
    """A minimal envelope sample that passes validate_sample(..., "export_csv")."""
    news = [{"news_id": "1", "news_time": "2025-03-11 08:00", "news_text": "growth"}]
    evidence = [
        {
            "evidence_id": "1_E001",
            "news_id": "1",
            "news_time": "2025-03-11 08:00",
            "evidence_text": "growth",
            "polarity": "positive",
            "expected_direction": "UP",
            "support_score": 1.0,
        }
    ]
    return {
        "sample_id": sample_id,
        "ticker": ticker,
        "forecast_time": "2025-03-12 09:00",
        "label": label,
        "next_day_return": 0.01,
        "price_5d_return": 0.03,
        "news": news,
        "valid_news": news,
        "invalid_future_news": invalid_future_news or [],
        "evidence": evidence,
        "forecast": {
            "prediction": prediction,
            "confidence": 0.7,
            "rationale": "Prediction UP because ...",
            "class_confidences": {"UP": 0.7, "DOWN": 0.15, "HOLD": 0.15},
        },
        "selection": {
            "pro_evidence": [{"news_id": "1"}],
            "counterevidence": [],
            "neutral_evidence": [],
        },
        "coverage": {
            "counterevidence_coverage": 1.0,
            "counterevidence_detected_rate": 1.0,
        },
        "faithfulness": {
            "temporal_validity": 1.0,
            "evidence_support": 1.0,
            "confidence_drop": confidence_drop,
            "confidence_after_removal": 0.7 - confidence_drop,
            "prediction_after_removal": "HOLD",
            "verdict": verdict,
        },
        "sufficiency": {"sufficiency_score": 0.9, "counterfactual_delta": 0.2},
        "market": {
            "market_consistent": True,
            "regime": "bull",
            "next_day_return": 0.01,
            "price_5d_return": 0.03,
        },
    }


def write_envelope(tmp_path: Path, samples: list) -> str:
    path = tmp_path / "08_market.json"
    path.write_text(
        json.dumps({"stage": "market_analyzer", "samples": samples}),
        encoding="utf-8",
    )
    return str(path)


def test_load_valid_envelope(tmp_path: Path) -> None:
    future = [{"news_id": "9", "news_time": "2025-03-13 10:00", "news_text": "late"}]
    path = write_envelope(
        tmp_path,
        [make_sample(), make_sample(sample_id="X2", ticker="GOOGL", invalid_future_news=future)],
    )
    data = load_dashboard_data(path)
    assert isinstance(data, DashboardData)
    assert len(data.samples) == 2
    assert len(data.evidence) == 2
    assert len(data.leakage) == 1
    row = data.samples.iloc[0]
    assert row["faithfulness_label"] == "HIGH"  # drop 0.45, tv 1.0
    assert bool(row["is_correct"]) is True
    assert data.leakage.iloc[0]["leakage_minutes"] > 0


def test_evidence_role_and_cited_flag(tmp_path: Path) -> None:
    path = write_envelope(tmp_path, [make_sample()])
    ev = load_dashboard_data(path).evidence.iloc[0]
    assert ev["evidence_role"] == "pro"
    assert bool(ev["is_cited"]) is True


def test_raw_sample_lookup(tmp_path: Path) -> None:
    path = write_envelope(tmp_path, [make_sample()])
    data = load_dashboard_data(path)
    assert data.raw_sample("AAPL_2025-03-12_0900")["ticker"] == "AAPL"
    with pytest.raises(KeyError):
        data.raw_sample("nope")


def test_missing_file_raises_with_hint(tmp_path: Path) -> None:
    with pytest.raises(DashboardDataError, match="src.runner"):
        load_dashboard_data(str(tmp_path / "nope.json"))


def test_bad_json_raises(tmp_path: Path) -> None:
    p = tmp_path / "08_market.json"
    p.write_text("{broken", encoding="utf-8")
    with pytest.raises(DashboardDataError, match="JSON"):
        load_dashboard_data(str(p))


def test_schema_violation_raises(tmp_path: Path) -> None:
    bad = make_sample()
    del bad["faithfulness"]
    path = write_envelope(tmp_path, [bad])
    with pytest.raises(DashboardDataError, match="faithfulness"):
        load_dashboard_data(path)


def test_leakage_sorted_descending(tmp_path: Path) -> None:
    future = [
        {"news_id": "8", "news_time": "2025-03-12 10:00", "news_text": "a"},
        {"news_id": "9", "news_time": "2025-03-14 09:00", "news_text": "b"},
    ]
    path = write_envelope(tmp_path, [make_sample(invalid_future_news=future)])
    leakage = load_dashboard_data(path).leakage
    minutes = leakage["leakage_minutes"].tolist()
    assert minutes == sorted(minutes, reverse=True)