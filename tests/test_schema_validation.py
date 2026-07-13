"""Unit tests for schema.validate_sample and stage_io envelope loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.schema import REQUIRED_SAMPLE_KEYS, validate_sample
from src.core.stage_io import EnvelopeError, dump_envelope, load_envelope


def _base_sample() -> dict:
    return {
        "sample_id": "AAPL_2025-03-12_0900",
        "ticker": "AAPL",
        "forecast_time": "2025-03-12 09:00",
        "news": [],
    }


# ---------------------------------------------------------------------------
# validate_sample
# ---------------------------------------------------------------------------


def test_valid_base_sample_passes_retriever() -> None:
    assert validate_sample(_base_sample(), "retriever") == []


def test_missing_key_reports_sample_id_and_key() -> None:
    sample = _base_sample()
    del sample["news"]
    errors = validate_sample(sample, "retriever")
    assert len(errors) == 1
    assert "AAPL_2025-03-12_0900" in errors[0]
    assert "'news'" in errors[0]


def test_wrong_type_reports_expected_and_actual() -> None:
    sample = _base_sample()
    sample["news"] = "not a list"
    errors = validate_sample(sample, "retriever")
    assert len(errors) == 1
    assert "must be list" in errors[0]
    assert "got str" in errors[0]


def test_non_dict_sample_is_single_error() -> None:
    errors = validate_sample("not a dict", "retriever")
    assert len(errors) == 1
    assert "not a dict" in errors[0]


def test_unknown_stage_raises() -> None:
    with pytest.raises(ValueError):
        validate_sample(_base_sample(), "bogus_stage")


def test_requirements_are_cumulative_along_the_chain() -> None:
    """Each stage requires at least everything the previous stage required."""
    chain = [
        "retriever",
        "evidence_extractor",
        "forecast_model",
        "evidence_selector",
        "faithfulness_evaluator",
        "sufficiency_evaluator",
        "market_analyzer",
        "export_csv",
    ]
    for earlier, later in zip(chain, chain[1:]):
        earlier_keys = set(REQUIRED_SAMPLE_KEYS[earlier])
        later_keys = set(REQUIRED_SAMPLE_KEYS[later])
        assert earlier_keys <= later_keys, f"{later} lost keys from {earlier}"


def test_faithfulness_stage_requires_forecast() -> None:
    sample = _base_sample()
    sample.update(
        {"valid_news": [], "invalid_future_news": [], "evidence": []}
    )
    errors = validate_sample(sample, "evidence_selector")
    assert any("'forecast'" in e for e in errors)


# ---------------------------------------------------------------------------
# stage_io: load_envelope / dump_envelope
# ---------------------------------------------------------------------------


def test_load_envelope_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(EnvelopeError, match="not found"):
        load_envelope(str(tmp_path / "nope.json"), stage="retriever")


def test_load_envelope_bad_json_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("NOT JSON", encoding="utf-8")
    with pytest.raises(EnvelopeError, match="not valid JSON"):
        load_envelope(str(p), stage="retriever")


def test_load_envelope_wrong_shape_raises(tmp_path: Path) -> None:
    p = tmp_path / "shape.json"
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(EnvelopeError, match="samples"):
        load_envelope(str(p), stage="retriever")


def test_load_envelope_invalid_sample_lists_errors(tmp_path: Path) -> None:
    p = tmp_path / "env.json"
    p.write_text(
        json.dumps({"stage": "ingest", "samples": [{"sample_id": "S1"}]}),
        encoding="utf-8",
    )
    with pytest.raises(EnvelopeError, match="'ticker'"):
        load_envelope(str(p), stage="retriever")


def test_load_envelope_valid_roundtrip(tmp_path: Path) -> None:
    env = {"stage": "ingest", "samples": [_base_sample()]}
    p = tmp_path / "env.json"
    dump_envelope(env, str(p))
    loaded = load_envelope(str(p), stage="retriever")
    assert loaded == env


def test_dump_envelope_is_deterministic(tmp_path: Path) -> None:
    env = {"stage": "ingest", "samples": [_base_sample()]}
    p1, p2 = tmp_path / "a.json", tmp_path / "b.json"
    dump_envelope(env, str(p1))
    dump_envelope(env, str(p2))
    assert p1.read_bytes() == p2.read_bytes()
    assert p1.read_bytes().endswith(b"\n")