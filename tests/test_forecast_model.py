"""Unit tests for the Forecast Model (Version 3 — attention_evidence_v1).

The fixture checkpoint under ``models/evidence_aggregator_v1.pt`` is the
random-init weights produced by ``python3 -c "from src.stages.
forecast_model import AttentionEvidenceAggregator; import torch;
torch.manual_seed(42); torch.save(AttentionEvidenceAggregator().state_dict(),
'models/evidence_aggregator_v1.pt')"``. After training on Colab, the
checkpoint is regenerated; tests must remain deterministic against
whichever checkpoint is checked in (they only assert SHAPE and
REPRODUCIBILITY properties, not specific numerics).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src.stages.forecast_model import (
    AttentionEvidenceAggregator,
    ForecastModel,
    ForecastModelError,
)

_model = ForecastModel()
CSV_COLUMNS = ForecastModel.CSV_COLUMNS
CSV_DEFAULT_PATH = ForecastModel.CSV_DEFAULT_PATH
JSON_DEFAULT_PATH = ForecastModel.JSON_DEFAULT_PATH
MODEL_VERSION = ForecastModel.MODEL_VERSION
REQUIRED_INPUT_FIELDS = ForecastModel.REQUIRED_INPUT_FIELDS
VALID_DIRECTIONS = ForecastModel.VALID_DIRECTIONS
VALID_PREDICTIONS = ForecastModel.VALID_PREDICTIONS
WARNING_CODES = ForecastModel.WARNING_CODES
_deduplicate = _model._deduplicate
_filter_temporal = _model._filter_temporal
_parse_news_time = _model._parse_news_time
_partition_evidence = _model._partition_evidence
_build_pro_and_counter = _model._build_pro_and_counter
_build_rationale = _model._build_rationale
_argmax_with_tiebreak = _model._argmax_with_tiebreak
compute_accuracy_and_confusion = _model.compute_accuracy_and_confusion
predict = _model.predict
predict_batch = _model.predict_batch
predict_without_evidence = _model.predict_without_evidence


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _evidence(eid: str, direction: str, news_time: str = "2025-03-11 08:30", **extra):
    pos_p, neg_p, neu_p = (
        (0.95, 0.02, 0.03) if direction == "UP"
        else (0.05, 0.90, 0.05) if direction == "DOWN"
        else (0.05, 0.05, 0.90)
    )
    base = {
        "evidence_id": eid,
        "news_id": eid.split("_E")[0],
        "news_time": news_time,
        "evidence_text": f"phrase for {eid}",
        "polarity": "positive" if direction == "UP" else "negative" if direction == "DOWN" else "neutral",
        "expected_direction": direction,
        "support_score": pos_p if direction == "UP" else neg_p if direction == "DOWN" else neu_p,
        "sentiment_probs": {"positive": pos_p, "negative": neg_p, "neutral": neu_p},
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
        "price_5d_return": 0.02,
        "volume_change": -0.05,
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
def empty_input() -> dict:
    return {
        "sample_id": "S0003",
        "ticker": "AMZN",
        "forecast_time": "2025-05-01 09:00",
        "label": "HOLD",
        "evidence": [],
    }


@pytest.fixture
def future_evidence_input() -> dict:
    return {
        "sample_id": "S0004",
        "ticker": "TSLA",
        "forecast_time": "2025-03-12 09:00",
        "label": "UP",
        "evidence": [
            _evidence("N020_E001", "UP", news_time="2025-03-11 08:30"),
            _evidence("N021_E001", "UP", news_time="2025-03-11 09:30"),
            _evidence("N022_E001", "UP", news_time="2025-03-12 15:30"),
        ],
    }


# ---------------------------------------------------------------------------
# Constants — public schema contract
# ---------------------------------------------------------------------------


def test_required_input_fields_match_spec() -> None:
    assert REQUIRED_INPUT_FIELDS == ("sample_id", "ticker", "forecast_time", "evidence")


def test_valid_predictions_and_directions_are_canonical() -> None:
    assert VALID_PREDICTIONS == ("UP", "DOWN", "HOLD")
    assert VALID_DIRECTIONS == ("UP", "DOWN", "HOLD")


def test_model_version_is_attention_evidence_v1() -> None:
    assert MODEL_VERSION == "attention_evidence_v1"


def test_csv_columns_match_v1_schema() -> None:
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
        "label",
        "model_version",
    )


def test_default_paths_are_outputs() -> None:
    assert CSV_DEFAULT_PATH == "outputs/prediction_results.csv"
    assert JSON_DEFAULT_PATH == "outputs/prediction_results.json"


def test_warning_codes_set() -> None:
    assert set(WARNING_CODES) == {
        "TEMPORAL_LEAKAGE_BLOCKED",
        "INVALID_EVIDENCE",
        "DUPLICATE_EVIDENCE_ID",
        "MALFORMED_NEWS_TIME",
        "INPUT_ERROR",
        "MISSING_SENTIMENT_PROBS",
    }


# ---------------------------------------------------------------------------
# AttentionEvidenceAggregator — direct tests
# ---------------------------------------------------------------------------


def test_attention_aggregator_forward_on_empty_evidence_returns_3_probs() -> None:
    import torch

    m = AttentionEvidenceAggregator()
    m.eval()
    ef = torch.zeros((0, 7))
    pf = torch.zeros(2)
    with torch.no_grad():
        probs = m(ef, pf)
    assert probs.shape == (3,)
    assert float(probs.sum()) == pytest.approx(1.0, abs=1e-6)
    assert all(float(p) >= 0.0 for p in probs)


def test_attention_aggregator_forward_on_nonempty_evidence() -> None:
    import torch

    m = AttentionEvidenceAggregator()
    m.eval()
    ef = torch.tensor(
        [
            [0.90, 0.05, 0.05, 0.90, 1.0, 0.0, 0.0],
            [0.10, 0.85, 0.05, 0.85, 0.0, 1.0, 0.0],
            [0.05, 0.05, 0.90, 0.50, 0.0, 0.0, 1.0],
        ],
        dtype=torch.float32,
    )
    pf = torch.tensor([0.02, -0.01], dtype=torch.float32)
    with torch.no_grad():
        probs = m(ef, pf)
    assert probs.shape == (3,)
    assert float(probs.sum()) == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# ForecastModel — public API
# ---------------------------------------------------------------------------


def test_load_real_checkpoint_succeeds(tmp_path: Path) -> None:
    """The committed checkpoint at the default path must be loadable."""
    model = ForecastModel()
    assert hasattr(model, "model")
    assert model.checkpoint_path.endswith("evidence_aggregator_v1.pt")


def test_load_missing_checkpoint_raises_friendly_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "src.stages.forecast_model.DEFAULT_CHECKPOINT_PATH",
        str(tmp_path / "does-not-exist.pt"),
    )
    # Re-import to pick up the patched constant — easier to just patch
    # via env var instead.
    import os
    os.environ["FORECAST_CHECKPOINT"] = str(tmp_path / "does-not-exist.pt")
    try:
        with pytest.raises(ForecastModelError) as excinfo:
            ForecastModel()
        assert "checkpoint" in str(excinfo.value).lower()
    finally:
        os.environ.pop("FORECAST_CHECKPOINT", None)


# ---------------------------------------------------------------------------
# predict() — output schema
# ---------------------------------------------------------------------------


def test_predict_returns_valid_label_and_confidence(up_input: dict) -> None:
    result = predict(up_input)
    assert result["prediction"] in VALID_PREDICTIONS
    assert 0.0 < result["confidence"] <= 1.0
    assert result["class_confidences"][result["prediction"]] == pytest.approx(
        result["confidence"], abs=1e-6
    )
    assert sum(result["class_confidences"].values()) == pytest.approx(1.0, abs=1e-6)


def test_predict_counts_match_input(up_input: dict) -> None:
    result = predict(up_input)
    assert result["positive_count"] == 3
    assert result["negative_count"] == 1
    assert result["directional_evidence_count"] == 4
    assert result["total_evidence"] == 4


def test_predict_with_empty_evidence_is_well_formed(empty_input: dict) -> None:
    result = predict(empty_input)
    assert result["prediction"] in VALID_PREDICTIONS
    assert sum(result["class_confidences"].values()) == pytest.approx(1.0, abs=1e-6)
    assert result["pro_evidence"] == []
    assert result["counter_evidence"] == []
    assert result["total_evidence"] == 0


def test_predict_block_future_evidence(future_evidence_input: dict) -> None:
    result = predict(future_evidence_input)
    future_warnings = [w for w in result["warnings"] if w["code"] == "TEMPORAL_LEAKAGE_BLOCKED"]
    assert len(future_warnings) == 1
    assert future_warnings[0]["evidence_id"] == "N022_E001"


def test_predict_model_version_constant(up_input: dict) -> None:
    result = predict(up_input)
    assert result["model_version"] == "attention_evidence_v1"


def test_predict_rationale_is_template(up_input: dict) -> None:
    result = predict(up_input)
    assert result["rationale"].startswith("Attention model:")


# ---------------------------------------------------------------------------
# Determinism (seed-reproducible within tolerance)
# ---------------------------------------------------------------------------


def test_predict_is_seed_reproducible(up_input: dict) -> None:
    a = predict(up_input)
    b = predict(up_input)
    assert a["prediction"] == b["prediction"]
    assert a["confidence"] == pytest.approx(b["confidence"], abs=1e-6)
    for label in VALID_PREDICTIONS:
        assert a["class_confidences"][label] == pytest.approx(
            b["class_confidences"][label], abs=1e-6
        )
    assert a["positive_count"] == b["positive_count"]
    assert a["negative_count"] == b["negative_count"]
    assert a["total_evidence"] == b["total_evidence"]


def test_predict_without_evidence_empty_matches_predict(up_input: dict) -> None:
    a = predict(up_input)
    b = predict_without_evidence(up_input, [])
    assert a == b


def test_predict_without_evidence_none_matches_predict(up_input: dict) -> None:
    a = predict(up_input)
    b = predict_without_evidence(up_input, None)
    assert a == b


def test_predict_without_evidence_unknown_ids_matches_predict(up_input: dict) -> None:
    a = predict(up_input)
    b = predict_without_evidence(up_input, ["UNKNOWN_E001"])
    assert a == b


def test_predict_without_evidence_changes_output(up_input: dict) -> None:
    a = predict(up_input)
    # Pick the three UP evidence IDs deterministically — regardless of
    # the model's prediction, removing them MUST change the input shape.
    pro_ids = [
        e["evidence_id"]
        for e in up_input["evidence"]
        if e["expected_direction"] == "UP"
    ]
    assert len(pro_ids) >= 2
    b = predict_without_evidence(up_input, pro_ids)
    assert b["prediction"] in VALID_PREDICTIONS
    # The result dicts must differ in either counts or class probs because
    # the evidence tensor that fed the model has shrunk.
    assert a != b


# ---------------------------------------------------------------------------
# Defensive helpers — kept stable from V1
# ---------------------------------------------------------------------------


def test_parse_news_time_handles_invalid_and_valid() -> None:
    assert _parse_news_time(None) is None
    assert _parse_news_time("") is None
    assert _parse_news_time("not-a-date") is None
    parsed = _parse_news_time("2025-03-12T09:00:00")
    assert parsed is not None
    assert parsed.strftime("%Y-%m-%d %H:%M:%S") == "2025-03-12 09:00:00"


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
    out = _filter_temporal(
        items, _parse_news_time("2025-03-12 09:00"), warnings
    )
    assert out == []
    assert any(w["code"] == "TEMPORAL_LEAKAGE_BLOCKED" for w in warnings)


def test_filter_temporal_keeps_equal_timestamp() -> None:
    items = [_evidence("N001_E001", "UP", news_time="2025-03-12 09:00")]
    warnings: list[dict] = []
    out = _filter_temporal(
        items, _parse_news_time("2025-03-12 09:00"), warnings
    )
    assert len(out) == 1
    assert not any(w["code"] == "TEMPORAL_LEAKAGE_BLOCKED" for w in warnings)


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


def test_build_pro_and_counter_branches() -> None:
    pro, counter = _build_pro_and_counter(
        "UP",
        [{"evidence_id": "u1"}, {"evidence_id": "u2"}],
        [{"evidence_id": "d1"}],
    )
    assert [e["evidence_id"] for e in pro] == ["u1", "u2"]
    assert [e["evidence_id"] for e in counter] == ["d1"]

    pro, counter = _build_pro_and_counter(
        "HOLD",
        [{"evidence_id": "u1"}, {"evidence_id": "u2"}],
        [{"evidence_id": "d1"}],
    )
    assert pro == [] and counter == []


def test_argmax_with_tiebreak_picks_up_then_down_then_hold() -> None:
    probs = {"UP": 0.4, "DOWN": 0.4, "HOLD": 0.2}
    label, conf = _argmax_with_tiebreak(probs)
    assert label == "UP"
    probs = {"UP": 0.2, "DOWN": 0.4, "HOLD": 0.4}
    label, _ = _argmax_with_tiebreak(probs)
    assert label == "DOWN"
    probs = {"UP": 0.2, "DOWN": 0.2, "HOLD": 0.6}
    label, _ = _argmax_with_tiebreak(probs)
    assert label == "HOLD"


# ---------------------------------------------------------------------------
# Request-envelope validation
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


def test_strict_mode_raises_on_invalid_expected_direction(up_input: dict) -> None:
    up_input["evidence"].append(_evidence("N099_E001", "INVALID"))
    with pytest.raises(ForecastModelError):
        predict(up_input, strict=True)


# ---------------------------------------------------------------------------
# Batch API
# ---------------------------------------------------------------------------


def test_batch_returns_one_result_per_record_in_order(
    up_input: dict, down_input: dict, empty_input: dict
) -> None:
    results = predict_batch(
        [up_input, down_input, empty_input],
        output_csv_path=None,
        output_json_path=None,
    )
    assert len(results) == 3
    for r in results:
        assert r["prediction"] in VALID_PREDICTIONS
        assert json.dumps(r)  # serializable


def test_batch_writes_csv_with_correct_header(tmp_path: Path) -> None:
    csv_path = tmp_path / "out.csv"
    predict_batch(
        [
            {
                "sample_id": "S0001",
                "ticker": "AAPL",
                "forecast_time": "2025-03-12 09:00",
                "label": "UP",
                "evidence": [
                    _evidence("N001_E001", "UP"),
                    _evidence("N002_E001", "UP"),
                    _evidence("N003_E001", "UP"),
                ],
            }
        ],
        output_csv_path=str(csv_path),
        output_json_path=None,
    )
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0].keys()) == list(CSV_COLUMNS)
    assert len(rows) == 1
    assert rows[0]["model_version"] == MODEL_VERSION


def test_batch_input_error_yields_default_hold() -> None:
    bad = {"sample_id": "S999", "ticker": "AAPL"}
    results = predict_batch(
        [bad], output_csv_path=None, output_json_path=None
    )
    assert len(results) == 1
    assert results[0]["prediction"] == "HOLD"
    assert results[0]["confidence"] == 0.5
    assert any(w["code"] == "INPUT_ERROR" for w in results[0]["warnings"])


def test_compute_accuracy_and_confusion_small_fixture() -> None:
    base = {
        "sample_id": "S1",
        "ticker": "AAPL",
        "forecast_time": "2025-03-12 09:00",
        "evidence": [_evidence("N001_E001", "UP")],
    }
    def _rec(i: int, label: str, direction: str) -> dict:
        return {
            **base,
            "label": label,
            "evidence": [_evidence(f"N{i:03}_E001", direction)],
        }

    records = [
        _rec(1, "UP", "UP"),
        _rec(2, "UP", "UP"),
        _rec(3, "DOWN", "UP"),
        _rec(4, "UP", "DOWN"),
        _rec(5, "HOLD", "HOLD"),
        _rec(6, "DOWN", "DOWN"),
    ]
    results = predict_batch(records, output_csv_path=None, output_json_path=None)
    metrics = compute_accuracy_and_confusion(results)
    assert metrics["n_samples"] == 6
    expected_correct = sum(
        1 for r, rec in zip(results, records) if r["prediction"] == rec["label"]
    )
    assert metrics["accuracy"] == pytest.approx(expected_correct / 6)
    matrix = metrics["confusion_matrix"]["matrix"]
    assert len(matrix) == 3 and all(len(row) == 3 for row in matrix)
    for label in ("UP", "DOWN", "HOLD"):
        for key in ("precision", "recall", "f1", "support"):
            assert key in metrics["per_class"][label]


def test_compute_accuracy_and_confusion_empty_input() -> None:
    metrics = compute_accuracy_and_confusion([])
    assert metrics["n_samples"] == 0
    assert metrics["accuracy"] == 0.0


# ---------------------------------------------------------------------------
# Module integration (no circular imports)
# ---------------------------------------------------------------------------


def test_module_does_not_import_extractor_or_selector() -> None:
    """Forecast Model must read `sentiment_probs` from upstream but not re-import the extractor."""
    import importlib
    from src.stages import forecast_model

    importlib.reload(forecast_model)
    src_text = Path(forecast_model.__file__).read_text()
    assert "from src.stages.evidence_extractor" not in src_text
    assert "from src.stages.evidence_selector" not in src_text
    assert "import src.stages.evidence_extractor" not in src_text
    assert "import src.stages.evidence_selector" not in src_text
