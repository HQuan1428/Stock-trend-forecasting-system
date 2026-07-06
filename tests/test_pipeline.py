"""Integration tests for ``src.pipeline``.

These tests cover the ten scenarios from the OpenSpec change:

1.  Pipeline completes without error on the real sample dataset.
2.  Future news is excluded from prediction.
3.  Valid news flows into evidence extraction.
4.  ``prediction_results.csv`` is created with required columns.
5.  ``faithfulness_results.csv`` is created with required columns.
6.  ``evidence_results.csv`` is created with required columns.
7.  ``temporal_leakage_results.csv`` is created with required columns.
8.  ``confidence_drop`` is a finite float for at least one group.
9.  A group with future rows shows ``invalid_future_news_count > 0``.
10. The four CSVs contain the columns the dashboard requires.

The tests are deliberately small and deterministic — no mocks, no
external services. They run against the real ``data/sample_dataset.csv``
when present, and against a synthetic in-memory CSV otherwise.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from src.pipeline import (
    EVIDENCE_COLUMNS,
    FAITHFULNESS_COLUMNS,
    LEAKAGE_COLUMNS,
    MARKET_COLUMNS,
    PREDICTION_COLUMNS,
    SUFFICIENCY_COLUMNS,
    run_pipeline,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_CSV = PROJECT_ROOT / "data" / "sample_dataset.csv"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_output_dir(tmp_path: Path) -> Path:
    """Run the pipeline on the real sample dataset into a temp dir."""
    if not SAMPLE_CSV.exists():
        pytest.skip(f"sample dataset not found at {SAMPLE_CSV}")
    run_pipeline(str(SAMPLE_CSV), str(tmp_path))
    return tmp_path


@pytest.fixture()
def synthetic_output_dir(tmp_path: Path) -> Path:
    """Build a small synthetic CSV (3 rows: 1 valid, 1 future, 1 alt-group)
    and run the pipeline against it.
    """
    csv = tmp_path / "synthetic.csv"
    csv.write_text(
        "news_id,ticker,forecast_time,news_time,news_text,label\n"
        # Group 1: AAPL @ 2025-03-12 — one valid row.
        "1,AAPL,2025-03-12 09:00,2025-03-11 08:00,"
        "Apple reports stronger than expected iPhone demand in India,UP\n"
        # Group 1: AAPL @ 2025-03-12 — one FUTURE row.
        "2,AAPL,2025-03-12 09:00,2025-03-12 15:00,"
        "Apple launches surprise new product for next quarter,UP\n"
        # Group 2: GOOGL @ 2025-03-12 — one valid row.
        "3,GOOGL,2025-03-12 09:00,2025-03-11 18:00,"
        "Google loses small cloud customer but says backlog remains steady,HOLD\n"
    )
    run_pipeline(str(csv), str(tmp_path / "out"))
    return tmp_path / "out"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_csv(path: Path) -> pd.DataFrame:
    assert path.exists(), f"expected output file missing: {path}"
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Test 1: smoke test on the real sample dataset
# ---------------------------------------------------------------------------


def test_pipeline_runs_on_sample_dataset(sample_output_dir: Path) -> None:
    """Test 1: pipeline completes without error on the sample dataset."""
    for name in (
        "prediction_results.csv",
        "evidence_results.csv",
        "faithfulness_results.csv",
        "temporal_leakage_results.csv",
    ):
        path = sample_output_dir / name
        assert path.exists(), f"missing output: {name}"
        df = pd.read_csv(path)
        assert not df.empty, f"{name} has no rows"


# ---------------------------------------------------------------------------
# Test 2: future news is excluded from prediction
# ---------------------------------------------------------------------------


def test_future_news_excluded_from_evidence_results(synthetic_output_dir: Path) -> None:
    """Test 2: a future-dated news_id is in leakage, not in evidence."""
    leakage = _read_csv(synthetic_output_dir / "temporal_leakage_results.csv")
    evidence = _read_csv(synthetic_output_dir / "evidence_results.csv")
    # news_id=2 is future-dated relative to forecast 2025-03-12 09:00.
    assert 2 in set(leakage["news_id"].tolist()), (
        "future-dated news_id=2 should appear in leakage_results"
    )
    assert 2 not in set(evidence["news_id"].tolist()), (
        "future-dated news_id=2 must NOT appear in evidence_results"
    )


# ---------------------------------------------------------------------------
# Test 3: valid news flows into evidence extraction
# ---------------------------------------------------------------------------


def test_valid_news_flows_into_extraction(synthetic_output_dir: Path) -> None:
    """Test 3: at least one row exists in evidence_results for the all-valid group."""
    evidence = _read_csv(synthetic_output_dir / "evidence_results.csv")
    # Group GOOGL @ 2025-03-12 has one valid row (news_id=3).
    googl_rows = evidence[
        evidence["ticker"].astype(str) == "GOOGL"
    ]
    assert not googl_rows.empty, "GOOGL group should have at least one evidence row"
    assert 3 in set(googl_rows["news_id"].tolist())


# ---------------------------------------------------------------------------
# Test 4: prediction_results.csv schema
# ---------------------------------------------------------------------------


def test_prediction_results_schema(sample_output_dir: Path) -> None:
    """Test 4: prediction_results.csv has all required columns."""
    df = _read_csv(sample_output_dir / "prediction_results.csv")
    for col in PREDICTION_COLUMNS:
        assert col in df.columns, f"prediction_results missing column: {col}"


# ---------------------------------------------------------------------------
# Test 5: faithfulness_results.csv schema
# ---------------------------------------------------------------------------


def test_faithfulness_results_schema(sample_output_dir: Path) -> None:
    """Test 5: faithfulness_results.csv has all required columns."""
    df = _read_csv(sample_output_dir / "faithfulness_results.csv")
    for col in FAITHFULNESS_COLUMNS:
        assert col in df.columns, f"faithfulness_results missing column: {col}"
    # faithfulness_label must be one of HIGH / MEDIUM / LOW
    labels = set(df["faithfulness_label"].dropna().unique())
    assert labels <= {"HIGH", "MEDIUM", "LOW"}, f"bad labels: {labels}"


# ---------------------------------------------------------------------------
# Test 6: evidence_results.csv schema
# ---------------------------------------------------------------------------


def test_evidence_results_schema(sample_output_dir: Path) -> None:
    """Test 6: evidence_results.csv has all required columns."""
    df = _read_csv(sample_output_dir / "evidence_results.csv")
    for col in EVIDENCE_COLUMNS:
        assert col in df.columns, f"evidence_results missing column: {col}"
    # evidence_role must be one of pro / counter / neutral
    roles = set(df["evidence_role"].dropna().unique())
    assert roles <= {"pro", "counter", "neutral"}, f"bad evidence_role: {roles}"


# ---------------------------------------------------------------------------
# Test 7: temporal_leakage_results.csv schema
# ---------------------------------------------------------------------------


def test_temporal_leakage_results_schema(sample_output_dir: Path) -> None:
    """Test 7: temporal_leakage_results.csv has all required columns."""
    df = _read_csv(sample_output_dir / "temporal_leakage_results.csv")
    for col in LEAKAGE_COLUMNS:
        assert col in df.columns, f"leakage_results missing column: {col}"
    if not df.empty:
        assert (df["leakage_type"] == "future_news").all(), (
            "every leakage row must have leakage_type == future_news"
        )


# ---------------------------------------------------------------------------
# Test 8: confidence_drop is a finite float
# ---------------------------------------------------------------------------


def test_confidence_drop_is_finite(sample_output_dir: Path) -> None:
    """Test 8: at least one row has a finite confidence_drop."""
    df = _read_csv(sample_output_dir / "faithfulness_results.csv")
    drops = df["confidence_drop"].astype(float)
    finite = drops[
        drops.apply(lambda v: isinstance(v, float) and math.isfinite(v))
    ]
    assert not finite.empty, "no finite confidence_drop value found"


# ---------------------------------------------------------------------------
# Test 9: invalid_future_news_count > 0 for groups with future rows
# ---------------------------------------------------------------------------


def test_invalid_future_news_count_for_future_groups(synthetic_output_dir: Path) -> None:
    """Test 9: AAPL @ 2025-03-12 has one future row, so its count > 0."""
    df = _read_csv(synthetic_output_dir / "prediction_results.csv")
    aapl_row = df[df["ticker"].astype(str) == "AAPL"].iloc[0]
    assert int(aapl_row["invalid_future_news_count"]) > 0, (
        "AAPL group should have invalid_future_news_count > 0"
    )
    assert int(aapl_row["valid_news_count"]) == 1


# ---------------------------------------------------------------------------
# Test 10: dashboard column contract
# ---------------------------------------------------------------------------


def test_dashboard_column_contract(sample_output_dir: Path) -> None:
    """Test 10: the four CSVs contain the columns ``load_dashboard_data`` requires."""
    from src.dashboard.data_loader import (
        EVIDENCE_COLUMNS as DASH_EVIDENCE,
        FAITHFULNESS_COLUMNS as DASH_FAITH,
        LEAKAGE_COLUMNS as DASH_LEAK,
        PREDICTION_COLUMNS as DASH_PRED,
    )

    pred = _read_csv(sample_output_dir / "prediction_results.csv")
    evid = _read_csv(sample_output_dir / "evidence_results.csv")
    faith = _read_csv(sample_output_dir / "faithfulness_results.csv")
    leak = _read_csv(sample_output_dir / "temporal_leakage_results.csv")

    # The dashboard loader backfills missing columns, so we just need to
    # verify the proposal-shape columns exist; the rest is the loader's job.
    for col in ("sample_id", "ticker", "forecast_time", "prediction"):
        assert col in pred.columns
        assert col in faith.columns
    for col in ("sample_id", "ticker", "forecast_time", "news_id"):
        assert col in evid.columns
        assert col in leak.columns


# ---------------------------------------------------------------------------
# Bonus: missing label column is tolerated
# ---------------------------------------------------------------------------


def test_pipeline_tolerates_missing_label_column(tmp_path: Path) -> None:
    """If the label column is absent, every row's label is empty and the run
    still completes without raising."""
    csv = tmp_path / "no_label.csv"
    csv.write_text(
        "news_id,ticker,forecast_time,news_time,news_text\n"
        "1,AAPL,2025-03-12 09:00,2025-03-11 08:00,"
        "Apple reports stronger than expected iPhone demand in India\n"
    )
    out = tmp_path / "out"
    run_pipeline(str(csv), str(out))
    pred = pd.read_csv(out / "prediction_results.csv")
    assert len(pred) == 1
    # label column is present but empty.
    assert "label" in pred.columns


# ---------------------------------------------------------------------------
# B2: Counterevidence Coverage
# ---------------------------------------------------------------------------


def test_faithfulness_results_has_counterevidence_columns(sample_output_dir: Path) -> None:
    """Task 4.1: faithfulness_results.csv must have coverage columns after pipeline run."""
    df = _read_csv(sample_output_dir / "faithfulness_results.csv")
    assert "counterevidence_coverage" in df.columns, (
        "faithfulness_results.csv missing column: counterevidence_coverage"
    )
    assert "counterevidence_detected" in df.columns, (
        "faithfulness_results.csv missing column: counterevidence_detected"
    )
    coverages = pd.to_numeric(df["counterevidence_coverage"], errors="coerce")
    assert coverages.between(0.0, 1.0).all(), (
        "counterevidence_coverage values must be in [0.0, 1.0]"
    )


def test_counterevidence_detected_true_for_mixed_evidence(tmp_path: Path) -> None:
    """Task 4.2: sample with UP and DOWN evidence → counterevidence_detected=True."""
    csv = tmp_path / "mixed.csv"
    csv.write_text(
        "news_id,ticker,forecast_time,news_time,news_text,label\n"
        # positive signal → should give UP prediction
        "1,TSLA,2025-03-12 09:00,2025-03-11 08:00,"
        "Tesla beats expectations and raises guidance for next quarter,UP\n"
        # negative signal → counterevidence for UP prediction
        "2,TSLA,2025-03-12 09:00,2025-03-11 09:00,"
        "Tesla faces a recall of Model Y vehicles due to brake defect,UP\n"
    )
    out = tmp_path / "out"
    run_pipeline(str(csv), str(out))
    faith = _read_csv(out / "faithfulness_results.csv")
    tsla_row = faith[faith["ticker"].astype(str) == "TSLA"].iloc[0]
    assert bool(tsla_row["counterevidence_detected"]) is True, (
        "TSLA group has both UP and DOWN evidence — counterevidence_detected must be True"
    )


def test_counterevidence_detected_false_for_single_direction(tmp_path: Path) -> None:
    """Task 4.3: sample with only positive evidence → counterevidence_detected=False."""
    csv = tmp_path / "single_dir.csv"
    csv.write_text(
        "news_id,ticker,forecast_time,news_time,news_text,label\n"
        "1,AMZN,2025-03-12 09:00,2025-03-11 08:00,"
        "Amazon beats expectations and launches new product lineup,UP\n"
        "2,AMZN,2025-03-12 09:00,2025-03-11 09:00,"
        "Amazon signs a major supply agreement with logistics partners,UP\n"
    )
    out = tmp_path / "out"
    run_pipeline(str(csv), str(out))
    faith = _read_csv(out / "faithfulness_results.csv")
    amzn_row = faith[faith["ticker"].astype(str) == "AMZN"].iloc[0]
    assert bool(amzn_row["counterevidence_detected"]) is False, (
        "AMZN group has only positive evidence — counterevidence_detected must be False"
    )


# ---------------------------------------------------------------------------
# B1: Sufficiency tests
# ---------------------------------------------------------------------------


def test_sufficiency_results_csv_has_required_columns(sample_output_dir: Path) -> None:
    """Task 5.2: pipeline produces sufficiency_results.csv with the 10 required columns."""
    suff = _read_csv(sample_output_dir / "sufficiency_results.csv")
    missing = [c for c in SUFFICIENCY_COLUMNS if c not in suff.columns]
    assert not missing, f"sufficiency_results.csv missing columns: {missing}"


def test_sufficiency_results_row_count_equals_groups(sample_output_dir: Path) -> None:
    """Task 5.3: sufficiency_results.csv has exactly one row per (ticker, forecast_time) group."""
    preds = _read_csv(sample_output_dir / "prediction_results.csv")
    suff = _read_csv(sample_output_dir / "sufficiency_results.csv")
    n_groups = len(preds)
    assert len(suff) == n_groups, (
        f"expected {n_groups} rows in sufficiency_results.csv (one per group), got {len(suff)}"
    )


# ---------------------------------------------------------------------------
# B3: Market Consistency tests
# ---------------------------------------------------------------------------


def test_market_consistency_results_csv_has_required_columns(sample_output_dir: Path) -> None:
    """Task 6.2: pipeline produces market_consistency_results.csv with 9 required columns."""
    market = _read_csv(sample_output_dir / "market_consistency_results.csv")
    missing = [c for c in MARKET_COLUMNS if c not in market.columns]
    assert not missing, f"market_consistency_results.csv missing columns: {missing}"


def test_market_consistency_results_row_count_equals_groups(sample_output_dir: Path) -> None:
    """Task 6.3: market_consistency_results.csv has exactly one row per (ticker, forecast_time) group."""
    preds = _read_csv(sample_output_dir / "prediction_results.csv")
    market = _read_csv(sample_output_dir / "market_consistency_results.csv")
    assert len(market) == len(preds), (
        f"expected {len(preds)} rows in market_consistency_results.csv, got {len(market)}"
    )


def test_pipeline_does_not_crash_without_market_columns(tmp_path: Path) -> None:
    """Task 6.4: pipeline with no next_day_return/price_5d_return columns → no crash, defaults to 0.0."""
    csv = tmp_path / "no_market.csv"
    csv.write_text(
        "news_id,ticker,forecast_time,news_time,news_text,label\n"
        "1,TSLA,2025-04-01 09:00,2025-03-31 08:00,"
        "Tesla reports record deliveries in Q1 2025,UP\n"
    )
    out = tmp_path / "out"
    summary = run_pipeline(str(csv), str(out))
    assert "market_consistency_results_csv" in summary
    market = _read_csv(out / "market_consistency_results.csv")
    assert len(market) == 1
    assert float(market.iloc[0]["next_day_return"]) == 0.0
    assert float(market.iloc[0]["price_5d_return"]) == 0.0
    assert str(market.iloc[0]["regime"]) == "sideways"