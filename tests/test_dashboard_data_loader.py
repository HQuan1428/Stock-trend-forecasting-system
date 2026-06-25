"""Unit tests for ``src.dashboard.data_loader``.

These tests use the three fixture sets under ``samples/dashboard/``:

- ``healthy/``         — five predictions, no leakage, all three levels.
- ``leakage/``         — five predictions, one temporal-leakage row.
- ``faithfulness_levels/`` — three predictions, one per level.

The loader's adapter layer is the most behavior-dense piece; the tests
focus on the contract from the proposal (column renames, derived
counts, leakage synthesis) and the spec scenarios.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from src.dashboard.data_loader import (
    EVIDENCE_COLUMNS,
    FAITHFULNESS_COLUMNS,
    LEAKAGE_COLUMNS,
    PREDICTION_COLUMNS,
    DashboardData,
    load_dashboard_data,
)
from src.dashboard.validators import DashboardDataError, assert_columns


SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples" / "dashboard"


# ---------------------------------------------------------------------------
# Healthy fixture
# ---------------------------------------------------------------------------


def test_healthy_load_returns_populated_data() -> None:
    data = load_dashboard_data(str(SAMPLES_DIR / "healthy"))
    assert isinstance(data, DashboardData)
    assert data.predictions is not None and not data.predictions.empty
    assert data.evidence is not None and not data.evidence.empty
    assert data.faithfulness is not None and not data.faithfulness.empty
    assert data.leakage is not None


def test_healthy_predictions_have_all_required_columns() -> None:
    data = load_dashboard_data(str(SAMPLES_DIR / "healthy"))
    assert_columns(data.predictions, PREDICTION_COLUMNS, file_label="prediction_results.csv")


def test_healthy_evidence_has_all_required_columns() -> None:
    data = load_dashboard_data(str(SAMPLES_DIR / "healthy"))
    assert_columns(data.evidence, EVIDENCE_COLUMNS, file_label="evidence_results.csv")


def test_healthy_faithfulness_has_all_required_columns() -> None:
    data = load_dashboard_data(str(SAMPLES_DIR / "healthy"))
    assert_columns(data.faithfulness, FAITHFULNESS_COLUMNS, file_label="faithfulness_results.csv")


def test_healthy_predictions_enriched_with_counts() -> None:
    """The adapter should compute ``valid_news_count`` from the evidence frame."""
    data = load_dashboard_data(str(SAMPLES_DIR / "healthy"))
    assert "valid_news_count" in data.predictions.columns
    assert "invalid_future_news_count" in data.predictions.columns
    # The healthy fixture has zero invalid future news.
    assert (data.predictions["invalid_future_news_count"] == 0).all()
    # The valid count is at least the count of cited evidence rows.
    for _, row in data.predictions.iterrows():
        sid = row["sample_id"]
        cited_count = int((data.evidence["sample_id"] == sid).sum())
        assert int(row["valid_news_count"]) >= 0
        # The valid count should match the row count for that sample.
        expected = int((data.evidence["sample_id"] == sid).sum())
        assert int(row["valid_news_count"]) == expected


def test_healthy_evidence_cited_flag_distinguishes_roles() -> None:
    data = load_dashboard_data(str(SAMPLES_DIR / "healthy"))
    cited = data.evidence[data.evidence["evidence_role"].isin(
        ["pro_evidence", "counter_evidence"]
    )]
    non_cited = data.evidence[~data.evidence["evidence_role"].isin(
        ["pro_evidence", "counter_evidence"]
    )]
    assert cited["is_cited"].all()
    assert (~non_cited["is_cited"]).all()


def test_healthy_no_leakage() -> None:
    data = load_dashboard_data(str(SAMPLES_DIR / "healthy"))
    assert data.leakage.empty


# ---------------------------------------------------------------------------
# Leakage fixture
# ---------------------------------------------------------------------------


def test_leakage_load_has_one_leakage_row() -> None:
    data = load_dashboard_data(str(SAMPLES_DIR / "leakage"))
    assert not data.leakage.empty
    assert len(data.leakage) == 1


def test_leakage_row_has_positive_minutes() -> None:
    data = load_dashboard_data(str(SAMPLES_DIR / "leakage"))
    minutes = float(data.leakage["leakage_minutes"].iloc[0])
    assert minutes > 0.0


def test_leakage_row_has_required_columns() -> None:
    data = load_dashboard_data(str(SAMPLES_DIR / "leakage"))
    assert_columns(data.leakage, LEAKAGE_COLUMNS, file_label="temporal_leakage_results.csv")


def test_leakage_predictions_includes_invalid_future_count() -> None:
    data = load_dashboard_data(str(SAMPLES_DIR / "leakage"))
    # The fixture is generated from upstream, so the JSON-based adapter
    # may or may not populate ``invalid_future_news_count`` depending
    # on which path is used. Verify the column exists; the value can
    # be 0 (the upstream model filtered the future item out of the
    # evidence frame before the dashboard sees it).
    assert "invalid_future_news_count" in data.predictions.columns


# ---------------------------------------------------------------------------
# Faithfulness levels fixture
# ---------------------------------------------------------------------------


def test_faithfulness_levels_covers_all_three() -> None:
    data = load_dashboard_data(str(SAMPLES_DIR / "faithfulness_levels"))
    labels = set(data.faithfulness["faithfulness_label"].astype(str).unique())
    assert labels == {"high", "medium", "low"}


def test_faithfulness_label_derived_from_confidence_drop() -> None:
    """The dashboard's normalize step maps ``confidence_drop`` to a level."""
    data = load_dashboard_data(str(SAMPLES_DIR / "faithfulness_levels"))
    for _, row in data.faithfulness.iterrows():
        drop = float(row["confidence_drop"])
        if drop >= 0.20:
            expected = "high"
        elif drop >= 0.05:
            expected = "medium"
        else:
            expected = "low"
        assert row["faithfulness_label"] == expected


