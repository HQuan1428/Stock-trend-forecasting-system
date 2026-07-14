"""Shared envelope I/O and CLI plumbing for the per-stage commands.

Every stage command (``python -m src.<stage>``) reads an envelope JSON
file, calls the stage's pure ``process(envelope)`` function, and writes
the enriched envelope back out. This module owns the three shared
pieces so the stage modules stay ~10 lines of CLI code each:

- :func:`load_envelope` — read + validate at the stage boundary; any
  problem (missing file, bad JSON, schema violation) prints a clear
  message to stderr and exits with code 2. Internal bugs still raise.
- :func:`dump_envelope` — deterministic serialization: ``sort_keys``,
  ``indent=2``, ``ensure_ascii=False``, trailing newline. The same
  envelope always produces byte-identical files.
- :func:`build_stage_parser` / :func:`run_stage_cli` — the shared
  argparse surface (``--input`` / ``-o``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.core.schema import validate_sample

EXIT_INVALID_INPUT = 2


class EnvelopeError(Exception):
    """Raised when an envelope file cannot be loaded or fails validation."""


def load_envelope(path: str, stage: Optional[str] = None) -> Dict[str, Any]:
    """Load an envelope JSON file, validating each sample for ``stage``.

    ``stage`` is the stage about to run (a key of
    ``schema.REQUIRED_SAMPLE_KEYS``); pass ``None`` to skip per-sample
    validation (used by ``ingest`` which reads CSV, not envelopes).

    Raises:
        EnvelopeError: file missing, unparseable JSON, wrong top-level
            shape, or any sample failing ``validate_sample``.
    """
    path_obj = Path(path)
    if not path_obj.exists():
        raise EnvelopeError(f"input file not found: {path}")
    try:
        data = json.loads(path_obj.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EnvelopeError(f"input is not valid JSON: {path} ({exc})") from exc
    if not isinstance(data, dict) or not isinstance(data.get("samples"), list):
        raise EnvelopeError(
            f'envelope must be an object with a "samples" list: {path}'
        )
    if stage is not None:
        errors: List[str] = []
        for sample in data["samples"]:
            errors.extend(validate_sample(sample, stage))
        if errors:
            raise EnvelopeError(
                f"envelope failed validation for stage {stage!r}:\n  "
                + "\n  ".join(errors)
            )
    return data


def dump_envelope(envelope: Dict[str, Any], path: str) -> None:
    """Write ``envelope`` to ``path`` deterministically."""
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    path_obj.write_text(
        json.dumps(envelope, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def build_stage_parser(stage_name: str, description: str) -> argparse.ArgumentParser:
    """Return the shared ``--input`` / ``-o`` parser for a stage command."""
    parser = argparse.ArgumentParser(prog=f"src.{stage_name}", description=description)
    parser.add_argument("--input", required=True, help="Path to the input file.")
    parser.add_argument(
        "-o", "--output", required=True, help="Path to write the output envelope JSON."
    )
    return parser


def run_stage_cli(
    stage_name: str,
    description: str,
    process: Callable[[Dict[str, Any]], Dict[str, Any]],
    argv: Optional[List[str]] = None,
) -> int:
    """Standard CLI body shared by every envelope-in/envelope-out stage."""
    args = build_stage_parser(stage_name, description).parse_args(argv)
    try:
        envelope = load_envelope(args.input, stage=stage_name)
    except EnvelopeError as exc:
        print(f"src.{stage_name}: {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT
    result = process(envelope)
    dump_envelope(result, args.output)
    print(f"src.{stage_name}: ok ({len(result['samples'])} samples) -> {args.output}")
    return 0


__all__ = [
    "EXIT_INVALID_INPUT",
    "EnvelopeError",
    "build_stage_parser",
    "dump_envelope",
    "load_envelope",
    "run_stage_cli",
]