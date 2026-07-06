"""Agentic SDLC Trace Log (B4).

Provides three public functions for managing a JSON trace log that records
the AI-agent actions taken during the development lifecycle of this project.

The trace log captures:
- Which agent role performed the work (Research / Coding / Testing-Review)
- What task was performed and what was produced
- Whether a human reviewed and accepted the output
- Whether the quality gate (pytest, pipeline, spec review) passed

All functions are pure with respect to logic; only write_trace_entry does IO.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

#: Default trace log path (relative to project root when invoked via CLI).
DEFAULT_LOG_PATH: str = "outputs/run_log.json"

#: Required fields for every trace entry.
REQUIRED_FIELDS: tuple = (
    "run_id",
    "agent_role",
    "task",
    "output",
    "human_review",
    "quality_gate",
)

#: Valid values for quality_gate field.
VALID_QUALITY_GATES = ("passed", "failed")

#: Valid values for human_review field.
VALID_HUMAN_REVIEWS = ("accepted", "rejected")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_trace_entry(
    entry: Dict[str, Any],
    path: str = DEFAULT_LOG_PATH,
) -> None:
    """Append ``entry`` to the JSON trace log at ``path``.

    Creates the file (and parent directories) if absent.
    Reads the existing array, appends, and writes back atomically-enough
    for single-process prototype use.
    """
    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_trace_log(path)
    existing.append(entry)
    with log_path.open("w", encoding="utf-8") as fh:
        json.dump(existing, fh, ensure_ascii=False, indent=2)


def load_trace_log(path: str = DEFAULT_LOG_PATH) -> List[Dict[str, Any]]:
    """Return the list of trace entries from ``path``.

    Returns ``[]`` when the file is missing, unreadable, or malformed —
    never raises.
    """
    log_path = Path(path)
    if not log_path.exists():
        return []
    try:
        with log_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [e for e in payload if isinstance(e, dict)]


def summarize_trace(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute summary statistics over a list of trace entries.

    Returns a dict with:
    - ``total`` (int): number of entries
    - ``passed_quality_gates`` (int)
    - ``failed_quality_gates`` (int)
    - ``pass_rate`` (float): passed / total, or 0.0 when total == 0
    - ``roles`` (dict[str, int]): count per agent_role
    - ``human_accepted`` (int)
    - ``human_rejected`` (int)
    """
    total = len(entries)
    passed = sum(1 for e in entries if e.get("quality_gate") == "passed")
    failed = sum(1 for e in entries if e.get("quality_gate") == "failed")
    accepted = sum(1 for e in entries if e.get("human_review") == "accepted")
    rejected = sum(1 for e in entries if e.get("human_review") == "rejected")

    roles: Dict[str, int] = {}
    for e in entries:
        role = e.get("agent_role", "Unknown")
        roles[role] = roles.get(role, 0) + 1

    return {
        "total": total,
        "passed_quality_gates": passed,
        "failed_quality_gates": failed,
        "pass_rate": passed / total if total > 0 else 0.0,
        "roles": roles,
        "human_accepted": accepted,
        "human_rejected": rejected,
    }