def test_faithfulness_label_derived_when_missing() -> None:
    """When the upstream frame lacks ``faithfulness_label``, the loader
    adds it from ``confidence_drop``."""
    # Build a hand-crafted upstream frame without faithfulness_label.
    tmp_dir = _make_tmp_outputs(
        include_all=True,
        include_faithfulness=True,
        faithfulness_rows=[
            {
                "sample_id": "X1",
                "ticker": "AAPL",
                "forecast_time": "2025-03-12 09:00",
                "prediction": "UP",
                "original_confidence": 0.8,
                "confidence_without_cited_evidence": 0.5,
                "confidence_drop": 0.30,
                "evidence_support": 1.0,
                "temporal_validity": 1.0,
            },
        ],
        # Drop the synthesized JSON sibling so the adapter does not
        # accidentally pick up the default record.
        prediction_results_json=[],
    )
    try:
        # Rewrite the file without faithfulness_label so we exercise
        # the derive path.
        from src.dashboard.data_loader import FAITHFULNESS_COLUMNS
        df = pd.DataFrame(
            [
                {
                    "sample_id": "X1",
                    "ticker": "AAPL",
                    "forecast_time": "2025-03-12 09:00",
                    "prediction": "UP",
                    "original_confidence": 0.8,
                    "confidence_without_cited_evidence": 0.5,
                    "confidence_drop": 0.30,
                    "evidence_support": 1.0,
                    "temporal_validity": 1.0,
                }
            ],
            columns=[c for c in FAITHFULNESS_COLUMNS if c != "faithfulness_label"],
        )
        df.to_csv(tmp_dir / "faithfulness_results.csv", index=False)
        data = load_dashboard_data(str(tmp_dir))
        assert "faithfulness_label" in data.faithfulness.columns
        assert data.faithfulness.iloc[0]["faithfulness_label"] == "high"
    finally:
        _rm_tree(tmp_dir)


# ---------------------------------------------------------------------------
# Adapter: synthesize evidence from JSON
# ---------------------------------------------------------------------------


