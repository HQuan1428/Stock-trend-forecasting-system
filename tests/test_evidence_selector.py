"""Unit tests for the Evidence Selector (Version 1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evidence_selector import EvidenceSelector, EvidenceSelectorError

_selector = EvidenceSelector()
CLASSIFICATION_TABLE = EvidenceSelector.CLASSIFICATION_TABLE
DEFAULT_TOP_K = EvidenceSelector.DEFAULT_TOP_K
EVIDENCE_SELECTOR_FIELDS = EvidenceSelector.EVIDENCE_SELECTOR_FIELDS
OUTPUT_GROUPS = EvidenceSelector.OUTPUT_GROUPS
REASON_TABLE = EvidenceSelector.REASON_TABLE
REQUIRED_INPUT_FIELDS = EvidenceSelector.REQUIRED_INPUT_FIELDS
SELECTION_METHOD = EvidenceSelector.SELECTION_METHOD
VALID_DIRECTIONS = EvidenceSelector.VALID_DIRECTIONS
VALID_PREDICTIONS = EvidenceSelector.VALID_PREDICTIONS
_classify = _selector._classify
_is_future = _selector._is_future
_parse_news_time = _selector._parse_news_time
compute_coverage = _selector.compute_coverage
select_evidence = _selector.select
select_evidence_batch = _selector.select_batch


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_classification_table_has_nine_cells() -> None:
    assert len(CLASSIFICATION_TABLE) == 9
    for prediction in VALID_PREDICTIONS:
        for direction in VALID_DIRECTIONS:
            assert (prediction, direction) in CLASSIFICATION_TABLE
            assert CLASSIFICATION_TABLE[(prediction, direction)] in (
                "pro",
                "counter",
                "neutral",
            )


def test_reason_table_matches_classification_table_keys() -> None:
    assert set(REASON_TABLE.keys()) == set(CLASSIFICATION_TABLE.keys())


def test_required_input_fields_match_spec() -> None:
    assert REQUIRED_INPUT_FIELDS == (
        "ticker",
        "forecast_time",
        "prediction",
        "confidence",
        "evidence_candidates",
    )


def test_output_groups_match_spec() -> None:
    assert OUTPUT_GROUPS == ("pro_evidence", "counterevidence", "neutral_evidence")


def test_default_top_k_is_three_per_group() -> None:
    assert DEFAULT_TOP_K == {"pro_evidence": 3, "counterevidence": 3, "neutral_evidence": 3}


def test_selection_method_is_rule_based() -> None:
    assert SELECTION_METHOD == "rule_based"


def test_evidence_selector_fields_contains_required_keys() -> None:
    expected_subset = {
        "news_id",
        "ticker",
        "news_time",
        "evidence_text",
        "polarity",
        "expected_direction",
        "extractor_score",
        "selector_label",
        "selector_score",
        "reason",
    }
    assert expected_subset.issubset(set(EVIDENCE_SELECTOR_FIELDS))


# ---------------------------------------------------------------------------
# Classification helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prediction, direction, expected_label",
    [
        ("UP", "UP", "pro"),
        ("UP", "DOWN", "counter"),
        ("UP", "HOLD", "neutral"),
        ("DOWN", "DOWN", "pro"),
        ("DOWN", "UP", "counter"),
        ("DOWN", "HOLD", "neutral"),
        ("HOLD", "HOLD", "pro"),
        ("HOLD", "UP", "counter"),
        ("HOLD", "DOWN", "counter"),
    ],
)
def test_classify_full_matrix(
    prediction: str, direction: str, expected_label: str
) -> None:
    label, reason = _classify(prediction, direction)
    assert label == expected_label
    # The reason string must mention both the evidence direction and the prediction.
    assert prediction in reason or direction in reason


def test_classify_rejects_unknown_prediction() -> None:
    with pytest.raises(EvidenceSelectorError):
        _classify("MAYBE", "UP")


def test_classify_rejects_unknown_direction() -> None:
    with pytest.raises(EvidenceSelectorError):
        _classify("UP", "MAYBE")


@pytest.mark.parametrize(
    "prediction, direction, expected_reason_substring",
    [
        ("UP", "UP", "matches prediction UP"),
        ("UP", "DOWN", "conflicts with prediction UP"),
        ("UP", "HOLD", "HOLD is not directional for prediction UP"),
        ("DOWN", "DOWN", "matches prediction DOWN"),
        ("DOWN", "UP", "conflicts with prediction DOWN"),
        ("DOWN", "HOLD", "HOLD is not directional for prediction DOWN"),
        ("HOLD", "HOLD", "matches prediction HOLD"),
        ("HOLD", "UP", "conflicts with prediction HOLD"),
        ("HOLD", "DOWN", "conflicts with prediction HOLD"),
    ],
)
def test_reason_strings_match_spec(
    prediction: str, direction: str, expected_reason_substring: str
) -> None:
    _, reason = _classify(prediction, direction)
    assert expected_reason_substring in reason


# ---------------------------------------------------------------------------
# _parse_news_time / _is_future helpers
# ---------------------------------------------------------------------------


def test_parse_news_time_returns_none_for_missing() -> None:
    assert _parse_news_time(None) is None
    assert _parse_news_time("") is None
    assert _parse_news_time("   ") is None
    assert _parse_news_time("not-a-date") is None


def test_parse_news_time_parses_iso_naive() -> None:
    dt = _parse_news_time("2025-03-11 08:30")
    assert dt is not None
    assert dt.year == 2025 and dt.month == 3 and dt.day == 11


def test_is_future_strict_inequality() -> None:
    from datetime import datetime, timezone

    ft = datetime(2025, 3, 12, 9, 0, 0, tzinfo=timezone.utc)
    assert _is_future(datetime(2025, 3, 12, 10, 0, 0, tzinfo=timezone.utc), ft) is True
    assert _is_future(datetime(2025, 3, 12, 9, 0, 0, tzinfo=timezone.utc), ft) is False
    assert _is_future(datetime(2025, 3, 12, 8, 0, 0, tzinfo=timezone.utc), ft) is False


def test_is_future_handles_none_defensively() -> None:
    from datetime import datetime, timezone

    ft = datetime(2025, 3, 12, 9, 0, 0, tzinfo=timezone.utc)
    assert _is_future(None, ft) is False
    assert _is_future(None, None) is False


# ---------------------------------------------------------------------------
# Public API — request builders
# ---------------------------------------------------------------------------


def _base_request(**overrides) -> dict:
    base = {
        "ticker": "AAPL",
        "forecast_time": "2025-03-12 09:00",
        "prediction": "UP",
        "confidence": 0.82,
        "evidence_candidates": [],
    }
    base.update(overrides)
    return base


def _cand(
    news_id: str,
    expected_direction: str,
    extractor_score: float = 0.8,
    news_time: str = "2025-03-11 08:00",
    **extras,
) -> dict:
    item = {
        "news_id": news_id,
        "ticker": "AAPL",
        "news_time": news_time,
        "evidence_text": f"text for {news_id}",
        "polarity": "positive" if expected_direction == "UP" else "negative",
        "expected_direction": expected_direction,
        "extractor_score": extractor_score,
    }
    item.update(extras)
    return item


# ---------------------------------------------------------------------------
# Top-level validation
# ---------------------------------------------------------------------------


def test_select_evidence_rejects_non_dict_request() -> None:
    with pytest.raises(EvidenceSelectorError):
        select_evidence("not a dict")  # type: ignore[arg-type]


def test_select_evidence_rejects_missing_prediction() -> None:
    req = _base_request()
    del req["prediction"]
    with pytest.raises(EvidenceSelectorError):
        select_evidence(req)


def test_select_evidence_rejects_unknown_prediction() -> None:
    req = _base_request(prediction="MAYBE")
    with pytest.raises(EvidenceSelectorError):
        select_evidence(req)


def test_select_evidence_rejects_non_list_candidates() -> None:
    req = _base_request(evidence_candidates="not a list")
    with pytest.raises(EvidenceSelectorError):
        select_evidence(req)


def test_select_evidence_rejects_missing_forecast_time() -> None:
    req = _base_request()
    del req["forecast_time"]
    with pytest.raises(EvidenceSelectorError):
        select_evidence(req)


def test_select_evidence_rejects_malformed_forecast_time() -> None:
    req = _base_request(forecast_time="not-a-date")
    with pytest.raises(EvidenceSelectorError):
        select_evidence(req)


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


def test_empty_evidence_list_returns_empty_groups_and_zero_counts() -> None:
    result = select_evidence(_base_request())
    assert result["pro_evidence"] == []
    assert result["counterevidence"] == []
    assert result["neutral_evidence"] == []
    assert result["invalid_future_evidence"] == []
    assert result["summary"] == {
        "pro_count": 0,
        "counter_count": 0,
        "neutral_count": 0,
        "has_counterevidence": False,
        "counterevidence_ratio": 0.0,
    }
    assert result["selection_method"] == "rule_based"


# ---------------------------------------------------------------------------
# Classification — full 9-cell matrix via the public API
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prediction, expected_direction, expected_label",
    [
        ("UP", "UP", "pro"),
        ("UP", "DOWN", "counter"),
        ("UP", "HOLD", "neutral"),
        ("DOWN", "DOWN", "pro"),
        ("DOWN", "UP", "counter"),
        ("DOWN", "HOLD", "neutral"),
        ("HOLD", "HOLD", "pro"),
        ("HOLD", "UP", "counter"),
        ("HOLD", "DOWN", "counter"),
    ],
)
def test_full_classification_matrix_via_public_api(
    prediction: str, expected_direction: str, expected_label: str
) -> None:
    req = _base_request(
        prediction=prediction,
        evidence_candidates=[_cand("n1", expected_direction)],
    )
    result = select_evidence(req)

    if expected_label == "pro":
        assert len(result["pro_evidence"]) == 1
        assert result["counterevidence"] == []
        assert result["neutral_evidence"] == []
    elif expected_label == "counter":
        assert len(result["counterevidence"]) == 1
        assert result["pro_evidence"] == []
        assert result["neutral_evidence"] == []
    else:
        assert len(result["neutral_evidence"]) == 1
        assert result["pro_evidence"] == []
        assert result["counterevidence"] == []

    target_list = (
        result["pro_evidence"]
        if expected_label == "pro"
        else result["counterevidence"]
        if expected_label == "counter"
        else result["neutral_evidence"]
    )
    assert target_list[0]["selector_label"] == expected_label
    assert target_list[0]["expected_direction"] == expected_direction
    assert target_list[0]["selector_score"] == pytest.approx(0.8)


def test_pro_counter_neutral_mix_for_up_prediction() -> None:
    req = _base_request(
        prediction="UP",
        evidence_candidates=[
            _cand("n_pro", "UP", extractor_score=0.9),
            _cand("n_counter", "DOWN", extractor_score=0.85),
            _cand("n_neutral", "HOLD", extractor_score=0.5),
        ],
    )
    result = select_evidence(req)
    assert {e["news_id"] for e in result["pro_evidence"]} == {"n_pro"}
    assert {e["news_id"] for e in result["counterevidence"]} == {"n_counter"}
    assert {e["news_id"] for e in result["neutral_evidence"]} == {"n_neutral"}
    assert result["summary"]["has_counterevidence"] is True
    assert result["summary"]["counterevidence_ratio"] == 0.5


def test_down_prediction_pro_and_counter() -> None:
    req = _base_request(
        prediction="DOWN",
        evidence_candidates=[
            _cand("n1", "DOWN", extractor_score=0.95),
            _cand("n2", "UP", extractor_score=0.8),
        ],
    )
    result = select_evidence(req)
    assert {e["news_id"] for e in result["pro_evidence"]} == {"n1"}
    assert {e["news_id"] for e in result["counterevidence"]} == {"n2"}


def test_hold_prediction_pro_and_counter() -> None:
    req = _base_request(
        prediction="HOLD",
        evidence_candidates=[
            _cand("n1", "HOLD", extractor_score=0.7),
            _cand("n2", "UP", extractor_score=0.9),
        ],
    )
    result = select_evidence(req)
    assert {e["news_id"] for e in result["pro_evidence"]} == {"n1"}
    assert {e["news_id"] for e in result["counterevidence"]} == {"n2"}


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def test_groups_sorted_by_selector_score_descending() -> None:
    req = _base_request(
        evidence_candidates=[
            _cand("a", "UP", extractor_score=0.5),
            _cand("b", "UP", extractor_score=0.9),
            _cand("c", "UP", extractor_score=0.7),
        ],
    )
    result = select_evidence(req)
    scores = [e["selector_score"] for e in result["pro_evidence"]]
    assert scores == [0.9, 0.7, 0.5]


def test_stable_sort_on_equal_score() -> None:
    req = _base_request(
        evidence_candidates=[
            _cand("first", "UP", extractor_score=0.5),
            _cand("second", "UP", extractor_score=0.5),
            _cand("third", "UP", extractor_score=0.5),
        ],
    )
    result = select_evidence(req)
    ids = [e["news_id"] for e in result["pro_evidence"]]
    assert ids == ["first", "second", "third"]


def test_groups_sorted_independently() -> None:
    req = _base_request(
        prediction="UP",
        evidence_candidates=[
            _cand("p_low", "UP", extractor_score=0.1),
            _cand("p_high", "UP", extractor_score=0.99),
            _cand("c_low", "DOWN", extractor_score=0.2),
            _cand("c_high", "DOWN", extractor_score=0.95),
        ],
    )
    result = select_evidence(req)
    assert [e["news_id"] for e in result["pro_evidence"]] == ["p_high", "p_low"]
    assert [e["news_id"] for e in result["counterevidence"]] == ["c_high", "c_low"]


# ---------------------------------------------------------------------------
# top_k truncation
# ---------------------------------------------------------------------------


def test_top_k_truncates_per_group() -> None:
    req = _base_request(
        prediction="UP",
        evidence_candidates=[
            _cand(f"p{i}", "UP", extractor_score=1.0 - i * 0.1) for i in range(5)
        ]
        + [_cand(f"c{i}", "DOWN", extractor_score=1.0 - i * 0.1) for i in range(5)],
    )
    result = select_evidence(req, top_k_pro=2, top_k_counter=2)
    assert len(result["pro_evidence"]) == 2
    assert len(result["counterevidence"]) == 2
    # Summary counts use pre-truncation totals.
    assert result["summary"]["pro_count"] == 5
    assert result["summary"]["counter_count"] == 5


def test_top_k_default_three_per_group() -> None:
    req = _base_request(
        evidence_candidates=[
            _cand(f"p{i}", "UP", extractor_score=1.0 - i * 0.1) for i in range(5)
        ],
    )
    result = select_evidence(req)
    assert len(result["pro_evidence"]) == 3
    assert result["summary"]["pro_count"] == 5


def test_top_k_does_not_starve_other_groups() -> None:
    req = _base_request(
        prediction="UP",
        evidence_candidates=[
            _cand(f"p{i}", "UP", extractor_score=1.0 - i * 0.1) for i in range(5)
        ]
        + [_cand("c1", "DOWN", extractor_score=0.9)],
    )
    result = select_evidence(req, top_k_pro=2, top_k_counter=10)
    assert len(result["pro_evidence"]) == 2
    assert len(result["counterevidence"]) == 1


# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------


def test_summary_counterevidence_ratio_three_to_one() -> None:
    req = _base_request(
        prediction="UP",
        evidence_candidates=[
            _cand("p1", "UP", extractor_score=0.9),
            _cand("p2", "UP", extractor_score=0.8),
            _cand("p3", "UP", extractor_score=0.7),
            _cand("c1", "DOWN", extractor_score=0.85),
        ],
    )
    result = select_evidence(req)
    assert result["summary"]["counterevidence_ratio"] == pytest.approx(0.25)


def test_summary_counterevidence_ratio_zero_when_no_pro_or_counter() -> None:
    req = _base_request(
        evidence_candidates=[_cand("n1", "HOLD", extractor_score=0.5)],
    )
    result = select_evidence(req)
    assert result["summary"]["counterevidence_ratio"] == 0.0


def test_summary_has_counterevidence_true_when_present() -> None:
    req = _base_request(
        evidence_candidates=[
            _cand("p1", "UP"),
            _cand("c1", "DOWN"),
        ],
    )
    result = select_evidence(req)
    assert result["summary"]["has_counterevidence"] is True


def test_summary_has_counterevidence_false_when_absent() -> None:
    req = _base_request(
        evidence_candidates=[_cand("p1", "UP"), _cand("p2", "UP")],
    )
    result = select_evidence(req)
    assert result["summary"]["has_counterevidence"] is False


def test_summary_counts_are_pre_truncation() -> None:
    req = _base_request(
        prediction="UP",
        evidence_candidates=[
            _cand(f"c{i}", "DOWN", extractor_score=1.0 - i * 0.05) for i in range(10)
        ],
    )
    result = select_evidence(req, top_k_counter=3)
    assert result["summary"]["counter_count"] == 10
    assert len(result["counterevidence"]) == 3


# ---------------------------------------------------------------------------
# Future-evidence flagging
# ---------------------------------------------------------------------------


def test_future_candidate_is_flagged_not_classified() -> None:
    req = _base_request(
        evidence_candidates=[
            _cand("past", "UP", extractor_score=0.9, news_time="2025-03-11 08:00"),
            _cand("future", "DOWN", extractor_score=0.99, news_time="2025-03-13 10:00"),
        ],
    )
    result = select_evidence(req)
    assert {e["news_id"] for e in result["pro_evidence"]} == {"past"}
    assert result["counterevidence"] == []
    assert len(result["invalid_future_evidence"]) == 1
    future_entry = result["invalid_future_evidence"][0]
    assert future_entry["news_id"] == "future"
    assert future_entry["news_time"] == "2025-03-13 10:00"
    assert future_entry["reason"] == "future_evidence"
    # The future item must not contribute to summary counts.
    assert result["summary"]["counter_count"] == 0
    assert result["summary"]["has_counterevidence"] is False


def test_equal_timestamp_is_not_future() -> None:
    req = _base_request(
        evidence_candidates=[
            _cand("equal", "UP", news_time="2025-03-12 09:00"),
        ],
    )
    result = select_evidence(req)
    assert result["invalid_future_evidence"] == []
    assert len(result["pro_evidence"]) == 1


def test_missing_news_time_is_treated_as_not_future() -> None:
    req = _base_request(
        evidence_candidates=[
            _cand("n1", "UP", news_time=None),
            _cand("n2", "DOWN", news_time="not-a-date"),
        ],
    )
    result = select_evidence(req)
    assert result["invalid_future_evidence"] == []
    assert len(result["pro_evidence"]) == 1
    assert len(result["counterevidence"]) == 1


# ---------------------------------------------------------------------------
# One bad candidate does not abort the batch
# ---------------------------------------------------------------------------


def test_one_bad_candidate_does_not_abort_batch() -> None:
    req = _base_request(
        evidence_candidates=[
            _cand("good1", "UP"),
            {"news_id": "bad", "ticker": "AAPL", "news_time": "2025-03-11 08:00",
             "evidence_text": "no direction", "polarity": "positive",
             "extractor_score": 0.7},  # missing expected_direction
            _cand("good2", "DOWN"),
        ],
    )
    result = select_evidence(req)
    assert {e["news_id"] for e in result["pro_evidence"]} == {"good1"}
    assert {e["news_id"] for e in result["counterevidence"]} == {"good2"}
    assert "invalid_candidates" in result
    assert any(c["news_id"] == "bad" for c in result["invalid_candidates"])


def test_unknown_expected_direction_is_reported_as_invalid() -> None:
    req = _base_request(
        evidence_candidates=[
            _cand("good", "UP"),
            _cand("bad", "MAYBE"),  # unknown direction
        ],
    )
    result = select_evidence(req)
    assert len(result["pro_evidence"]) == 1
    assert any(c["news_id"] == "bad" for c in result["invalid_candidates"])


# ---------------------------------------------------------------------------
# Field preservation
# ---------------------------------------------------------------------------


def test_each_output_item_preserves_input_fields_and_adds_selector_fields() -> None:
    req = _base_request(
        evidence_candidates=[_cand("n1", "UP", extractor_score=0.9)],
    )
    result = select_evidence(req)
    item = result["pro_evidence"][0]
    assert item["news_id"] == "n1"
    assert item["ticker"] == "AAPL"
    assert item["news_time"] == "2025-03-11 08:00"
    assert item["evidence_text"] == "text for n1"
    assert item["polarity"] == "positive"
    assert item["expected_direction"] == "UP"
    assert item["extractor_score"] == 0.9
    assert item["selector_label"] == "pro"
    assert item["selector_score"] == 0.9
    assert "reason" in item


def test_metadata_echoed_verbatim() -> None:
    req = _base_request(
        ticker="MSFT",
        forecast_time="2025-04-02 09:00",
        prediction="DOWN",
        confidence=0.7,
        evidence_candidates=[_cand("n1", "DOWN")],
    )
    result = select_evidence(req)
    assert result["ticker"] == "MSFT"
    assert result["forecast_time"] == "2025-04-02 09:00"
    assert result["prediction"] == "DOWN"
    assert result["confidence"] == 0.7


# ---------------------------------------------------------------------------
# Label-leakage protection
# ---------------------------------------------------------------------------


def test_extra_ground_truth_label_is_ignored() -> None:
    """A candidate carrying a ground_truth_label must be classified
    purely on expected_direction, and the output must NOT echo the
    ground_truth_label."""
    cand = _cand("n1", "UP", extractor_score=0.9)
    cand["ground_truth_label"] = "DOWN"  # attempt to leak
    req = _base_request(evidence_candidates=[cand])
    result = select_evidence(req)
    # Classified as pro (because expected_direction == UP matches prediction UP),
    # NOT as counter (which is what ground_truth_label would have implied).
    assert len(result["pro_evidence"]) == 1
    assert len(result["counterevidence"]) == 0
    item = result["pro_evidence"][0]
    assert "ground_truth_label" not in item
    assert "label" not in item


def test_extra_actual_field_is_ignored() -> None:
    cand = _cand("n1", "UP", extractor_score=0.9)
    cand["actual"] = "DOWN"
    req = _base_request(evidence_candidates=[cand])
    result = select_evidence(req)
    assert result["pro_evidence"][0]["expected_direction"] == "UP"
    assert "actual" not in result["pro_evidence"][0]


# ---------------------------------------------------------------------------
# Empty groups are lists, not null
# ---------------------------------------------------------------------------


def test_empty_groups_are_returned_as_empty_lists() -> None:
    """When a request has no candidates of a given kind, the matching
    output list MUST be an empty list, never null/None."""
    # No counter, neutral, or future candidates → those lists must be [].
    req = _base_request(evidence_candidates=[_cand("n1", "UP")])
    result = select_evidence(req)
    assert result["pro_evidence"] != []  # sanity: pro list is non-empty
    assert result["counterevidence"] == []
    assert result["neutral_evidence"] == []
    assert result["invalid_future_evidence"] == []

    # No candidates at all → every list must be [].
    empty = select_evidence(_base_request())
    assert empty["pro_evidence"] == []
    assert empty["counterevidence"] == []
    assert empty["neutral_evidence"] == []
    assert empty["invalid_future_evidence"] == []


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_identical_requests_produce_identical_results() -> None:
    req = _base_request(
        evidence_candidates=[
            _cand("p1", "UP", extractor_score=0.9),
            _cand("p2", "UP", extractor_score=0.5),
            _cand("c1", "DOWN", extractor_score=0.85),
        ],
    )
    r1 = select_evidence(req)
    r2 = select_evidence(req)
    assert r1 == r2


# ---------------------------------------------------------------------------
# Batch API
# ---------------------------------------------------------------------------


def test_batch_returns_one_result_per_input_in_order() -> None:
    reqs = [
        _base_request(
            ticker="AAPL",
            evidence_candidates=[_cand("a1", "UP")],
        ),
        _base_request(
            ticker="MSFT",
            prediction="DOWN",
            evidence_candidates=[_cand("m1", "DOWN")],
        ),
        _base_request(
            ticker="GOOGL",
            prediction="HOLD",
            evidence_candidates=[_cand("g1", "HOLD")],
        ),
    ]
    results = select_evidence_batch(reqs)
    assert len(results) == 3
    assert [r["ticker"] for r in results] == ["AAPL", "MSFT", "GOOGL"]
    assert [r["prediction"] for r in results] == ["UP", "DOWN", "HOLD"]


# ---------------------------------------------------------------------------
# Coverage helper
# ---------------------------------------------------------------------------


def test_compute_coverage_full() -> None:
    result = select_evidence(_base_request(
        prediction="UP",
        evidence_candidates=[
            _cand("p1", "UP"),
            _cand("c1", "DOWN"),
            _cand("c2", "DOWN"),
        ],
    ))
    cov = compute_coverage(result, {"p1": "pro", "c1": "counter", "c2": "counter"})
    assert cov["available_counterevidence_count"] == 2
    assert cov["detected_counterevidence_count"] == 2
    assert cov["counterevidence_coverage"] == 1.0
    assert cov["counterevidence_detected_rate"] == 1.0


def test_compute_coverage_partial() -> None:
    result = select_evidence(_base_request(
        prediction="UP",
        evidence_candidates=[
            _cand("p1", "UP"),
            _cand("c1", "DOWN"),  # detected
        ],
    ))
    cov = compute_coverage(result, {"p1": "pro", "c1": "counter", "c2": "counter"})
    assert cov["available_counterevidence_count"] == 2
    assert cov["detected_counterevidence_count"] == 1
    assert cov["counterevidence_coverage"] == 0.5


def test_compute_coverage_zero_when_no_annotation() -> None:
    result = select_evidence(_base_request())
    cov = compute_coverage(result, {})
    assert cov["available_counterevidence_count"] == 0
    assert cov["detected_counterevidence_count"] == 0
    assert cov["counterevidence_coverage"] == 0.0
    assert cov["counterevidence_detected_rate"] == 0.0


def test_compute_coverage_never_reads_label_from_candidate() -> None:
    """compute_coverage must derive everything from the caller's
    expected_labels dict, never from candidate fields."""
    cand = _cand("c1", "DOWN")
    cand["ground_truth_label"] = "counter"  # would-be leak
    result = select_evidence(_base_request(evidence_candidates=[cand]))
    # Caller's expected_labels says no counter; coverage should be 0
    # even though the candidate carries a ground_truth_label.
    cov = compute_coverage(result, {"c1": "pro"})
    assert cov["available_counterevidence_count"] == 0
    assert cov["detected_counterevidence_count"] == 0
    assert cov["counterevidence_coverage"] == 0.0


# ---------------------------------------------------------------------------
# Golden fixtures under samples/evidence_selector/
# ---------------------------------------------------------------------------


SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples" / "evidence_selector"


@pytest.mark.parametrize(
    "fixture_stem",
    [
        "01_up_with_counter",
        "02_down",
        "03_hold",
    ],
)
def test_golden_fixture_matches_selector_output(fixture_stem: str) -> None:
    """Every documented example under samples/evidence_selector/ must
    produce the saved expected result byte-for-byte."""
    inp_path = SAMPLES_DIR / f"{fixture_stem}_input.json"
    exp_path = SAMPLES_DIR / f"{fixture_stem}_expected.json"
    req = json.loads(inp_path.read_text())
    expected = json.loads(exp_path.read_text())
    actual = select_evidence(req)
    assert actual == expected, (
        f"Golden fixture {fixture_stem} drifted. "
        f"Inspect by re-running select_evidence(json.loads(open('{inp_path}').read()))."
    )
