"""Export stage: final envelope → the six result CSVs.

The last (optional) step in the interactive stage chain. Takes the
envelope produced by ``market_analyzer`` and writes the same six CSVs
the old monolithic pipeline produced, with identical columns and
derivation rules (faithfulness_label HIGH/MEDIUM/LOW, leakage_minutes):

    prediction_results.csv
    evidence_results.csv
    faithfulness_results.csv          (includes B2 counterevidence_coverage)
    sufficiency_results.csv           (B1)
    market_consistency_results.csv    (B3)
    temporal_leakage_results.csv

All row-building glue is ported from ``PipelineRunner`` (see
``git show`` history of ``src/pipeline.py``); the CSV writer uses the
stdlib ``csv`` module instead of pandas.

CLI: ``python -m src.export_csv --input 08_market.json --output-dir outputs``
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.stage_io import EXIT_INVALID_INPUT, EnvelopeError, load_envelope

STAGE_NAME = "export_csv"

PREDICTION_COLUMNS: Tuple[str, ...] = (
    "sample_id", "ticker", "forecast_time", "prediction", "confidence",
    "score", "label", "is_correct", "rationale", "cited_evidence_count",
    "valid_news_count", "invalid_future_news_count",
)

EVIDENCE_COLUMNS: Tuple[str, ...] = (
    "sample_id", "ticker", "forecast_time", "news_id", "news_time",
    "news_text", "evidence_text", "polarity", "expected_direction",
    "evidence_role", "support_score", "is_cited", "is_temporally_valid",
)

FAITHFULNESS_COLUMNS: Tuple[str, ...] = (
    "sample_id", "ticker", "forecast_time", "prediction",
    "original_confidence", "confidence_without_cited_evidence",
    "confidence_drop", "temporal_validity", "evidence_support",
    "faithfulness_label", "counterevidence_coverage",
    "counterevidence_detected",
)

SUFFICIENCY_COLUMNS: Tuple[str, ...] = (
    "sample_id", "ticker", "forecast_time", "prediction",
    "original_confidence", "sufficiency_confidence", "sufficiency_score",
    "prediction_on_only_cited", "counterfactual_confidence",
    "counterfactual_delta",
)

MARKET_COLUMNS: Tuple[str, ...] = (
    "sample_id", "ticker", "forecast_time", "prediction",
    "next_day_return", "price_5d_return", "market_consistent", "regime",
    "market_consistency_score",
)

LEAKAGE_COLUMNS: Tuple[str, ...] = (
    "sample_id", "ticker", "forecast_time", "news_id", "news_time",
    "news_text", "leakage_minutes", "leakage_type",
)


def _news_text(item: Dict[str, Any]) -> str:
    """Return the body text of a news dict under ``news_text`` or ``text``."""
    return item.get("news_text", item.get("text", ""))


def faithfulness_label(confidence_drop: float, temporal_validity: float) -> str:
    """Map (confidence_drop, temporal_validity) -> HIGH / MEDIUM / LOW.

    HIGH   if confidence_drop >= 0.20 and temporal_validity == 1.0
    MEDIUM if confidence_drop >= 0.05 and temporal_validity == 1.0
    LOW    otherwise
    """
    if temporal_validity >= 1.0 and confidence_drop >= 0.20:
        return "HIGH"
    if temporal_validity >= 1.0 and confidence_drop >= 0.05:
        return "MEDIUM"
    return "LOW"


def compute_leakage_minutes(news_time: str, forecast_time: str) -> int:
    """Minutes by which ``news_time`` exceeds ``forecast_time`` (UTC).

    Returns 0 on parse failure (defensive).
    """
    try:
        nt = datetime.fromisoformat(news_time.replace(" ", "T"))
        ft = datetime.fromisoformat(forecast_time.replace(" ", "T"))
        if nt.tzinfo is None:
            nt = nt.replace(tzinfo=timezone.utc)
        if ft.tzinfo is None:
            ft = ft.replace(tzinfo=timezone.utc)
        delta = (nt - ft).total_seconds() / 60.0
        return max(0, int(delta))
    except (ValueError, TypeError):
        return 0


def _cited_ids(selection: Dict[str, Any]) -> set:
    return {e["news_id"] for e in selection["pro_evidence"]} | {
        e["news_id"] for e in selection["counterevidence"]
    }


def _evidence_rows(sample: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Merge Evidence Extractor output with Evidence Selector roles."""
    selection = sample["selection"]
    cited = _cited_ids(selection)
    selector_index: Dict[str, str] = {}
    for e in selection["pro_evidence"]:
        selector_index[e["news_id"]] = "pro"
    for e in selection["counterevidence"]:
        selector_index[e["news_id"]] = "counter"
    for e in selection["neutral_evidence"]:
        selector_index.setdefault(e["news_id"], "neutral")

    text_by_news = {n["news_id"]: _news_text(n) for n in sample["valid_news"]}
    rows: List[Dict[str, Any]] = []
    for ev in sample["evidence"]:
        news_id = ev["news_id"]
        rows.append(
            {
                "sample_id": sample["sample_id"],
                "ticker": sample["ticker"],
                "forecast_time": sample["forecast_time"],
                "news_id": news_id,
                "news_time": ev["news_time"],
                "news_text": text_by_news.get(news_id, ""),
                "evidence_text": ev.get("evidence_text", ""),
                "polarity": ev.get("polarity", "neutral"),
                "expected_direction": ev.get("expected_direction", "HOLD"),
                "evidence_role": selector_index.get(news_id, "neutral"),
                "support_score": float(ev.get("support_score", 0.0) or 0.0),
                "is_cited": news_id in cited,
                "is_temporally_valid": True,
            }
        )
    return rows


