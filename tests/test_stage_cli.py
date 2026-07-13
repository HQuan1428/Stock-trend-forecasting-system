"""CLI tests for the per-stage commands (interactive-stage-cli change).

Covers: happy path per stage via ``main()``, chaining stage N output into
stage N+1, invalid input → exit code 2 with a clear stderr message, and
CLI-vs-``process()`` equivalence.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src import (
    evidence_extractor,
    evidence_selector,
    faithfulness_evaluator,
    forecast_model,
    ingest,
    market_analyzer,
    retriever,
    sufficiency_evaluator,
)
from src.schema import validate_sample

CHAIN = [
    retriever,
    evidence_extractor,
    forecast_model,
    evidence_selector,
    faithfulness_evaluator,
    sufficiency_evaluator,
    market_analyzer,
]

CSV_TEXT = """news_id,ticker,forecast_time,news_time,news_text,label,next_day_return,price_5d_return
1,AAPL,2025-03-12 09:00,2025-03-11 08:00,Apple reports record profit and strong growth,UP,0.02,0.03
2,AAPL,2025-03-12 09:00,2025-03-13 10:00,Apple wins landmark lawsuit,UP,0.02,0.03
3,GOOGL,2025-03-12 09:00,2025-03-11 09:30,Google faces antitrust lawsuit and heavy fine,DOWN,-0.01,-0.03
"""


@pytest.fixture()
def csv_path(tmp_path: Path) -> Path:
    p = tmp_path / "input.csv"
    p.write_text(CSV_TEXT, encoding="utf-8")
    return p


def _run_chain(tmp_path: Path, csv_path: Path) -> list[Path]:
    """Run ingest + all stages via their CLIs, returning the output paths."""
    paths = [tmp_path / "01_samples.json"]
    assert ingest.main(["--input", str(csv_path), "-o", str(paths[0])]) == 0
    for i, stage in enumerate(CHAIN, start=2):
        out = tmp_path / f"{i:02d}_{stage.STAGE_NAME}.json"
        assert stage.main(["--input", str(paths[-1]), "-o", str(out)]) == 0
        paths.append(out)
    return paths


# ---------------------------------------------------------------------------
# Happy path + chaining
# ---------------------------------------------------------------------------


def test_full_chain_via_cli(tmp_path: Path, csv_path: Path) -> None:
    paths = _run_chain(tmp_path, csv_path)
    final = json.loads(paths[-1].read_text(encoding="utf-8"))
    assert final["stage"] == "market_analyzer"
    assert len(final["samples"]) == 2  # AAPL group + GOOGL group
    for sample in final["samples"]:
        for key in (
            "news", "valid_news", "invalid_future_news", "evidence",
            "forecast", "selection", "coverage", "faithfulness",
            "sufficiency", "market",
        ):
            assert key in sample, f"missing {key}"


def test_ingest_groups_preserve_order_and_split_leakage(
    tmp_path: Path, csv_path: Path
) -> None:
    out = tmp_path / "01.json"
    ingest.main(["--input", str(csv_path), "-o", str(out)])
    env = json.loads(out.read_text(encoding="utf-8"))
    assert [s["ticker"] for s in env["samples"]] == ["AAPL", "GOOGL"]
    assert len(env["samples"][0]["news"]) == 2

    out2 = tmp_path / "02.json"
    retriever.main(["--input", str(out), "-o", str(out2)])
    env2 = json.loads(out2.read_text(encoding="utf-8"))
    aapl = env2["samples"][0]
    # news_id 2 is dated after the forecast → must land in invalid_future_news
    assert [n["news_id"] for n in aapl["valid_news"]] == ["1"]
    assert [n["news_id"] for n in aapl["invalid_future_news"]] == ["2"]


def test_each_stage_output_passes_next_stage_validator(
    tmp_path: Path, csv_path: Path
) -> None:
    paths = _run_chain(tmp_path, csv_path)
    next_stages = [s.STAGE_NAME for s in CHAIN] + ["export_csv"]
    for path, next_stage in zip(paths, next_stages):
        env = json.loads(path.read_text(encoding="utf-8"))
        for sample in env["samples"]:
            assert validate_sample(sample, next_stage) == []


def test_cli_and_process_produce_same_result(tmp_path: Path, csv_path: Path) -> None:
    out1 = tmp_path / "01.json"
    ingest.main(["--input", str(csv_path), "-o", str(out1)])
    env = json.loads(out1.read_text(encoding="utf-8"))

    via_process = retriever.process(copy.deepcopy(env))
    out2 = tmp_path / "02.json"
    retriever.main(["--input", str(out1), "-o", str(out2)])
    via_cli = json.loads(out2.read_text(encoding="utf-8"))
    assert via_cli == json.loads(
        json.dumps(via_process)  # normalize tuples/None the same way JSON does
    )


# ---------------------------------------------------------------------------
# Invalid input → exit 2
# ---------------------------------------------------------------------------


def test_missing_input_file_exits_2(tmp_path: Path, capsys) -> None:
    code = retriever.main(
        ["--input", str(tmp_path / "nope.json"), "-o", str(tmp_path / "o.json")]
    )
    assert code == 2
    assert "not found" in capsys.readouterr().err


def test_ingest_missing_column_exits_2(tmp_path: Path, capsys) -> None:
    bad = tmp_path / "bad.csv"
    bad.write_text("foo,bar\n1,2\n", encoding="utf-8")
    code = ingest.main(["--input", str(bad), "-o", str(tmp_path / "o.json")])
    assert code == 2
    assert "missing required columns" in capsys.readouterr().err


def test_skipping_a_stage_fails_validation_with_sample_id(
    tmp_path: Path, csv_path: Path, capsys
) -> None:
    out1 = tmp_path / "01.json"
    ingest.main(["--input", str(csv_path), "-o", str(out1)])
    # Jump straight to faithfulness (missing forecast/selection/etc.)
    code = faithfulness_evaluator.main(
        ["--input", str(out1), "-o", str(tmp_path / "o.json")]
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "'forecast'" in err
    assert "AAPL_2025-03-12_0900" in err


def test_malformed_json_exits_2(tmp_path: Path, capsys) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    code = retriever.main(["--input", str(bad), "-o", str(tmp_path / "o.json")])
    assert code == 2
    assert "not valid JSON" in capsys.readouterr().err