"""Unit tests for the Faithfulness Metrics (pure functions)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.faithfulness_metrics import VERDICTS, FaithfulnessMetrics
from src.faithfulness_evaluator import FaithfulnessEvaluator

calculate_confidence_drop = FaithfulnessMetrics.calculate_confidence_drop
calculate_dataset_temporal_validity = FaithfulnessMetrics.calculate_dataset_temporal_validity
calculate_evidence_support = FaithfulnessMetrics.calculate_evidence_support
calculate_faithfulness_score = FaithfulnessMetrics.calculate_faithfulness_score
calculate_prediction_temporal_validity = FaithfulnessMetrics.calculate_prediction_temporal_validity
classify_faithfulness = FaithfulnessMetrics.classify_faithfulness
confidence_after_removal_for_original_class = (
    FaithfulnessMetrics.confidence_after_removal_for_original_class
)
evidence_support_score = FaithfulnessMetrics.evidence_support_score
CSV_COLUMNS = FaithfulnessEvaluator.CSV_COLUMNS
CSV_DEFAULT_PATH = FaithfulnessEvaluator.CSV_DEFAULT_PATH
JSON_DEFAULT_PATH = FaithfulnessEvaluator.JSON_DEFAULT_PATH


FORECAST_TIME = "2025-03-12 09:00"


def _evidence(eid: str, direction: str, news_time: str = "2025-03-11 08:30", **extra):
    item = {
        "evidence_id": eid,
        "news_id": f"N-{eid}",
        "news_time": news_time,
        "evidence_text": "...",
        "polarity": "positive",
        "expected_direction": direction,
    }
    item.update(extra)
    return item


# ---------------------------------------------------------------------------
# Temporal validity
# ---------------------------------------------------------------------------


def test_temporal_validity_all_valid_is_one() -> None:
    cited = [
        _evidence("E1", "UP"),
        _evidence("E2", "DOWN"),
        _evidence("E3", "UP"),
    ]
    assert calculate_prediction_temporal_validity(cited, FORECAST_TIME) == 1.0


def test_temporal_validity_one_future_is_zero() -> None:
    cited = [
        _evidence("E1", "UP", news_time="2025-03-11 08:30"),
        _evidence("E2", "UP", news_time="2025-03-13 09:00"),  # future
    ]
    assert calculate_prediction_temporal_validity(cited, FORECAST_TIME) == 0.0


def test_temporal_validity_empty_cited_is_one() -> None:
    assert calculate_prediction_temporal_validity([], FORECAST_TIME) == 1.0


def test_temporal_validity_equal_timestamp_is_valid() -> None:
    cited = [_evidence("E1", "UP", news_time=FORECAST_TIME)]
    assert calculate_prediction_temporal_validity(cited, FORECAST_TIME) == 1.0


def test_dataset_temporal_validity_empty_is_one() -> None:
    assert calculate_dataset_temporal_validity([]) == 1.0


def test_dataset_temporal_validity_two_of_three() -> None:
    records = [
        {"news_time": "2025-03-11 08:30", "forecast_time": FORECAST_TIME},
        {"news_time": "2025-03-11 09:00", "forecast_time": FORECAST_TIME},
        {"news_time": "2025-03-13 09:00", "forecast_time": FORECAST_TIME},
    ]
    assert calculate_dataset_temporal_validity(records) == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------
# Evidence support
# ---------------------------------------------------------------------------


def test_evidence_support_exact_match_DOWN_DOWN() -> None:
    assert evidence_support_score("DOWN", "DOWN") == 1.0


def test_evidence_support_exact_match_UP_DOWN() -> None:
    assert evidence_support_score("UP", "DOWN") == 0.0


def test_evidence_support_hold_partial_UP_HOLD() -> None:
    assert evidence_support_score("UP", "HOLD") == 0.5


def test_evidence_support_hold_partial_HOLD_UP() -> None:
    assert evidence_support_score("HOLD", "UP") == 0.5


def test_evidence_support_hold_partial_DOWN_HOLD() -> None:
    assert evidence_support_score("DOWN", "HOLD") == 0.5


def test_evidence_support_hold_match() -> None:
    assert evidence_support_score("HOLD", "HOLD") == 1.0


def test_evidence_support_unknown_treated_as_hold() -> None:
    # Unknown expected_direction is treated as HOLD → 0.5 vs UP/DOWN
    assert evidence_support_score("UP", "WEIRD") == 0.5


def test_calculate_evidence_support_empty_is_one() -> None:
    assert calculate_evidence_support("UP", []) == 1.0


def test_calculate_evidence_support_three_item_average() -> None:
    cited = [
        _evidence("E1", "UP"),
        _evidence("E2", "DOWN"),
        _evidence("E3", "HOLD"),
    ]
    assert calculate_evidence_support("UP", cited) == pytest.approx((1.0 + 0.0 + 0.5) / 3.0)


# ---------------------------------------------------------------------------
# Confidence drop
# ---------------------------------------------------------------------------


def test_confidence_drop_large_positive() -> None:
    drop = calculate_confidence_drop(
        original_confidence=0.80,
        original_prediction="DOWN",
        reduced_prediction="DOWN",
        reduced_confidence=0.55,
    )
    assert drop == pytest.approx(0.25)


def test_confidence_drop_near_zero() -> None:
    drop = calculate_confidence_drop(
        original_confidence=0.80,
        original_prediction="UP",
        reduced_prediction="UP",
        reduced_confidence=0.79,
    )
    assert drop == pytest.approx(0.01)


def test_confidence_drop_negative() -> None:
    drop = calculate_confidence_drop(
        original_confidence=0.55,
        original_prediction="UP",
        reduced_prediction="UP",
        reduced_confidence=0.80,
    )
    assert drop == pytest.approx(-0.25)


def test_confidence_drop_prediction_flips_with_class_confidences() -> None:
    drop = calculate_confidence_drop(
        original_confidence=0.80,
        original_prediction="DOWN",
        reduced_prediction="UP",
        reduced_confidence=0.0,
        reduced_class_confidences={"UP": 0.42, "DOWN": 0.50, "HOLD": 0.08},
    )
    assert drop == pytest.approx(0.30)


def test_confidence_drop_prediction_flips_without_class_confidences() -> None:
    drop = calculate_confidence_drop(
        original_confidence=0.80,
        original_prediction="DOWN",
        reduced_prediction="UP",
        reduced_confidence=0.42,
    )
    assert drop == pytest.approx(0.80)


def test_confidence_after_removal_prefers_class_confidences() -> None:
    after = confidence_after_removal_for_original_class(
        original_prediction="DOWN",
        reduced_prediction="UP",
        reduced_confidence=0.0,
        reduced_class_confidences={"UP": 0.42, "DOWN": 0.50, "HOLD": 0.08},
    )
    assert after == pytest.approx(0.50)


def test_confidence_after_removal_same_prediction_fallback() -> None:
    after = confidence_after_removal_for_original_class(
        original_prediction="UP",
        reduced_prediction="UP",
        reduced_confidence=0.55,
    )
    assert after == pytest.approx(0.55)


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------


def test_faithfulness_score_known_weights_full() -> None:
    assert calculate_faithfulness_score(1.0, 1.0, 0.30) == pytest.approx(1.0)


def test_faithfulness_score_known_weights_zero_drop() -> None:
    assert calculate_faithfulness_score(1.0, 1.0, 0.0) == pytest.approx(0.65)


def test_faithfulness_score_clamps_negative_drop() -> None:
    # Negative drop contributes 0 to the composite; tv=1, es=1, drop=0 → 0.65
    score = calculate_faithfulness_score(1.0, 1.0, -0.10)
    assert score == pytest.approx(0.65)


def test_faithfulness_score_saturates_at_drop_030() -> None:
    assert calculate_faithfulness_score(1.0, 1.0, 0.30) == pytest.approx(1.0)
    assert calculate_faithfulness_score(1.0, 1.0, 1.00) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------


def test_verdict_temporal_leakage_branch() -> None:
    assert (
        classify_faithfulness(0.0, 1.0, 0.30, "UP", "UP")
        == "invalid_temporal_leakage"
    )


def test_verdict_unsupported_branch() -> None:
    assert (
        classify_faithfulness(1.0, 0.0, 0.30, "UP", "UP")
        == "unsupported_evidence"
    )


def test_verdict_strong_via_flip() -> None:
    assert (
        classify_faithfulness(1.0, 1.0, 0.0, "UP", "DOWN")
        == "strong_faithful_candidate"
    )


def test_verdict_strong_via_drop() -> None:
    assert (
        classify_faithfulness(1.0, 1.0, 0.20, "UP", "UP")
        == "strong_faithful_candidate"
    )


def test_verdict_moderate() -> None:
    assert (
        classify_faithfulness(1.0, 1.0, 0.10, "UP", "UP")
        == "moderate_faithful_candidate"
    )


def test_verdict_weak() -> None:
    assert (
        classify_faithfulness(1.0, 1.0, 0.05, "UP", "UP")
        == "weak_faithful_candidate"
    )


def test_verdict_decorative() -> None:
    assert (
        classify_faithfulness(1.0, 1.0, 0.01, "UP", "UP")
        == "decorative_explanation_risk"
    )


def test_verdict_clamps_out_of_range_inputs() -> None:
    # negative temporal_validity → invalid_temporal_leakage
    assert (
        classify_faithfulness(-0.1, 1.0, 0.30, "UP", "UP")
        == "invalid_temporal_leakage"
    )
    # evidence_support > 1 → still passes; drop 0 → decorative
    assert (
        classify_faithfulness(1.0, 1.5, 0.0, "UP", "UP")
        == "decorative_explanation_risk"
    )


def test_verdict_set_has_six_labels() -> None:
    assert len(VERDICTS) == 6
    assert "invalid_temporal_leakage" in VERDICTS
    assert "unsupported_evidence" in VERDICTS
    assert "strong_faithful_candidate" in VERDICTS
    assert "moderate_faithful_candidate" in VERDICTS
    assert "weak_faithful_candidate" in VERDICTS
    assert "decorative_explanation_risk" in VERDICTS


# ---------------------------------------------------------------------------
# Constant sanity
# ---------------------------------------------------------------------------


def test_csv_columns_match_spec() -> None:
    assert CSV_COLUMNS == (
        "ticker",
        "forecast_time",
        "prediction",
        "original_confidence",
        "prediction_after_removal",
        "confidence_after_removal",
        "confidence_drop",
        "temporal_validity",
        "evidence_support",
        "faithfulness_score",
        "verdict",
        "warnings",
    )


def test_default_paths_are_outputs() -> None:
    assert CSV_DEFAULT_PATH == "outputs/faithfulness_results.csv"
    assert JSON_DEFAULT_PATH == "outputs/faithfulness_results.json"