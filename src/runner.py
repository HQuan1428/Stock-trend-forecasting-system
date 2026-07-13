"""Thin end-to-end runner for the interactive stage chain.

Chains the per-stage ``process()`` functions in-process — the exact
functions the standalone CLIs call, so there is a single code path —
and writes each intermediate envelope to ``NN_<name>.json`` in the
output directory, followed by the six result CSVs.

This module re-implements NO stage logic; it is glue only.

CLI:
    python -m src.runner --input data/sample_dataset.csv --output-dir outputs
    python -m src.runner --input ... --output-dir ... --stop-after forecast_model
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from src import (
    evidence_extractor,
    evidence_selector,
    export_csv,
    faithfulness_evaluator,
    forecast_model,
    ingest,
    market_analyzer,
    retriever,
    sufficiency_evaluator,
)
from src.stage_io import EXIT_INVALID_INPUT, EnvelopeError, dump_envelope

# (stage_name, envelope filename, process function) in chain order.
STAGES: Tuple[Tuple[str, str, Callable[[Dict[str, Any]], Dict[str, Any]]], ...] = (
    ("retriever", "02_retrieved.json", retriever.process),
    ("evidence_extractor", "03_evidence.json", evidence_extractor.process),
    ("forecast_model", "04_forecast.json", forecast_model.process),
    ("evidence_selector", "05_selected.json", evidence_selector.process),
    ("faithfulness_evaluator", "06_faithfulness.json", faithfulness_evaluator.process),
    ("sufficiency_evaluator", "07_sufficiency.json", sufficiency_evaluator.process),
    ("market_analyzer", "08_market.json", market_analyzer.process),
)

STAGE_NAMES: Tuple[str, ...] = ("ingest",) + tuple(s[0] for s in STAGES) + (
    "export_csv",
)


def run(
    input_csv: str, output_dir: str, *, stop_after: Optional[str] = None
) -> Dict[str, Any]:
    """Run the chain on ``input_csv``, writing envelopes (and CSVs) to
    ``output_dir``. Returns a summary dict.

    Raises:
        EnvelopeError: bad input CSV.
        ValueError: unknown ``stop_after`` stage name.
    """
    if stop_after is not None and stop_after not in STAGE_NAMES:
        raise ValueError(
            f"unknown stage {stop_after!r}; expected one of {STAGE_NAMES}"
        )
    out = Path(output_dir)
    written: List[str] = []

    envelope = ingest.process_csv(input_csv)
    path = out / "01_samples.json"
    dump_envelope(envelope, str(path))
    written.append(str(path))
    if stop_after == "ingest":
        return {"samples": len(envelope["samples"]), "written": written}

    for name, filename, process in STAGES:
        envelope = process(envelope)
        path = out / filename
        dump_envelope(envelope, str(path))
        written.append(str(path))
        if stop_after == name:
            return {"samples": len(envelope["samples"]), "written": written}

    csvs = export_csv.export(envelope, output_dir)
    written.extend(csvs.values())
    return {"samples": len(envelope["samples"]), "written": written}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="src.runner",
        description="Run the full stage chain on a news CSV.",
    )
    parser.add_argument("--input", required=True, help="Path to the input CSV.")
    parser.add_argument(
        "--output-dir", required=True, help="Directory for envelopes and CSVs."
    )
    parser.add_argument(
        "--stop-after",
        choices=STAGE_NAMES,
        help="Stop after this stage (later files are not written).",
    )
    args = parser.parse_args(argv)
    try:
        summary = run(args.input, args.output_dir, stop_after=args.stop_after)
    except EnvelopeError as exc:
        print(f"src.runner: {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT
    print(f"src.runner: ok ({summary['samples']} samples)")
    for path in summary["written"]:
        print(f"  {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())