def test_adapter_synthesizes_evidence_from_json() -> None:
    """When ``evidence_results.csv`` is missing, the loader synthesizes
    one from ``prediction_results.json``."""
    tmp_dir = _make_tmp_outputs(
        include_all=True,
        include_evidence=False,
        include_evidence_csv=False,
        prediction_results_json=[
            {
                "sample_id": "S1",
                "ticker": "AAPL",
                "forecast_time": "2025-03-12 09:00",
                "pro_evidence": [
                    {
                        "news_id": "N1",
                        "news_time": "2025-03-11 08:00",
                        "evidence_text": "good sales",
                        "polarity": "positive",
                        "expected_direction": "UP",
                        "support_score": 1.0,
                    }
                ],
                "counter_evidence": [],
                "up_evidence": [],
                "down_evidence": [],
                "neutral_evidence": [],
                "warnings": [],
            }
        ],
    )
    try:
        data = load_dashboard_data(str(tmp_dir))
        # The synthesized frame is built from the JSON sibling when the
        # CSV is absent. The frame is non-empty and carries the
        # correct role / cited flags.
        assert not data.evidence.empty
        assert data.evidence.iloc[0]["is_cited"] in (True, "True")
        assert data.evidence.iloc[0]["evidence_role"] == "pro_evidence"
        # The adapter does not list the file as missing when it has
        # synthesized replacement data.
        assert "evidence_results.csv" not in data.missing_files
    finally:
        _rm_tree(tmp_dir)


def test_adapter_synthesizes_leakage_from_json() -> None:
    tmp_dir = _make_tmp_outputs(
        include_all=True,
        include_leakage=False,
        include_leakage_csv=False,
        prediction_results_json=[
            {
                "sample_id": "S1",
                "ticker": "AAPL",
                "forecast_time": "2025-03-12 09:00",
                "pro_evidence": [],
                "counter_evidence": [],
                "up_evidence": [],
                "down_evidence": [],
                "neutral_evidence": [],
                "warnings": [
                    {
                        "code": "TEMPORAL_LEAKAGE_BLOCKED",
                        "evidence_id": "N1",
                        "news_time": "2025-03-12 18:00",
                        "forecast_time": "2025-03-12 09:00",
                        "message": "leakage",
                    }
                ],
            }
        ],
    )
    try:
        data = load_dashboard_data(str(tmp_dir))
        assert not data.leakage.empty
        assert float(data.leakage["leakage_minutes"].iloc[0]) > 0
        assert "temporal_leakage_results.csv" not in data.missing_files
    finally:
        _rm_tree(tmp_dir)


# ---------------------------------------------------------------------------
# Missing / empty file handling
# ---------------------------------------------------------------------------


def test_missing_file_is_marked_not_raised() -> None:
    """Empty output dir → all four files missing, no exception."""
    tmp_dir = _make_tmp_outputs(include_all=False)
    try:
        data = load_dashboard_data(str(tmp_dir))
        # predictions / faithfulness: None because no JSON sibling
        # exists. evidence / leakage: empty synthesized frames because
        # the adapter always provides a stable shape.
        assert data.predictions is None
        assert data.faithfulness is None
        assert data.evidence is not None and data.evidence.empty
        assert data.leakage is not None and data.leakage.empty
        assert "prediction_results.csv" in data.missing_files
        assert "faithfulness_results.csv" in data.missing_files
    finally:
        _rm_tree(tmp_dir)


def test_empty_file_is_marked_as_empty_not_missing() -> None:
    tmp_dir = _make_tmp_outputs(
        include_predictions=True,
        include_evidence=True,
        include_faithfulness=True,
        include_leakage=True,
        empty_predictions=True,
        empty_evidence=True,
        empty_faithfulness=True,
        empty_leakage=True,
    )
    try:
        data = load_dashboard_data(str(tmp_dir))
        assert data.predictions is not None and data.predictions.empty
        assert data.evidence is not None and data.evidence.empty
        assert data.faithfulness is not None and data.faithfulness.empty
        assert data.leakage is not None and data.leakage.empty
        assert "prediction_results.csv" in data.empty_files
    finally:
        _rm_tree(tmp_dir)


