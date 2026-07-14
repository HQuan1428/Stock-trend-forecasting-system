"""Ingest stage: input CSV → the first envelope.

The first command in the interactive stage chain. Reads the project's
news CSV (``news_id, ticker, forecast_time, news_time, news_text,
label`` plus the optional B3 columns ``next_day_return`` /
``price_5d_return``), groups rows by ``(ticker, forecast_time)``
preserving first-appearance order, and emits the initial envelope:

    {"stage": "ingest", "samples": [{sample_id, ticker, forecast_time,
     label, next_day_return, price_5d_return, news: [...]}, ...]}

Uses only the stdlib ``csv`` module — no pandas.

CLI: ``python -m src.stages.ingest --input data/sample_dataset.csv -o 01_samples.json``
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.stage_io import (
    EXIT_INVALID_INPUT,
    EnvelopeError,
    build_stage_parser,
    dump_envelope,
)

STAGE_NAME = "ingest"

REQUIRED_COLUMNS = ("news_id", "ticker", "forecast_time", "news_time", "news_text")


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Parse ``value`` as a float, falling back to ``default`` on any
    falsy or unparseable input (mirrors the CSV's optional B3 columns).
    """
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _sample_id(ticker: str, forecast_time: str) -> str:
    return f"{ticker}_{forecast_time}".replace(" ", "_").replace(":", "")


def read_csv_rows(input_path: str) -> List[Dict[str, str]]:
    """Read the input CSV, raising :class:`EnvelopeError` on bad input."""
    path_obj = Path(input_path)
    if not path_obj.exists():
        raise EnvelopeError(f"input file not found: {input_path}")
    with path_obj.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
        if missing:
            raise EnvelopeError(
                f"input CSV is missing required columns: {missing}"
            )
        return list(reader)


def build_envelope(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    """Group CSV ``rows`` into the initial envelope."""
    group_keys: List[Tuple[str, str]] = []
    groups: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
    for row in rows:
        key = (str(row["ticker"]), str(row["forecast_time"]))
        if key not in groups:
            groups[key] = []
            group_keys.append(key)
        groups[key].append(row)

    samples: List[Dict[str, Any]] = []
    for ticker, forecast_time in group_keys:
        group_rows = groups[(ticker, forecast_time)]
        label = ""
        for row in group_rows:
            if row.get("label"):
                label = str(row["label"])
                break
        first = group_rows[0]
        samples.append(
            {
                "sample_id": _sample_id(ticker, forecast_time),
                "ticker": ticker,
                "forecast_time": forecast_time,
                "label": label,
                "next_day_return": _safe_float(first.get("next_day_return")),
                "price_5d_return": _safe_float(first.get("price_5d_return")),
                "news": [
                    {
                        "news_id": str(row["news_id"]),
                        "news_time": str(row["news_time"]),
                        "news_text": str(row["news_text"]),
                    }
                    for row in group_rows
                ],
            }
        )
    return {"stage": STAGE_NAME, "samples": samples}


def process_csv(input_path: str) -> Dict[str, Any]:
    """CSV path → initial envelope (the ingest equivalent of ``process``)."""
    return build_envelope(read_csv_rows(input_path))


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_stage_parser(
        STAGE_NAME, "Read the input news CSV and emit the initial envelope."
    )
    args = parser.parse_args(argv)
    try:
        envelope = process_csv(args.input)
    except EnvelopeError as exc:
        print(f"src.{STAGE_NAME}: {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT
    dump_envelope(envelope, args.output)
    print(
        f"src.{STAGE_NAME}: ok ({len(envelope['samples'])} samples) -> {args.output}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())