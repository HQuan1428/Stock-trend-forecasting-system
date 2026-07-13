"""End-to-end tests for src.runner and src.export_csv."""

from __future__ import annotations

import csv
import filecmp
import json
from pathlib import Path

import pytest

from src import export_csv, runner

DATASET = Path(__file__).resolve().parent.parent / "data" / "sample_dataset.csv"

ENVELOPE_FILES = [
    "01_samples.json",
    "02_retrieved.json",
    "03_evidence.json",
    "04_forecast.json",
    "05_selected.json",
    "06_faithfulness.json",
    "07_sufficiency.json",
    "08_market.json",
]

CSV_FILES = [
    "prediction_results.csv",
    "evidence_results.csv",
    "faithfulness_results.csv",
    "sufficiency_results.csv",
    "market_consistency_results.csv",
    "temporal_leakage_results.csv",
]


@pytest.fixture(scope="module")
def full_run(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("run")
    code = runner.main(["--input", str(DATASET), "--output-dir", str(out)])
    assert code == 0
    return out


def test_all_outputs_written(full_run: Path) -> None:
    for name in ENVELOPE_FILES + CSV_FILES:
        assert (full_run / name).exists(), f"missing {name}"


def test_final_envelope_shape(full_run: Path) -> None:
    env = json.loads((full_run / "08_market.json").read_text(encoding="utf-8"))
    assert env["stage"] == "market_analyzer"
    assert len(env["samples"]) > 0
    sample = env["samples"][0]
    for key in ("forecast", "selection", "faithfulness", "sufficiency", "market"):
        assert key in sample


def test_csv_headers_match_columns(full_run: Path) -> None:
    expected = {
        "prediction_results.csv": export_csv.PREDICTION_COLUMNS,
        "evidence_results.csv": export_csv.EVIDENCE_COLUMNS,
        "faithfulness_results.csv": export_csv.FAITHFULNESS_COLUMNS,
        "sufficiency_results.csv": export_csv.SUFFICIENCY_COLUMNS,
        "market_consistency_results.csv": export_csv.MARKET_COLUMNS,
        "temporal_leakage_results.csv": export_csv.LEAKAGE_COLUMNS,
    }
    for name, columns in expected.items():
        with (full_run / name).open(encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle))
        assert header == list(columns), name


def test_determinism_two_runs_byte_equal(full_run: Path, tmp_path: Path) -> None:
    out2 = tmp_path / "run2"
    assert runner.main(["--input", str(DATASET), "--output-dir", str(out2)]) == 0
    for name in ENVELOPE_FILES + CSV_FILES:
        assert filecmp.cmp(full_run / name, out2 / name, shallow=False), (
            f"{name} differs between runs"
        )


def test_stop_after_writes_only_prefix(tmp_path: Path) -> None:
    out = tmp_path / "partial"
    code = runner.main(
        [
            "--input", str(DATASET),
            "--output-dir", str(out),
            "--stop-after", "forecast_model",
        ]
    )
    assert code == 0
    for name in ENVELOPE_FILES[:4]:
        assert (out / name).exists(), f"missing {name}"
    for name in ENVELOPE_FILES[4:] + CSV_FILES:
        assert not (out / name).exists(), f"unexpected {name}"


def test_intermediate_file_reusable_by_standalone_cli(
    full_run: Path, tmp_path: Path
) -> None:
    """outputs/03_evidence.json fed to the forecast CLI reproduces 04_forecast.json."""
    from src import forecast_model

    out = tmp_path / "04_again.json"
    code = forecast_model.main(
        ["--input", str(full_run / "03_evidence.json"), "-o", str(out)]
    )
    assert code == 0
    assert out.read_bytes() == (full_run / "04_forecast.json").read_bytes()


def test_export_csv_standalone_matches_runner(full_run: Path, tmp_path: Path) -> None:
    out = tmp_path / "csv_again"
    code = export_csv.main(
        [
            "--input", str(full_run / "08_market.json"),
            "--output-dir", str(out),
        ]
    )
    assert code == 0
    for name in CSV_FILES:
        assert filecmp.cmp(full_run / name, out / name, shallow=False), name


def test_runner_missing_input_exits_2(tmp_path: Path, capsys) -> None:
    code = runner.main(
        ["--input", str(tmp_path / "nope.csv"), "--output-dir", str(tmp_path / "o")]
    )
    assert code == 2
    assert "not found" in capsys.readouterr().err