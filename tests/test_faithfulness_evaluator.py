"""Unit and integration tests for the Faithfulness Evaluator."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src.stages.faithfulness_evaluator import FaithfulnessEvaluator, FaithfulnessEvaluatorError
from src.stages.forecast_model import ForecastModel

ABLATION_STRATEGIES = FaithfulnessEvaluator.ABLATION_STRATEGIES
CSV_COLUMNS = FaithfulnessEvaluator.CSV_COLUMNS
CSV_DEFAULT_PATH = FaithfulnessEvaluator.CSV_DEFAULT_PATH
JSON_DEFAULT_PATH = FaithfulnessEvaluator.JSON_DEFAULT_PATH
evaluate_batch = FaithfulnessEvaluator().evaluate_batch
predict = ForecastModel().predict


def _evidence(eid: str, direction: str, news_time: str) -> dict:
    return {
        "evidence_id": eid,
        "news_id": f"N-{eid}",
        "news_time": news_time,
        "evidence_text": "...",
        "polarity": "positive" if direction == "UP" else "negative" if direction == "DOWN" else "neutral",
        "expected_direction": direction,
        "support_score": 1.0,
    }


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


def test_ablation_strategies_default_first() -> None:
    assert ABLATION_STRATEGIES[0] == "remove_cited_pro_evidence"
    assert "remove_all_cited_evidence" in ABLATION_STRATEGIES


# ---------------------------------------------------------------------------
# Class validation
# ---------------------------------------------------------------------------


def test_evaluate_raises_on_non_dict_input() -> None:
    with pytest.raises(FaithfulnessEvaluatorError):
        FaithfulnessEvaluator().evaluate("not a dict", {})


def test_evaluate_raises_on_non_dict_result() -> None:
    with pytest.raises(FaithfulnessEvaluatorError):
        FaithfulnessEvaluator().evaluate({}, "not a dict")


def test_evaluate_raises_on_invalid_strategy() -> None:
    with pytest.raises(FaithfulnessEvaluatorError):
        FaithfulnessEvaluator().evaluate({}, {}, ablation_strategy="bogus")


def test_evaluate_raises_on_missing_prediction() -> None:
    inp = {"sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00", "evidence": []}
    result = {"confidence": 0.5}
    with pytest.raises(FaithfulnessEvaluatorError):
        FaithfulnessEvaluator().evaluate(inp, result)


def test_evaluate_raises_on_non_numeric_confidence() -> None:
    inp = {"sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00", "evidence": []}
    result = {"prediction": "UP", "confidence": "high"}
    with pytest.raises(FaithfulnessEvaluatorError):
        FaithfulnessEvaluator().evaluate(inp, result)


def test_evaluate_raises_on_missing_forecast_time() -> None:
    inp: dict = {"sample_id": "X", "ticker": "AAPL", "evidence": []}
    result = {"prediction": "UP", "confidence": 0.5}
    with pytest.raises(FaithfulnessEvaluatorError):
        FaithfulnessEvaluator().evaluate(inp, result)


# ---------------------------------------------------------------------------
# Happy-path with all four archetypes
# ---------------------------------------------------------------------------


def _strong_faithful_pair() -> tuple[dict, dict]:
    inp = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "evidence": [
            _evidence("E1", "UP", "2025-03-11 08:00"),
            _evidence("E2", "UP", "2025-03-11 09:00"),
        ],
    }
    return inp, predict(inp)


def _decorative_pair() -> tuple[dict, dict]:
    inp = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "evidence": [],
    }
    result = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "prediction": "UP", "confidence": 0.6,
        "pro_evidence": [], "counter_evidence": [],
        "warnings": [], "model_version": "rule_based_v1",
    }
    return inp, result


def _temporal_leakage_pair() -> tuple[dict, dict]:
    future = _evidence("E_LATE", "UP", "2025-03-13 09:00")
    inp = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "evidence": [_evidence("E1", "UP", "2025-03-11 08:00"), future],
    }
    result = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "prediction": "UP", "confidence": 0.8,
        "pro_evidence": [_evidence("E1", "UP", "2025-03-11 08:00"), future],
        "counter_evidence": [], "warnings": [], "model_version": "rule_based_v1",
    }
    return inp, result


def _unsupported_pair() -> tuple[dict, dict]:
    inp = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "evidence": [_evidence("E1", "DOWN", "2025-03-11 08:00")],
    }
    result = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "prediction": "UP", "confidence": 0.6,
        "pro_evidence": [_evidence("E1", "DOWN", "2025-03-11 08:00")],
        "counter_evidence": [], "warnings": [], "model_version": "rule_based_v1",
    }
    return inp, result


_ARCHETYPE_PAIRS = {
    "strong_faithful": _strong_faithful_pair,
    "decorative": _decorative_pair,
    "temporal_leakage": _temporal_leakage_pair,
    "unsupported": _unsupported_pair,
}


@pytest.mark.parametrize(
    "name,expected_verdict",
    [
        ("strong_faithful", "strong_faithful_candidate"),
        ("decorative", "decorative_explanation_risk"),
        ("temporal_leakage", "invalid_temporal_leakage"),
        ("unsupported", "unsupported_evidence"),
    ],
)
def test_archetype_pairs_produce_expected_verdict(name: str, expected_verdict: str) -> None:
    inp, result = _ARCHETYPE_PAIRS[name]()
    report = FaithfulnessEvaluator().evaluate(inp, result)
    assert report["verdict"] == expected_verdict


# ---------------------------------------------------------------------------
# Acceptance scenarios from the spec
# ---------------------------------------------------------------------------


def test_scenario_temporal_validity_pass() -> None:
    inp = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "evidence": [
            _evidence("E1", "UP", "2025-03-11 08:00"),
            _evidence("E2", "UP", "2025-03-11 09:00"),
        ],
    }
    result = predict(inp)
    report = FaithfulnessEvaluator().evaluate(inp, result)
    assert report["temporal_validity"] == 1.0
    assert report["temporal_warnings"] == []


def test_scenario_temporal_leakage_detected() -> None:
    future = _evidence("E_LATE", "UP", "2025-03-13 09:00")
    inp = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "evidence": [
            _evidence("E1", "UP", "2025-03-11 08:00"),
            future,
        ],
    }
    result = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "prediction": "UP", "confidence": 0.8,
        "pro_evidence": [_evidence("E1", "UP", "2025-03-11 08:00"), future],
        "counter_evidence": [], "warnings": [], "model_version": "rule_based_v1",
    }
    report = FaithfulnessEvaluator().evaluate(inp, result)
    assert report["temporal_validity"] == 0.0
    assert report["verdict"] == "invalid_temporal_leakage"
    assert any("E_LATE" in w for w in report["temporal_warnings"])


def test_scenario_evidence_support_exact_match() -> None:
    inp = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "evidence": [_evidence("E1", "DOWN", "2025-03-11 08:00")],
    }
    result = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "prediction": "DOWN", "confidence": 0.6,
        "pro_evidence": [_evidence("E1", "DOWN", "2025-03-11 08:00")],
        "counter_evidence": [], "warnings": [], "model_version": "rule_based_v1",
    }
    report = FaithfulnessEvaluator().evaluate(inp, result)
    assert report["evidence_support"] == 1.0


def test_scenario_evidence_support_mismatch() -> None:
    inp = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "evidence": [_evidence("E1", "DOWN", "2025-03-11 08:00")],
    }
    result = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "prediction": "UP", "confidence": 0.6,
        "pro_evidence": [_evidence("E1", "DOWN", "2025-03-11 08:00")],
        "counter_evidence": [], "warnings": [], "model_version": "rule_based_v1",
    }
    report = FaithfulnessEvaluator().evaluate(inp, result)
    assert report["evidence_support"] == 0.0
    assert report["verdict"] == "unsupported_evidence"


def test_scenario_evidence_support_hold_partial() -> None:
    inp = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "evidence": [_evidence("E1", "HOLD", "2025-03-11 08:00")],
    }
    result = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "prediction": "UP", "confidence": 0.6,
        "pro_evidence": [_evidence("E1", "HOLD", "2025-03-11 08:00")],
        "counter_evidence": [], "warnings": [], "model_version": "rule_based_v1",
    }
    report = FaithfulnessEvaluator().evaluate(inp, result)
    assert report["evidence_support"] == 0.5


def test_scenario_empty_cited_handled_safely() -> None:
    inp = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "evidence": [],
    }
    result = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "prediction": "UP", "confidence": 0.6,
        "pro_evidence": [], "counter_evidence": [],
        "warnings": [], "model_version": "rule_based_v1",
    }
    report = FaithfulnessEvaluator().evaluate(inp, result)
    assert report["verdict"] == "decorative_explanation_risk"
    assert report["per_evidence_results"] == []


def test_scenario_confidence_drop_negative_adds_warning() -> None:
    inp = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "evidence": [
            _evidence("E1", "UP", "2025-03-11 08:00"),
            _evidence("E2", "UP", "2025-03-11 09:00"),
        ],
    }
    result = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "prediction": "UP", "confidence": 0.6,
        "pro_evidence": [_evidence("E1", "UP", "2025-03-11 08:00")],
        "counter_evidence": [], "warnings": [], "model_version": "rule_based_v1",
    }
    # The reduced result is hand-built to force a negative drop.
    # We need a way to make the ablated prediction more confident; the
    # easiest way is to have the pro_evidence contain only the
    # counter-evidence, so removal actually flips the prediction.
    # Hand-build a result whose ablation reduces to UP with 0.7
    # confidence.
    result2 = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "prediction": "UP", "confidence": 0.6,
        "pro_evidence": [_evidence("E1", "DOWN", "2025-03-11 08:00")],
        "counter_evidence": [], "warnings": [], "model_version": "rule_based_v1",
    }
    # Remove the DOWN pro_evidence → 1 UP left → UP/0.6 → drop 0.0
    # (no negative). To produce a negative drop, the pro_evidence must
    # be items whose removal INCREASES confidence. Easiest: hand-build
    # a result whose pro_evidence contains a single neutral item
    # (HOLD); ablation removes it → prediction still UP, but the
    # remaining confidence is 0.5 vs original 0.6. Hmm, that gives
    # drop = 0.1. We need a different path: the spec example is
    # original 0.55 → reduced 0.80.
    # Use a contrived result: pro_evidence contains a HOLD item
    # that drags confidence down.
    result3 = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "prediction": "UP", "confidence": 0.55,
        "pro_evidence": [_evidence("E1", "HOLD", "2025-03-11 08:00")],
        "counter_evidence": [], "warnings": [], "model_version": "rule_based_v1",
    }
    inp3 = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "evidence": [
            _evidence("E1", "HOLD", "2025-03-11 08:00"),
            _evidence("E2", "UP", "2025-03-11 09:00"),
            _evidence("E3", "UP", "2025-03-11 10:00"),
        ],
    }
    report = FaithfulnessEvaluator().evaluate(inp3, result3)
    # Original: 2 UP, 1 HOLD → score 2 → confidence 0.7
    # The Forecast Model's actual prediction is UP/0.7, but we
    # hand-built result3 with confidence 0.55 to drive a negative drop.
    # After removing E1 (HOLD) from pro_evidence: the ablated input
    # has 2 UP, 0 HOLD → score 2 → confidence 0.7.
    # confidence_drop = 0.55 - 0.7 = -0.15
    assert report["confidence_drop"] < 0
    assert "confidence_increased_after_removal" in report["ablation_warnings"]


# ---------------------------------------------------------------------------
# evaluate_batch
# ---------------------------------------------------------------------------


def test_evaluate_batch_writes_csv_with_required_columns(tmp_path: Path) -> None:
    inp1, result1 = _strong_faithful_pair()
    inp2, result2 = _decorative_pair()
    csv_path = tmp_path / "out.csv"
    evaluate_batch(
        [(inp1, result1), (inp2, result2)],
        output_csv_path=str(csv_path),
    )
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = list(reader)
    assert header == list(CSV_COLUMNS)
    assert len(rows) == 2


def test_evaluate_batch_writes_json_sibling(tmp_path: Path) -> None:
    inp1, result1 = _strong_faithful_pair()
    json_path = tmp_path / "out.json"
    evaluate_batch(
        [(inp1, result1)],
        output_json_path=str(json_path),
    )
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert "per_evidence_results" in data[0]


def test_evaluate_batch_swallows_per_record_error(tmp_path: Path) -> None:
    inp1, result1 = _strong_faithful_pair()
    csv_path = tmp_path / "out.csv"
    bad = ("not a tuple",)  # type: ignore[list-item]
    result = evaluate_batch(
        [(inp1, result1), bad],
        output_csv_path=str(csv_path),
    )
    assert len(result) == 2
    assert result[0]["verdict"] == "strong_faithful_candidate"
    assert result[1]["verdict"] == "unsupported_evidence"
    assert any(
        w.startswith("EVALUATION_ERROR: ") for w in result[1]["ablation_warnings"]
    )


# ---------------------------------------------------------------------------
# Ablation strategies
# ---------------------------------------------------------------------------


def test_remove_all_cited_evidence_removes_counter_too() -> None:
    inp = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "evidence": [
            _evidence("E1", "UP", "2025-03-11 08:00"),
            _evidence("E2", "UP", "2025-03-11 09:00"),
            _evidence("E3", "DOWN", "2025-03-11 10:00"),
        ],
    }
    result = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "prediction": "UP", "confidence": 0.6,
        "pro_evidence": [_evidence("E1", "UP", "2025-03-11 08:00")],
        "counter_evidence": [_evidence("E3", "DOWN", "2025-03-11 10:00")],
        "warnings": [], "model_version": "rule_based_v1",
    }
    report_default = FaithfulnessEvaluator().evaluate(inp, result)
    report_all = FaithfulnessEvaluator().evaluate(
        inp, result, ablation_strategy="remove_all_cited_evidence"
    )
    # Different ablation strategies → different confidence drops
    assert report_default["confidence_drop"] != report_all["confidence_drop"]


# ---------------------------------------------------------------------------
# Defensive
# ---------------------------------------------------------------------------


def test_report_keys_all_present() -> None:
    inp, result = _strong_faithful_pair()
    report = FaithfulnessEvaluator().evaluate(inp, result)
    expected_keys = {
        "sample_id", "ticker", "forecast_time", "prediction",
        "original_confidence", "temporal_validity", "evidence_support",
        "confidence_drop", "confidence_after_removal",
        "prediction_after_removal", "faithfulness_score", "verdict",
        "temporal_warnings", "support_warnings", "ablation_warnings",
        "per_evidence_results",
    }
    assert expected_keys.issubset(report.keys())


def test_per_evidence_results_sorted_by_evidence_id() -> None:
    inp = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "evidence": [
            _evidence("Z", "UP", "2025-03-11 08:00"),
            _evidence("A", "UP", "2025-03-11 09:00"),
            _evidence("M", "UP", "2025-03-11 10:00"),
        ],
    }
    result = predict(inp)
    report = FaithfulnessEvaluator().evaluate(inp, result)
    ids = [row["evidence_id"] for row in report["per_evidence_results"]]
    assert ids == sorted(ids)


def test_determinism_same_input_same_output() -> None:
    inp, result = _strong_faithful_pair()
    r1 = FaithfulnessEvaluator().evaluate(inp, result)
    r2 = FaithfulnessEvaluator().evaluate(inp, result)
    assert r1 == r2


def test_default_paths() -> None:
    assert CSV_DEFAULT_PATH == "outputs/faithfulness_results.csv"
    assert JSON_DEFAULT_PATH == "outputs/faithfulness_results.json"


# ---------------------------------------------------------------------------
# Integration with the Forecast Model — multi-record batch
# ---------------------------------------------------------------------------


def test_integration_predict_then_evaluate_batch(tmp_path: Path) -> None:
    """Wires `predict_batch` → `evaluate_batch` and asserts the CSV shape."""
    predict_batch = ForecastModel().predict_batch

    records = []
    for i in range(5):
        records.append({
            "sample_id": f"S-BATCH-{i:02d}",
            "ticker": "AAPL",
            "forecast_time": "2025-03-12 09:00",
            "label": "UP",
            "evidence": [
                _evidence(f"E{i:02d}A", "UP", "2025-03-11 08:00"),
                _evidence(f"E{i:02d}B", "DOWN", "2025-03-11 09:00"),
                _evidence(f"E{i:02d}C", "UP", "2025-03-11 10:00"),
            ],
        })
    results = predict_batch(records, output_csv_path=None, output_json_path=None)
    pairs = list(zip(records, results))
    csv_path = tmp_path / "batch.csv"
    reports = evaluate_batch(pairs, output_csv_path=str(csv_path))
    assert len(reports) == 5
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 5
    for row in rows:
        assert row["verdict"] in {
            "invalid_temporal_leakage",
            "unsupported_evidence",
            "strong_faithful_candidate",
            "moderate_faithful_candidate",
            "weak_faithful_candidate",
            "decorative_explanation_risk",
        }


def test_integration_news_id_collapse_records_warning() -> None:
    """When two evidence snippets share a news_id, the expansion is logged."""
    shared_news_evidence = [
        {
            "evidence_id": "E_A",
            "news_id": "NEWS-1",
            "news_time": "2025-03-11 08:00",
            "evidence_text": "...",
            "polarity": "positive",
            "expected_direction": "UP",
            "support_score": 1.0,
        },
        {
            "evidence_id": "E_B",
            "news_id": "NEWS-1",  # same article
            "news_time": "2025-03-11 09:00",
            "evidence_text": "...",
            "polarity": "positive",
            "expected_direction": "UP",
            "support_score": 1.0,
        },
        {
            "evidence_id": "E_C",
            "news_id": "NEWS-2",
            "news_time": "2025-03-11 10:00",
            "evidence_text": "...",
            "polarity": "negative",
            "expected_direction": "DOWN",
            "support_score": 1.0,
        },
    ]
    inp = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "evidence": shared_news_evidence,
    }
    result = {
        "sample_id": "X", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00",
        "prediction": "UP", "confidence": 0.6,
        "pro_evidence": [shared_news_evidence[0], shared_news_evidence[1]],
        "counter_evidence": [shared_news_evidence[2]],
        "warnings": [], "model_version": "rule_based_v1",
    }
    report = FaithfulnessEvaluator().evaluate(
        inp, result, ablation_strategy="remove_all_cited_evidence"
    )
    # The collapse warning should record that E_A and E_B were collapsed
    # into NEWS-1. The expansion warnings live in `ablation_warnings`.
    collapse_warnings = [
        w for w in report["ablation_warnings"] if w.startswith("COLLAPSED_BY_NEWS_ID")
    ]
    assert any("NEWS-1" in w for w in collapse_warnings)
