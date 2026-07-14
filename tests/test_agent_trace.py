"""Unit tests for src.core.agent_trace (B4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.agent_trace import load_trace_log, summarize_trace, write_trace_entry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(run_id: str, role: str, gate: str = "passed", review: str = "accepted") -> dict:
    return {
        "run_id": run_id,
        "agent_role": role,
        "task": f"Task for {run_id}",
        "output": f"Output for {run_id}",
        "human_review": review,
        "quality_gate": gate,
    }


# ---------------------------------------------------------------------------
# write_trace_entry
# ---------------------------------------------------------------------------


def test_write_creates_file_when_absent(tmp_path: Path) -> None:
    path = str(tmp_path / "trace.json")
    write_trace_entry(_make_entry("R001", "Research Agent"), path)
    assert Path(path).exists()
    entries = load_trace_log(path)
    assert len(entries) == 1
    assert entries[0]["run_id"] == "R001"


def test_write_appends_to_existing_file(tmp_path: Path) -> None:
    path = str(tmp_path / "trace.json")
    write_trace_entry(_make_entry("R001", "Research Agent"), path)
    write_trace_entry(_make_entry("R002", "Coding Agent"), path)
    entries = load_trace_log(path)
    assert len(entries) == 2
    assert entries[0]["run_id"] == "R001"
    assert entries[1]["run_id"] == "R002"


# ---------------------------------------------------------------------------
# load_trace_log
# ---------------------------------------------------------------------------


def test_load_returns_empty_list_when_file_missing(tmp_path: Path) -> None:
    result = load_trace_log(str(tmp_path / "nonexistent.json"))
    assert result == []


def test_load_returns_empty_list_for_malformed_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("NOT JSON", encoding="utf-8")
    assert load_trace_log(str(bad)) == []


def test_load_returns_empty_list_for_non_list_json(tmp_path: Path) -> None:
    path = tmp_path / "obj.json"
    path.write_text(json.dumps({"key": "value"}), encoding="utf-8")
    assert load_trace_log(str(path)) == []


# ---------------------------------------------------------------------------
# summarize_trace
# ---------------------------------------------------------------------------


def test_summarize_empty_entries() -> None:
    s = summarize_trace([])
    assert s["total"] == 0
    assert s["pass_rate"] == 0.0
    assert s["roles"] == {}


def test_summarize_pass_rate() -> None:
    entries = [
        _make_entry("R1", "Research Agent", gate="passed"),
        _make_entry("R2", "Coding Agent", gate="passed"),
        _make_entry("R3", "Testing/Review Agent", gate="passed"),
        _make_entry("R4", "Coding Agent", gate="failed"),
    ]
    s = summarize_trace(entries)
    assert s["total"] == 4
    assert s["passed_quality_gates"] == 3
    assert s["failed_quality_gates"] == 1
    assert s["pass_rate"] == pytest.approx(0.75)


def test_summarize_roles_count() -> None:
    entries = [
        _make_entry("R1", "Research Agent"),
        _make_entry("R2", "Research Agent"),
        _make_entry("R3", "Coding Agent"),
    ]
    s = summarize_trace(entries)
    assert s["roles"]["Research Agent"] == 2
    assert s["roles"]["Coding Agent"] == 1


def test_summarize_human_review_counts() -> None:
    entries = [
        _make_entry("R1", "Research Agent", review="accepted"),
        _make_entry("R2", "Coding Agent", review="accepted"),
        _make_entry("R3", "Testing/Review Agent", review="rejected"),
    ]
    s = summarize_trace(entries)
    assert s["human_accepted"] == 2
    assert s["human_rejected"] == 1