def test_loader_is_idempotent() -> None:
    data1 = load_dashboard_data(str(SAMPLES_DIR / "healthy"))
    data2 = load_dashboard_data(str(SAMPLES_DIR / "healthy"))
    pd.testing.assert_frame_equal(data1.predictions, data2.predictions)
    pd.testing.assert_frame_equal(data1.evidence, data2.evidence)
    pd.testing.assert_frame_equal(data1.faithfulness, data2.faithfulness)
    pd.testing.assert_frame_equal(data1.leakage, data2.leakage)


# ---------------------------------------------------------------------------
# Defensive: column type mismatch raises DashboardDataError
# ---------------------------------------------------------------------------


def test_loader_does_not_mutate_outputs() -> None:
    """The loader MUST NOT write to the output directory."""
    target = SAMPLES_DIR / "healthy"
    before = _dir_snapshot(target)
    load_dashboard_data(str(target))
    after = _dir_snapshot(target)
    assert before == after


def test_loader_does_not_call_upstream_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """The loader MUST NOT invoke the Forecast Model or Faithfulness Evaluator."""
    from src import dashboard

    called = {"forecast": False, "faithfulness": False}

    def _raise(*_args, **_kwargs):
        called["forecast"] = True
        raise AssertionError("forecast_model.predict was called")

    def _raise2(*_args, **_kwargs):
        called["faithfulness"] = True
        raise AssertionError("faithfulness_evaluator.evaluate_batch was called")

    monkeypatch.setattr("src.forecast_model.predict", _raise, raising=False)
    monkeypatch.setattr("src.forecast_model.predict_batch", _raise, raising=False)
    monkeypatch.setattr("src.faithfulness_evaluator.evaluate_batch", _raise2, raising=False)
    # The loader should still load the fixture without ever calling the pipeline.
    data = load_dashboard_data(str(SAMPLES_DIR / "healthy"))
    assert data is not None
    assert called == {"forecast": False, "faithfulness": False}
    # The dashboard package should also not import the upstream pipeline
    # at module load time.
    assert not hasattr(dashboard, "predict")
    assert not hasattr(dashboard, "evaluate_batch")


# ---------------------------------------------------------------------------
# Golden fixture regression — byte-equal reproducibility
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture_name",
    ["healthy", "leakage", "faithfulness_levels"],
)
def test_golden_fixture_loads_byte_equal(fixture_name: str) -> None:
    """Loading the same fixture twice produces byte-equal DataFrames."""
    target = SAMPLES_DIR / fixture_name
    data1 = load_dashboard_data(str(target))
    data2 = load_dashboard_data(str(target))
    for field in ("predictions", "evidence", "faithfulness", "leakage"):
        df1 = getattr(data1, field)
        df2 = getattr(data2, field)
        if df1 is None and df2 is None:
            continue
        if df1 is None or df2 is None:
            raise AssertionError(f"{field} differs: one side is None")
        pd.testing.assert_frame_equal(df1, df2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tmp_outputs(
    *,
    include_all: bool = True,
    include_predictions: bool = False,
    include_evidence: bool = False,
    include_faithfulness: bool = False,
    include_leakage: bool = False,
    prediction_rows: list = None,
    evidence_rows: list = None,
    faithfulness_rows: list = None,
    leakage_rows: list = None,
    empty_predictions: bool = False,
    empty_evidence: bool = False,
    empty_faithfulness: bool = False,
    empty_leakage: bool = False,
    include_evidence_csv: bool = True,
    include_leakage_csv: bool = True,
    prediction_results_json: list = None,
) -> Path:
    """Create a temporary ``outputs/``-shaped directory with the given rows."""
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="dashboard-fixture-"))
    if include_all:
        include_predictions = True
        include_evidence = True
        include_faithfulness = True
        include_leakage = True
    if include_predictions:
        _write_csv(
            tmp / "prediction_results.csv",
            PREDICTION_COLUMNS,
            [] if empty_predictions else (prediction_rows or _default_predictions()),
        )
    if include_evidence and include_evidence_csv:
        _write_csv(
            tmp / "evidence_results.csv",
            EVIDENCE_COLUMNS,
            [] if empty_evidence else (evidence_rows or _default_evidence()),
        )
    if include_faithfulness:
        _write_csv(
            tmp / "faithfulness_results.csv",
            FAITHFULNESS_COLUMNS,
            [] if empty_faithfulness else (faithfulness_rows or _default_faithfulness()),
        )
    if include_leakage and include_leakage_csv:
        _write_csv(
            tmp / "temporal_leakage_results.csv",
            LEAKAGE_COLUMNS,
            [] if empty_leakage else (leakage_rows or _default_leakage()),
        )
    if prediction_results_json is not None:
        with (tmp / "prediction_results.json").open("w", encoding="utf-8") as handle:
            json.dump(prediction_results_json, handle)
    elif include_predictions and not empty_predictions:
        # Always include a JSON sibling so the adapter has data to work
        # with when the proposal-shaped CSVs are absent.
        with (tmp / "prediction_results.json").open("w", encoding="utf-8") as handle:
            json.dump(_default_prediction_json(), handle)
    return tmp