def build_rows(envelope: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Build the six row lists from the final envelope."""
    prediction_rows: List[Dict[str, Any]] = []
    evidence_rows: List[Dict[str, Any]] = []
    faithfulness_rows: List[Dict[str, Any]] = []
    sufficiency_rows: List[Dict[str, Any]] = []
    market_rows: List[Dict[str, Any]] = []
    leakage_rows: List[Dict[str, Any]] = []

    for sample in envelope["samples"]:
        base = {
            "sample_id": sample["sample_id"],
            "ticker": sample["ticker"],
            "forecast_time": sample["forecast_time"],
        }
        forecast = sample["forecast"]
        report = sample["faithfulness"]
        coverage = sample["coverage"]
        suff = sample["sufficiency"]
        market = sample["market"]
        label = sample.get("label", "")
        cited = _cited_ids(sample["selection"])
        drop = float(report["confidence_drop"])
        temporal_validity = float(report["temporal_validity"])

        prediction_rows.append(
            {
                **base,
                "prediction": forecast["prediction"],
                "confidence": float(forecast["confidence"]),
                "score": int(forecast["score"]),
                "label": label,
                "is_correct": bool(label != "" and label == forecast["prediction"]),
                "rationale": forecast["rationale"],
                "cited_evidence_count": len(cited),
                "valid_news_count": len(sample["valid_news"]),
                "invalid_future_news_count": len(sample["invalid_future_news"]),
            }
        )
        evidence_rows.extend(_evidence_rows(sample))
        faithfulness_rows.append(
            {
                **base,
                "prediction": forecast["prediction"],
                "original_confidence": float(forecast["confidence"]),
                "confidence_without_cited_evidence": float(
                    report["confidence_after_removal"]
                ),
                "confidence_drop": drop,
                "temporal_validity": temporal_validity,
                "evidence_support": float(report["evidence_support"]),
                "faithfulness_label": faithfulness_label(drop, temporal_validity),
                "counterevidence_coverage": float(
                    coverage["counterevidence_coverage"]
                ),
                "counterevidence_detected": bool(
                    coverage["counterevidence_detected_rate"] == 1.0
                ),
            }
        )
        sufficiency_rows.append(
            {
                **base,
                "prediction": forecast["prediction"],
                "original_confidence": float(forecast["confidence"]),
                "sufficiency_confidence": float(suff["sufficiency_confidence"]),
                "sufficiency_score": float(suff["sufficiency_score"]),
                "prediction_on_only_cited": suff["prediction_on_only_cited"],
                "counterfactual_confidence": float(
                    suff["counterfactual_confidence"]
                ),
                "counterfactual_delta": float(suff["counterfactual_delta"]),
            }
        )
        market_rows.append(
            {
                **base,
                "prediction": forecast["prediction"],
                "next_day_return": market["next_day_return"],
                "price_5d_return": market["price_5d_return"],
                "market_consistent": bool(market["market_consistent"]),
                "regime": market["regime"],
                "market_consistency_score": float(
                    market["market_consistency_score"]
                ),
            }
        )
        leakage_rows.extend(
            {
                **base,
                "news_id": n["news_id"],
                "news_time": n["news_time"],
                "news_text": _news_text(n),
                "leakage_minutes": compute_leakage_minutes(
                    str(n["news_time"]), sample["forecast_time"]
                ),
                "leakage_type": "future_news",
            }
            for n in sample["invalid_future_news"]
        )

    return {
        "prediction_results": prediction_rows,
        "evidence_results": evidence_rows,
        "faithfulness_results": faithfulness_rows,
        "sufficiency_results": sufficiency_rows,
        "market_consistency_results": market_rows,
        "temporal_leakage_results": leakage_rows,
    }


_FILE_COLUMNS: Dict[str, Tuple[str, ...]] = {
    "prediction_results": PREDICTION_COLUMNS,
    "evidence_results": EVIDENCE_COLUMNS,
    "faithfulness_results": FAITHFULNESS_COLUMNS,
    "sufficiency_results": SUFFICIENCY_COLUMNS,
    "market_consistency_results": MARKET_COLUMNS,
    "temporal_leakage_results": LEAKAGE_COLUMNS,
}


def _write_csv(
    rows: List[Dict[str, Any]], columns: Tuple[str, ...], path: Path
) -> None:
    """Write ``rows`` to ``path`` enforcing the given column order.

    Empty ``rows`` yields a header-only CSV so the file is always
    present and schema-correct. ``lineterminator="\\n"`` keeps the byte
    output identical to the old pandas writer.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in columns})


def export(envelope: Dict[str, Any], output_dir: str) -> Dict[str, str]:
    """Write the six CSVs to ``output_dir``; returns name -> path."""
    out = Path(output_dir)
    tables = build_rows(envelope)
    written: Dict[str, str] = {}
    for name, rows in tables.items():
        path = out / f"{name}.csv"
        _write_csv(rows, _FILE_COLUMNS[name], path)
        written[name] = str(path)
    return written


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"src.{STAGE_NAME}",
        description="Export the final envelope to the six result CSVs.",
    )
    parser.add_argument("--input", required=True, help="Path to the final envelope.")
    parser.add_argument(
        "--output-dir", required=True, help="Directory for the six CSVs."
    )
    args = parser.parse_args(argv)
    try:
        envelope = load_envelope(args.input, stage=STAGE_NAME)
    except EnvelopeError as exc:
        print(f"src.{STAGE_NAME}: {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT
    written = export(envelope, args.output_dir)
    for name, path in written.items():
        print(f"src.{STAGE_NAME}: {name}.csv -> {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())