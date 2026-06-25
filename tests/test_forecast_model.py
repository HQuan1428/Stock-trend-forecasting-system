"""Unit tests for the Forecast Model (Version 1)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src import forecast_model as fm
from src.forecast_model import (
    CSV_COLUMNS,
    CSV_DEFAULT_PATH,
    ForecastModelError,
    JSON_DEFAULT_PATH,
    MODEL_VERSION,
    OUTPUT_EVIDENCE_LISTS,
    RATIONALE_TEMPLATES,
    REQUIRED_INPUT_FIELDS,
    VALID_DIRECTIONS,
    VALID_PREDICTIONS,
    _build_pro_and_counter,
    _build_rationale,
    _compute_confidence,
    _compute_conflict_ratio,
    _compute_evidence_strength,
    _deduplicate,
    _filter_temporal,
    _is_future,
    _partition_evidence,
    _parse_news_time,
    _vote,
    compute_accuracy_and_confusion,
    predict,
    predict_batch,
    predict_without_evidence,
)


SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples" / "forecast_model"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _evidence(eid: str, direction: str, news_time: str = "2025-03-11 08:30", **extra):
    base = {
        "evidence_id": eid,
        "news_id": eid.split("_E")[0],
        "news_time": news_time,
        "evidence_text": f"phrase for {eid}",
        "polarity": "positive" if direction == "UP" else "negative" if direction == "DOWN" else "neutral",
        "expected_direction": direction,
        "support_score": 1.0,
    }
    base.update(extra)
    return base


@pytest.fixture
def up_input() -> dict:
    return {
        "sample_id": "S0001",
        "ticker": "AAPL",
        "forecast_time": "2025-03-12 09:00",
        "label": "UP",
        "evidence": [
            _evidence("N001_E001", "UP"),
            _evidence("N002_E001", "UP"),
            _evidence("N003_E001", "UP"),
            _evidence("N004_E001", "DOWN"),
        ],
    }


@pytest.fixture
def down_input() -> dict:
    return {
        "sample_id": "S0002",
        "ticker": "MSFT",
        "forecast_time": "2025-04-01 09:00",
        "label": "DOWN",
        "evidence": [
            _evidence("N010_E001", "DOWN", news_time="2025-03-30 08:30"),
            _evidence("N011_E001", "DOWN", news_time="2025-03-30 09:30"),
            _evidence("N012_E001", "DOWN", news_time="2025-03-30 10:30"),
            _evidence("N013_E001", "UP", news_time="2025-03-30 11:30"),
        ],
    }


@pytest.fixture
def balanced_hold_input() -> dict:
    return {
        "sample_id": "S0003",
        "ticker": "GOOGL",
        "forecast_time": "2025-04-15 09:00",
        "label": "HOLD",
        "evidence": [
            _evidence("N020_E001", "UP", news_time="2025-04-14 08:00"),
            _evidence("N021_E001", "UP", news_time="2025-04-14 09:00"),
            _evidence("N022_E001", "DOWN", news_time="2025-04-14 10:00"),
            _evidence("N023_E001", "DOWN", news_time="2025-04-14 11:00"),
        ],
    }


@pytest.fixture
def empty_hold_input() -> dict:
    return {
        "sample_id": "S0004",
        "ticker": "AMZN",
        "forecast_time": "2025-05-01 09:00",
        "label": "HOLD",
        "evidence": [],
    }


@pytest.fixture
def future_evidence_input() -> dict:
    return {
        "sample_id": "S0005",
        "ticker": "TSLA",
        "forecast_time": "2025-03-12 09:00",
        "label": "UP",
        "evidence": [
            _evidence("N030_E001", "UP", news_time="2025-03-11 08:30"),
            _evidence("N031_E001", "UP", news_time="2025-03-11 09:30"),
            _evidence("N032_E001", "UP", news_time="2025-03-12 15:30"),
        ],
    }


@pytest.fixture
def neutral_only_input() -> dict:
    return {
        "sample_id": "S0006",
        "ticker": "META",
        "forecast_time": "2025-06-01 09:00",
        "label": "HOLD",
        "evidence": [
            _evidence("N040_E001", "HOLD"),
            _evidence("N041_E001", "HOLD"),
            _evidence("N042_E001", "HOLD"),
        ],
    }


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_required_input_fields_match_spec() -> None:
    assert REQUIRED_INPUT_FIELDS == ("sample_id", "ticker", "forecast_time", "evidence")


def test_valid_predictions_and_directions_are_canonical() -> None:
    assert VALID_PREDICTIONS == ("UP", "DOWN", "HOLD")
    assert VALID_DIRECTIONS == ("UP", "DOWN", "HOLD")


def test_model_version_is_rule_based_v1() -> None:
    assert MODEL_VERSION == "rule_based_v1"


def test_output_evidence_lists_match_spec() -> None:
    assert OUTPUT_EVIDENCE_LISTS == (
        "pro_evidence",
        "counter_evidence",
        "up_evidence",
        "down_evidence",
        "neutral_evidence",
    )


def test_csv_columns_match_spec() -> None:
    assert CSV_COLUMNS == (
        "sample_id",
        "ticker",
        "forecast_time",
        "prediction",
        "confidence",
        "score",
        "positive_count",
        "negative_count",
        "neutral_count",
        "total_evidence",
        "directional_evidence_count",
        "evidence_strength",
        "conflict_ratio",
        "label",
        "model_version",
    )


def test_default_paths_are_outputs() -> None:
    assert CSV_DEFAULT_PATH == "outputs/prediction_results.csv"
    assert JSON_DEFAULT_PATH == "outputs/prediction_results.json"


def test_rationale_templates_have_four_branches() -> None:
    assert set(RATIONALE_TEMPLATES.keys()) == {
        "UP",
        "DOWN",
        "HOLD_BALANCED",
        "HOLD_NO_DIRECTIONAL",
    }


# ---------------------------------------------------------------------------
# Helpers — voting, confidence, strength, conflict (Task 2.1–2.4, 2.5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "positive,negative,neutral,expected_score,expected_confidence",
    [
        (3, 1, 0, 2, 0.7),
        (1, 3, 0, -2, 0.7),
        (2, 2, 0, 0, 0.5),
        (0, 0, 4, 0, 0.5),
        (0, 0, 0, 0, 0.5),
    ],
)
def test_vote_and_confidence_for_canonical_scenarios(
    positive: int, negative: int, neutral: int, expected_score: int, expected_confidence: float
) -> None:
    items: list[dict] = []
    for i in range(positive):
        items.append(_evidence(f"N{i:03}_P", "UP"))
    for i in range(negative):
        items.append(_evidence(f"N{i:03}_N", "DOWN"))
    for i in range(neutral):
        items.append(_evidence(f"N{i:03}_H", "HOLD"))
    p, n, h, score = _vote(items)
    assert (p, n, h, score) == (positive, negative, neutral, expected_score)
    assert _compute_confidence(score, p + n) == expected_confidence


def test_vote_skips_unknown_directions_silently() -> None:
    items = [
        _evidence("N001_E001", "UP"),
        _evidence("N002_E001", "INVALID"),
        _evidence("N003_E001", "DOWN"),
    ]
    p, n, h, score = _vote(items)
    assert (p, n, h, score) == (1, 1, 0, 0)


def test_compute_confidence_saturates_at_095() -> None:
    assert _compute_confidence(5, 5) == 0.95
    assert _compute_confidence(10, 10) == 0.95


def test_compute_evidence_strength_zero_when_no_directional() -> None:
    assert _compute_evidence_strength(0, 0) == 0.0


def test_compute_conflict_ratio_zero_when_no_directional() -> None:
    assert _compute_conflict_ratio(0, 0) == 0.0


# Task 11.1 — evidence_strength / conflict_ratio formulas
@pytest.mark.parametrize(
    "positive,negative,expected_strength,expected_ratio",
    [
        (1, 0, 1.0, 0.0),
        (3, 1, 0.5, 0.25),
        (1, 1, 0.0, 0.5),
        (0, 0, 0.0, 0.0),
    ],
)
def test_evidence_strength_and_conflict_ratio_formulas(
    positive: int, negative: int, expected_strength: float, expected_ratio: float
) -> None:
    score = positive - negative
    assert _compute_evidence_strength(score, positive + negative) == expected_strength
    assert _compute_conflict_ratio(positive, negative) == expected_ratio


# Task 11.2 — confidence clamping at 0.5 and 0.95
@pytest.mark.parametrize("score,expected", [(0, 0.5), (5, 0.95), (10, 0.95)])
def test_confidence_clamping(score: int, expected: float) -> None:
    directional = max(abs(score), 1)
    assert _compute_confidence(score, directional) == expected


# ---------------------------------------------------------------------------
# Partition (Task 3.1, 3.3)
# ---------------------------------------------------------------------------


def test_partition_evidence_sorts_by_evidence_id() -> None:
    items = [
        _evidence("N003_E001", "UP"),
        _evidence("N001_E001", "DOWN"),
        _evidence("N002_E001", "UP"),
    ]
    warnings: list[dict] = []
    partitioned = _partition_evidence(items, warnings)
    assert [e["evidence_id"] for e in partitioned["up_evidence"]] == ["N002_E001", "N003_E001"]
    assert [e["evidence_id"] for e in partitioned["down_evidence"]] == ["N001_E001"]


def test_partition_evidence_routes_invalid_to_warnings() -> None:
    items = [
        _evidence("N001_E001", "UP"),
        _evidence("N002_E001", "INVALID"),
    ]
    warnings: list[dict] = []
    partitioned = _partition_evidence(items, warnings)
    assert len(partitioned["up_evidence"]) == 1
    assert len(partitioned["down_evidence"]) == 0
    assert any(w["code"] == "INVALID_EVIDENCE" for w in warnings)


def test_partition_strips_label_leakage() -> None:
    item = _evidence("N001_E001", "UP")
    item["ground_truth_label"] = "UP"
    item["label"] = "UP"
    warnings: list[dict] = []
    partitioned = _partition_evidence([item], warnings)
    assert "label" not in partitioned["up_evidence"][0]
    assert "ground_truth_label" not in partitioned["up_evidence"][0]


@pytest.mark.parametrize(
    "prediction, up, down, expected_pro, expected_counter",
    [
        ("UP", ["u1", "u2"], ["d1"], ["u1", "u2"], ["d1"]),
        ("DOWN", ["u1"], ["d1", "d2"], ["d1", "d2"], ["u1"]),
        ("HOLD", ["u1", "u2"], ["d1", "d2"], [], []),
    ],
)
def test_build_pro_and_counter_branches(
    prediction: str, up: list[str], down: list[str], expected_pro: list[str], expected_counter: list[str]
) -> None:
    up_items = [{"evidence_id": x} for x in up]
    down_items = [{"evidence_id": x} for x in down]
    pro, counter = _build_pro_and_counter(prediction, up_items, down_items)
    assert [e["evidence_id"] for e in pro] == expected_pro
    assert [e["evidence_id"] for e in counter] == expected_counter


# ---------------------------------------------------------------------------
# Rationale (Task 4.1, 4.2, 11.3)
# ---------------------------------------------------------------------------


def test_build_rationale_up_branch() -> None:
    assert _build_rationale("UP", 3, 1, 4) == (
        "Prediction UP because positive evidence count (3) is greater than negative evidence count (1)."
    )


def test_build_rationale_down_branch() -> None:
    assert _build_rationale("DOWN", 1, 3, 4) == (
        "Prediction DOWN because negative evidence count (3) is greater than positive evidence count (1)."
    )


def test_build_rationale_hold_balanced_branch() -> None:
    assert _build_rationale("HOLD", 2, 2, 4) == (
        "Prediction HOLD because positive and negative evidence are balanced."
    )


def test_build_rationale_hold_no_directional_branch() -> None:
    assert _build_rationale("HOLD", 0, 0, 0) == (
        "Prediction HOLD because positive and negative evidence are balanced or no valid directional evidence is available."
    )


# ---------------------------------------------------------------------------
# Temporal helpers (Task 5.1–5.4, 5.5, 11.6)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("", None),
        ("not-a-date", None),
        ("2025-03-12T09:00:00", "2025-03-12 09:00:00"),
        ("2025-03-12 09:00", "2025-03-12 09:00:00"),
    ],
)
def test_parse_news_time(value, expected) -> None:
    parsed = _parse_news_time(value)
    if expected is None:
        assert parsed is None
    else:
        assert parsed is not None
        assert parsed.strftime("%Y-%m-%d %H:%M:%S") == expected


def test_is_future_strict_inequality() -> None:
    ft = _parse_news_time("2025-03-12 09:00")
    assert _is_future(_parse_news_time("2025-03-12 15:30"), ft) is True
    assert _is_future(_parse_news_time("2025-03-12 09:00"), ft) is False
    assert _is_future(_parse_news_time("2025-03-12 08:00"), ft) is False
    assert _is_future(None, ft) is False


def test_deduplicate_keeps_first_and_warns() -> None:
    items = [
        _evidence("N001_E001", "UP"),
        _evidence("N002_E001", "DOWN"),
        _evidence("N001_E001", "UP"),
    ]
    warnings: list[dict] = []
    out = _deduplicate(items, warnings)
    assert len(out) == 2
    assert any(w["code"] == "DUPLICATE_EVIDENCE_ID" for w in warnings)


def test_filter_temporal_blocks_future() -> None:
    items = [
        _evidence("N001_E001", "UP", news_time="2025-03-12 15:30"),
    ]
    warnings: list[dict] = []
    out = _filter_temporal(items, _parse_news_time("2025-03-12 09:00"), warnings)
    assert out == []
    assert any(w["code"] == "TEMPORAL_LEAKAGE_BLOCKED" for w in warnings)


def test_filter_temporal_keeps_equal_timestamp() -> None:
    items = [
        _evidence("N001_E001", "UP", news_time="2025-03-12 09:00"),
    ]
    warnings: list[dict] = []
    out = _filter_temporal(items, _parse_news_time("2025-03-12 09:00"), warnings)
    assert len(out) == 1
    assert not any(w["code"] == "TEMPORAL_LEAKAGE_BLOCKED" for w in warnings)


def test_filter_temporal_keeps_missing_with_malformed_warning() -> None:
    items = [
        _evidence("N001_E001", "UP", news_time="not-a-date"),
    ]
    warnings: list[dict] = []
    out = _filter_temporal(items, _parse_news_time("2025-03-12 09:00"), warnings)
    assert len(out) == 1
    assert any(w["code"] == "MALFORMED_NEWS_TIME" for w in warnings)


# ---------------------------------------------------------------------------
# Acceptance scenarios (Tasks 6.4, 10.x)
# ---------------------------------------------------------------------------


def test_scenario_1_predict_up_from_positive_dominant(up_input: dict) -> None:
    result = predict(up_input)
    assert result["prediction"] == "UP"
    assert result["score"] == 2
    assert result["confidence"] == 0.7
    assert result["positive_count"] == 3
    assert result["negative_count"] == 1
    assert result["directional_evidence_count"] == 4
    assert result["evidence_strength"] == 0.5
    assert result["conflict_ratio"] == 0.25
    assert len(result["pro_evidence"]) == 3
    assert len(result["counter_evidence"]) == 1
    assert result["rationale"] == (
        "Prediction UP because positive evidence count (3) is greater than negative evidence count (1)."
    )
    assert result["warnings"] == []
    assert result["model_version"] == MODEL_VERSION


def test_scenario_2_predict_down_from_negative_dominant(down_input: dict) -> None:
    result = predict(down_input)
    assert result["prediction"] == "DOWN"
    assert result["score"] == -2
    assert result["confidence"] == 0.7
    assert result["rationale"] == (
        "Prediction DOWN because negative evidence count (3) is greater than positive evidence count (1)."
    )


def test_scenario_3_predict_hold_from_balanced(balanced_hold_input: dict) -> None:
    result = predict(balanced_hold_input)
    assert result["prediction"] == "HOLD"
    assert result["score"] == 0
    assert result["confidence"] == 0.5
    assert result["positive_count"] == 2
    assert result["negative_count"] == 2
    assert result["rationale"] == "Prediction HOLD because positive and negative evidence are balanced."


def test_scenario_4_predict_hold_from_neutral_only(neutral_only_input: dict) -> None:
    result = predict(neutral_only_input)
    assert result["prediction"] == "HOLD"
    assert result["score"] == 0
    assert result["confidence"] == 0.5
    assert result["directional_evidence_count"] == 0
    assert result["evidence_strength"] == 0.0
    assert result["neutral_count"] == 3
    assert result["up_evidence"] == []
    assert result["down_evidence"] == []
    assert len(result["neutral_evidence"]) == 3
    assert result["pro_evidence"] == []
    assert result["counter_evidence"] == []
    assert result["rationale"] == (
        "Prediction HOLD because positive and negative evidence are balanced or no valid directional evidence is available."
    )


def test_scenario_5_predict_hold_from_empty(empty_hold_input: dict) -> None:
    result = predict(empty_hold_input)
    assert result["prediction"] == "HOLD"
    assert result["score"] == 0
    assert result["confidence"] == 0.5
    assert result["total_evidence"] == 0
    assert result["positive_count"] == 0
    assert result["negative_count"] == 0
    assert result["neutral_count"] == 0
    assert result["evidence_strength"] == 0.0
    assert result["conflict_ratio"] == 0.0
    assert result["pro_evidence"] == []
    assert result["counter_evidence"] == []
    assert result["up_evidence"] == []
    assert result["down_evidence"] == []
    assert result["neutral_evidence"] == []
    assert result["rationale"] == (
        "Prediction HOLD because positive and negative evidence are balanced or no valid directional evidence is available."
    )
    assert result["warnings"] == []


def test_scenario_6_block_future_evidence(future_evidence_input: dict) -> None:
    result = predict(future_evidence_input)
    future_warning = [w for w in result["warnings"] if w["code"] == "TEMPORAL_LEAKAGE_BLOCKED"]
    assert len(future_warning) == 1
    assert future_warning[0]["evidence_id"] == "N032_E001"
    assert all(e["evidence_id"] != "N032_E001" for e in result["up_evidence"])
    assert all(e["evidence_id"] != "N032_E001" for e in result["pro_evidence"])
    assert result["prediction"] == "UP"


def test_scenario_7_predict_without_evidence_drops_confidence() -> None:
    """Build a fixture with original confidence 0.8 (3 UP, 0 DOWN) so
    removing the pro evidence drops confidence by a measurable amount.
    """
    request = {
        "sample_id": "S7",
        "ticker": "AAPL",
        "forecast_time": "2025-03-12 09:00",
        "label": "UP",
        "evidence": [
            _evidence("N001_E001", "UP"),
            _evidence("N002_E001", "UP"),
            _evidence("N003_E001", "UP"),
        ],
    }
    original = predict(request)
    assert original["confidence"] == pytest.approx(0.8)
    pro_ids = [e["evidence_id"] for e in original["pro_evidence"]]
    reduced = predict_without_evidence(request, pro_ids)
    assert reduced["prediction"] == "HOLD"
    confidence_drop = original["confidence"] - reduced["confidence"]
    assert confidence_drop >= 0.05


def test_scenario_7b_predict_without_evidence_empty_matches_predict(up_input: dict) -> None:
    a = predict(up_input)
    b = predict_without_evidence(up_input, [])
    assert a == b


def test_scenario_7c_predict_without_evidence_none_matches_predict(up_input: dict) -> None:
    a = predict(up_input)
    b = predict_without_evidence(up_input, None)
    assert a == b


def test_scenario_7d_predict_without_evidence_unknown_ids_matches_predict(up_input: dict) -> None:
    a = predict(up_input)
    b = predict_without_evidence(up_input, ["UNKNOWN_E001", "UNKNOWN_E002"])
    assert a == b


def test_scenario_8_rationale_template_based(up_input: dict) -> None:
    result = predict(up_input)
    assert "positive evidence count (3)" in result["rationale"]
    assert "negative evidence count (1)" in result["rationale"]
    forbidden = ["market conditions", "macro events", "prior session"]
    for phrase in forbidden:
        assert phrase not in result["rationale"]


# ---------------------------------------------------------------------------
# Edge cases and defensive behavior (Task 11.x)
# ---------------------------------------------------------------------------


def test_predict_rejects_missing_sample_id() -> None:
    with pytest.raises(ForecastModelError):
        predict({"ticker": "AAPL", "forecast_time": "2025-03-12 09:00", "evidence": []})


def test_predict_rejects_missing_ticker() -> None:
    with pytest.raises(ForecastModelError):
        predict({"sample_id": "S1", "forecast_time": "2025-03-12 09:00", "evidence": []})


def test_predict_rejects_missing_evidence() -> None:
    with pytest.raises(ForecastModelError):
        predict({"sample_id": "S1", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00"})


def test_predict_rejects_missing_forecast_time() -> None:
    with pytest.raises(ForecastModelError):
        predict({"sample_id": "S1", "ticker": "AAPL", "evidence": []})


def test_predict_rejects_unparseable_forecast_time() -> None:
    with pytest.raises(ForecastModelError):
        predict(
            {
                "sample_id": "S1",
                "ticker": "AAPL",
                "forecast_time": "not-a-date",
                "evidence": [],
            }
        )


def test_invalid_expected_direction_skipped_with_warning_by_default(up_input: dict) -> None:
    up_input["evidence"].append(_evidence("N099_E001", "INVALID"))
    result = predict(up_input)
    assert any(w["code"] == "INVALID_EVIDENCE" for w in result["warnings"])
    assert not any(e["evidence_id"] == "N099_E001" for e in result["up_evidence"] + result["down_evidence"])


def test_invalid_expected_direction_raises_under_strict(up_input: dict) -> None:
    up_input["evidence"].append(_evidence("N099_E001", "INVALID"))
    with pytest.raises(ForecastModelError):
        predict(up_input, strict=True)


def test_malformed_news_time_emits_warning_but_keeps_item() -> None:
    request = {
        "sample_id": "S1",
        "ticker": "AAPL",
        "forecast_time": "2025-03-12 09:00",
        "evidence": [_evidence("N001_E001", "UP", news_time="garbage")],
    }
    result = predict(request)
    assert any(w["code"] == "MALFORMED_NEWS_TIME" for w in result["warnings"])
    assert len(result["up_evidence"]) == 1


def test_duplicate_evidence_id_keeps_first_warns_second(up_input: dict) -> None:
    up_input["evidence"].append(_evidence("N001_E001", "UP"))
    result = predict(up_input)
    duplicate_warnings = [w for w in result["warnings"] if w["code"] == "DUPLICATE_EVIDENCE_ID"]
    assert len(duplicate_warnings) == 1
    assert duplicate_warnings[0]["evidence_id"] == "N001_E001"
    n001_in_up = [e for e in result["up_evidence"] if e["evidence_id"] == "N001_E001"]
    assert len(n001_in_up) == 1


def test_output_evidence_lists_are_always_lists_never_null(empty_hold_input: dict) -> None:
    result = predict(empty_hold_input)
    for key in OUTPUT_EVIDENCE_LISTS:
        assert result[key] == []
        assert isinstance(result[key], list)


def test_field_preservation_in_output(up_input: dict) -> None:
    result = predict(up_input)
    for item in result["up_evidence"] + result["pro_evidence"] + result["counter_evidence"]:
        for key in (
            "evidence_id",
            "news_id",
            "news_time",
            "evidence_text",
            "polarity",
            "expected_direction",
            "support_score",
        ):
            assert key in item
        assert "ground_truth_label" not in item


def test_determinism(up_input: dict) -> None:
    a = predict(up_input)
    b = predict(up_input)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_predict_does_not_read_label(up_input: dict) -> None:
    """`predict` echoes label but never uses it for prediction."""
    up_input["label"] = "DOWN"
    result = predict(up_input)
    assert result["prediction"] == "UP"
    assert result["label"] == "DOWN"


# ---------------------------------------------------------------------------
# Batch and evaluation helper (Task 7.3, 6.4, 10.9)
# ---------------------------------------------------------------------------


def test_batch_returns_one_result_per_record_in_order(
    up_input: dict, down_input: dict, balanced_hold_input: dict
) -> None:
    results = predict_batch([up_input, down_input, balanced_hold_input], output_csv_path=None, output_json_path=None)
    assert len(results) == 3
    assert results[0]["prediction"] == "UP"
    assert results[1]["prediction"] == "DOWN"
    assert results[2]["prediction"] == "HOLD"
    assert json.dumps(results)  # serializable


def test_batch_writes_csv_with_correct_header(tmp_path: Path) -> None:
    request = {
        "sample_id": "S0001",
        "ticker": "AAPL",
        "forecast_time": "2025-03-12 09:00",
        "label": "UP",
        "evidence": [
            _evidence("N001_E001", "UP"),
            _evidence("N002_E001", "UP"),
            _evidence("N003_E001", "UP"),
            _evidence("N004_E001", "DOWN"),
        ],
    }
    csv_path = tmp_path / "out.csv"
    predict_batch([request], output_csv_path=str(csv_path), output_json_path=None)
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0].keys()) == list(CSV_COLUMNS)
    assert len(rows) == 1
    assert rows[0]["sample_id"] == "S0001"
    assert rows[0]["prediction"] == "UP"
    assert rows[0]["label"] == "UP"
    assert rows[0]["model_version"] == MODEL_VERSION


def test_batch_writes_json_sibling(tmp_path: Path) -> None:
    request = {
        "sample_id": "S0001",
        "ticker": "AAPL",
        "forecast_time": "2025-03-12 09:00",
        "label": "UP",
        "evidence": [
            _evidence("N001_E001", "UP"),
            _evidence("N002_E001", "UP"),
            _evidence("N003_E001", "UP"),
            _evidence("N004_E001", "DOWN"),
        ],
    }
    json_path = tmp_path / "out.json"
    predict_batch([request], output_csv_path=None, output_json_path=str(json_path))
    with json_path.open() as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["sample_id"] == "S0001"
    assert isinstance(data[0]["pro_evidence"], list)


def test_batch_input_error_yields_default_hold() -> None:
    bad = {"sample_id": "S999", "ticker": "AAPL"}  # missing forecast_time, evidence
    results = predict_batch([bad], output_csv_path=None, output_json_path=None)
    assert len(results) == 1
    assert results[0]["prediction"] == "HOLD"
    assert results[0]["confidence"] == 0.5
    assert any(w["code"] == "INPUT_ERROR" for w in results[0]["warnings"])


def test_compute_accuracy_and_confusion_small_fixture() -> None:
    """2 UP/UP, 1 UP/DOWN, 1 DOWN/UP, 1 HOLD/HOLD, 1 DOWN/HOLD."""
    base_input = {
        "sample_id": "S1",
        "ticker": "AAPL",
        "forecast_time": "2025-03-12 09:00",
        "evidence": [],
    }
    records = []
    records.append({**base_input, "label": "UP", "evidence": [_evidence("N001_E001", "UP")]})  # UP
    records.append({**base_input, "label": "UP", "evidence": [_evidence("N002_E001", "UP")]})  # UP
    records.append({**base_input, "label": "DOWN", "evidence": [_evidence("N003_E001", "UP")]})  # mispredict UP
    records.append({**base_input, "label": "UP", "evidence": [_evidence("N004_E001", "DOWN")]})  # mispredict DOWN
    records.append({**base_input, "label": "HOLD", "evidence": [_evidence("N005_E001", "UP"), _evidence("N006_E001", "DOWN")]})  # HOLD correct
    records.append({**base_input, "label": "DOWN", "evidence": [_evidence("N007_E001", "UP"), _evidence("N008_E001", "DOWN")]})  # HOLD not DOWN
    results = predict_batch(records, output_csv_path=None, output_json_path=None)
    metrics = compute_accuracy_and_confusion(results)
    assert metrics["n_samples"] == 6
    assert metrics["accuracy"] == pytest.approx(3 / 6)
    matrix = metrics["confusion_matrix"]["matrix"]
    # rows = predicted, cols = actual, order UP/DOWN/HOLD
    # predicted UP: 3 actual (UP=2, DOWN=1, HOLD=0) → row [2, 1, 0]
    # predicted DOWN: 1 actual (UP=1, DOWN=0, HOLD=0) → row [1, 0, 0]
    # predicted HOLD: 2 actual (UP=0, DOWN=1, HOLD=1) → row [0, 1, 1]
    assert matrix == [[2, 1, 0], [1, 0, 0], [0, 1, 1]]
    for label in ("UP", "DOWN", "HOLD"):
        assert label in metrics["per_class"]
        for key in ("precision", "recall", "f1", "support"):
            assert key in metrics["per_class"][label]


def test_compute_accuracy_and_confusion_raises_on_non_empty_no_labels() -> None:
    records = [
        {
            "sample_id": "S1",
            "ticker": "AAPL",
            "forecast_time": "2025-03-12 09:00",
            "evidence": [_evidence("N001_E001", "UP")],
        }
    ]
    results = predict_batch(records, output_csv_path=None, output_json_path=None)
    with pytest.raises(ValueError):
        compute_accuracy_and_confusion(results)


def test_compute_accuracy_and_confusion_empty_input() -> None:
    metrics = compute_accuracy_and_confusion([])
    assert metrics["n_samples"] == 0
    assert metrics["accuracy"] == 0.0
    assert metrics["confusion_matrix"]["matrix"] == [[0, 0, 0], [0, 0, 0], [0, 0, 0]]


def test_compute_accuracy_and_confusion_accepts_input_record_pairs() -> None:
    inp = {
        "sample_id": "S1",
        "ticker": "AAPL",
        "forecast_time": "2025-03-12 09:00",
        "label": "UP",
        "evidence": [_evidence("N001_E001", "UP")],
    }
    result = predict(inp)
    metrics = compute_accuracy_and_confusion([(inp, result)])
    assert metrics["n_samples"] == 1


# ---------------------------------------------------------------------------
# Integration test (Task 12.1, 12.2, 12.3)
# ---------------------------------------------------------------------------


def test_integration_end_to_end_through_extractor_and_selector(tmp_path: Path) -> None:
    """`extract_evidence` → mocked selector → `predict` → well-formed result."""
    from src.evidence_extractor import extract_evidence

    news_time = "2025-03-11 08:30"
    raw = {
        "news_id": "N001",
        "ticker": "AAPL",
        "forecast_time": "2025-03-12 09:00",
        "news_time": news_time,
        "news_text": "Apple announces strong sales",
    }
    extractor_result = extract_evidence(raw)
    candidates = extractor_result["evidence"]
    # mock the selector: each candidate with positive polarity → UP, etc.
    selected = []
    for c in candidates:
        polarity = c["polarity"]
        direction = "UP" if polarity == "positive" else "DOWN" if polarity == "negative" else "HOLD"
        selected.append(
            {
                "evidence_id": c["evidence_id"],
                "news_id": c["news_id"],
                "news_time": news_time,
                "evidence_text": c["evidence_text"],
                "polarity": polarity,
                "expected_direction": direction,
                "support_score": c["support_score"],
            }
        )
    request = {
        "sample_id": "S0001",
        "ticker": "AAPL",
        "forecast_time": "2025-03-12 09:00",
        "evidence": selected,
    }
    result = predict(request)
    assert result["model_version"] == MODEL_VERSION
    assert result["prediction"] in VALID_PREDICTIONS
    assert 0.5 <= result["confidence"] <= 0.95


def test_integration_batch_csv_and_json_siblings(tmp_path: Path) -> None:
    csv_path = tmp_path / "predictions.csv"
    json_path = tmp_path / "predictions.json"
    records = [
        {
            "sample_id": f"S{i:04}",
            "ticker": "AAPL",
            "forecast_time": "2025-03-12 09:00",
            "label": "UP" if i % 2 == 0 else "DOWN",
            "evidence": [_evidence(f"N{i:03}_E001", "UP" if i % 2 == 0 else "DOWN")],
        }
        for i in range(5)
    ]
    results = predict_batch(records, output_csv_path=str(csv_path), output_json_path=str(json_path))
    assert len(results) == 5
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0].keys()) == list(CSV_COLUMNS)
    assert len(rows) == 5
    with json_path.open() as f:
        data = json.load(f)
    assert len(data) == 5
    for r in data:
        assert "pro_evidence" in r
        assert isinstance(r["pro_evidence"], list)


def test_integration_batch_with_evaluation_metrics(tmp_path: Path) -> None:
    records = [
        {
            "sample_id": "S0001",
            "ticker": "AAPL",
            "forecast_time": "2025-03-12 09:00",
            "label": "UP",
            "evidence": [_evidence("N001_E001", "UP")],
        },
        {
            "sample_id": "S0002",
            "ticker": "AAPL",
            "forecast_time": "2025-03-12 09:00",
            "label": "DOWN",
            "evidence": [_evidence("N002_E001", "DOWN")],
        },
    ]
    results = predict_batch(records, output_csv_path=None, output_json_path=None)
    metrics = compute_accuracy_and_confusion(results)
    assert metrics["n_samples"] == 2
    assert metrics["accuracy"] == 1.0


# ---------------------------------------------------------------------------
# Golden fixture regression (Task 9.7)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture_stem",
    [
        "01_up",
        "02_down",
        "03_balanced_hold",
        "04_empty_hold",
        "05_future_evidence",
    ],
)
def test_golden_fixture_matches_forecast_output(fixture_stem: str) -> None:
    """Every documented example under samples/forecast_model/ must match byte-for-byte."""
    inp_path = SAMPLES_DIR / f"{fixture_stem}_input.json"
    exp_path = SAMPLES_DIR / f"{fixture_stem}_expected.json"
    if not inp_path.exists() or not exp_path.exists():
        pytest.fail(f"Golden fixture pair missing for {fixture_stem}")
    input_data = json.loads(inp_path.read_text())
    expected = json.loads(exp_path.read_text())
    result = predict(input_data)
    if result != expected:
        diff_keys = sorted({k for k in (set(result) | set(expected)) if result.get(k) != expected.get(k)})
        pytest.fail(
            f"Golden fixture {fixture_stem} drifted. "
            f"Differing keys: {diff_keys}\n"
            f"got: {json.dumps(result, indent=2, sort_keys=True)}\n"
            f"expected: {json.dumps(expected, indent=2, sort_keys=True)}"
        )


# ---------------------------------------------------------------------------
# Module integration (no circular imports)
# ---------------------------------------------------------------------------


def test_module_does_not_import_extractor_or_selector() -> None:
    """Forecast Model must not import from the Evidence Extractor or Selector."""
    import importlib
    from src import forecast_model

    importlib.reload(forecast_model)
    src_text = Path(forecast_model.__file__).read_text()
    assert "from src.evidence_extractor" not in src_text
    assert "from src.evidence_selector" not in src_text
    assert "import src.evidence_extractor" not in src_text
    assert "import src.evidence_selector" not in src_text