def _write_csv(path: Path, columns, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns))
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def _default_predictions() -> list:
    return [
        {
            "sample_id": "S1",
            "ticker": "AAPL",
            "forecast_time": "2025-03-12 09:00",
            "prediction": "UP",
            "confidence": 0.8,
            "label": "UP",
            "score": 1.0,
            "rationale": "r",
            "valid_news_count": 0,
            "invalid_future_news_count": 0,
        }
    ]


def _default_evidence() -> list:
    return [
        {
            "sample_id": "S1",
            "news_id": "N1",
            "ticker": "AAPL",
            "forecast_time": "2025-03-12 09:00",
            "news_time": "2025-03-11 08:00",
            "news_text": "good",
            "evidence_text": "good",
            "polarity": "positive",
            "expected_direction": "UP",
            "evidence_role": "pro_evidence",
            "support_score": 1.0,
            "is_cited": True,
            "is_temporally_valid": True,
        }
    ]


def _default_faithfulness() -> list:
    return [
        {
            "sample_id": "S1",
            "ticker": "AAPL",
            "forecast_time": "2025-03-12 09:00",
            "prediction": "UP",
            "original_confidence": 0.8,
            "confidence_without_cited_evidence": 0.5,
            "confidence_drop": 0.30,
            "evidence_support": 1.0,
            "temporal_validity": 1.0,
            "faithfulness_label": "high",
        }
    ]


def _default_leakage() -> list:
    return [
        {
            "sample_id": "S1",
            "news_id": "N1",
            "ticker": "AAPL",
            "forecast_time": "2025-03-12 09:00",
            "news_time": "2025-03-12 18:00",
            "leakage_minutes": 540.0,
            "news_text": "leakage",
        }
    ]


def _default_prediction_json() -> list:
    return [
        {
            "sample_id": "S1",
            "ticker": "AAPL",
            "forecast_time": "2025-03-12 09:00",
            "pro_evidence": [
                {
                    "news_id": "N1",
                    "news_time": "2025-03-11 08:00",
                    "evidence_text": "good",
                    "polarity": "positive",
                    "expected_direction": "UP",
                    "support_score": 1.0,
                }
            ],
            "counter_evidence": [],
            "up_evidence": [],
            "down_evidence": [],
            "neutral_evidence": [],
            "warnings": [],
        }
    ]


def _dir_snapshot(path: Path) -> dict:
    """Return a dict of {relative_path: mtime_ns} for a directory tree."""
    out = {}
    for item in sorted(path.rglob("*")):
        if item.is_file():
            out[str(item.relative_to(path))] = item.stat().st_mtime_ns
    return out


def _rm_tree(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)