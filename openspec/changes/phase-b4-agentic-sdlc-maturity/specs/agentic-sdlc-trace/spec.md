## ADDED Requirements

### Requirement: agent_trace module provides write/read/summarize

`src/agent_trace.py` SHALL expose three public functions:

- `write_trace_entry(entry: dict, path: str) -> None`: append entry to JSON trace log. Creates file if absent.
- `load_trace_log(path: str) -> list[dict]`: return list of trace entries; return `[]` if file missing or unreadable.
- `summarize_trace(entries: list[dict]) -> dict`: return summary dict with fields `total`, `passed_quality_gates`, `failed_quality_gates`, `pass_rate`, `roles`, `human_accepted`, `human_rejected`.

Each trace entry MUST contain at least: `run_id` (str), `agent_role` (str), `task` (str), `output` (str), `human_review` (str: "accepted"/"rejected"), `quality_gate` (str: "passed"/"failed").

#### Scenario: write_trace_entry creates file when absent
- **WHEN** `write_trace_entry(entry, path)` is called and `path` does not exist
- **THEN** a new JSON file is created at `path` containing a single-element array

#### Scenario: write_trace_entry appends to existing file
- **WHEN** `write_trace_entry` is called twice with different entries on the same path
- **THEN** the file contains both entries in order

#### Scenario: load_trace_log returns empty list for missing file
- **WHEN** `load_trace_log(path)` is called and `path` does not exist
- **THEN** it returns `[]` and does NOT raise

#### Scenario: summarize_trace computes correct pass_rate
- **WHEN** `summarize_trace` is called with 4 entries (3 passed, 1 failed)
- **THEN** `pass_rate` is `0.75` and `passed_quality_gates` is `3`

#### Scenario: summarize_trace counts roles correctly
- **WHEN** entries include 2 "Research Agent" and 1 "Coding Agent"
- **THEN** `roles["Research Agent"]` is `2` and `roles["Coding Agent"]` is `1`

---

### Requirement: outputs/run_log.json seed covers 3+ agent roles

`outputs/run_log.json` SHALL exist and contain at least 9 entries covering:
- At least 3 distinct `agent_role` values: `"Research Agent"`, `"Coding Agent"`, `"Testing/Review Agent"`
- At least one entry per Phase (B1, B2, B3, B4) per role
- All entries SHALL have `quality_gate` = `"passed"` or `"failed"` and `human_review` = `"accepted"` or `"rejected"`

#### Scenario: run_log.json has minimum required entries
- **WHEN** `load_trace_log("outputs/run_log.json")` is called
- **THEN** it returns a list with at least 9 entries

#### Scenario: run_log.json covers all 3 agent roles
- **WHEN** `summarize_trace(entries)` is called on the seed log
- **THEN** `roles` dict contains keys for all three required agent roles

---

### Requirement: Dashboard renders Agentic SDLC tab

The dashboard SHALL include an "Agentic SDLC" tab that displays:
- Summary metric cards: total runs, quality gate pass rate, human acceptance rate.
- A table of all trace entries with columns: `run_id`, `agent_role`, `task`, `human_review`, `quality_gate`.
- A static reflection section describing the human-AI collaboration model.

#### Scenario: Agentic SDLC tab renders without crash
- **WHEN** `streamlit run src/dashboard/app.py` is opened and `run_log.json` exists
- **THEN** the "Agentic SDLC" tab renders without error

#### Scenario: Tab handles missing run_log.json gracefully
- **WHEN** `run_log.json` does not exist
- **THEN** the tab displays an informational message and MUST NOT raise
