# Visualization Dashboard — Design

## Context

The Faithful Evidence-Centric Financial News Forecasting pipeline now produces four upstream result files (`outputs/prediction_results.csv` from the Forecast Model, `outputs/faithfulness_results.csv` from the Faithfulness Evaluator, plus the CSV outputs the Temporal Retriever and Evidence Extractor write). Reviewers currently open raw CSVs in a spreadsheet to understand what the prototype did — there is no way to (a) see at a glance how many `UP`/`DOWN`/`HOLD` predictions were emitted, (b) compare the cited evidence against the prediction, (c) check the confidence drop after ablation, or (d) spot temporal leakage rows.

The Visualization Dashboard is the final read-only layer. Version 1 is built with Streamlit + Plotly + Pandas. It is for academic visualization, debugging, demo, and report evidence only — not for trading decisions.

A **key constraint** shaping this design is that the proposal-defined CSV contracts do not exactly match what the current source code emits. See the "Contract-bridging adapter" decision below — the dashboard therefore contains an adapter layer that joins / derives the missing columns from current upstream outputs.

## Goals / Non-Goals

**Goals:**

- Render a 5-tab Streamlit dashboard (Overview, Evidence, Confidence Drop, Temporal Leakage, Case Detail) from the four upstream CSVs.
- Provide sidebar filters (ticker, prediction, faithfulness level, forecast date range, cited-only, leakage-only) that update every tab consistently.
- Surface the three required deliverables for grading requirement A7: prediction distribution, evidence table, confidence drop chart, and temporal leakage warning.
- Be runnable for demo with `streamlit run src/dashboard/app.py` and suitable for screenshots / report figures.
- Be deterministic and side-effect-free with respect to upstream artifacts (the dashboard MUST NOT mutate `outputs/`).
- Be testable: pure-function modules for validation, metrics, and filtering; thin Streamlit layer on top.

**Non-Goals:**

- Authentication, multi-user support, role-based access.
- Database storage, persistence, caching layer.
- Real-time streaming, websocket updates, auto-refresh.
- Trading recommendations, buy/sell signal generation, position sizing.
- LLM-based explanation generation inside the dashboard (the dashboard is rule-based + Plotly only).
- Full pipeline orchestration (the dashboard does not call the Forecast Model or Faithfulness Evaluator at runtime).
- Production deployment setup (Docker, HTTPS, k8s, secrets management).
- Internationalization, accessibility audit, mobile-first layouts.

## Decisions

### 1. Modular package layout under `src/dashboard/`

The existing codebase already uses `src/forecast_model.py`, `src/faithfulness_evaluator.py`, etc. (mostly flat, with one nested subpackage). Version 1 of the dashboard is split into a small `src/dashboard/` package because the module has six distinct concerns (loading, validating, metrics, charts, components, app glue) and a single 600-line file would hurt testability.

```
src/dashboard/
  __init__.py          # Public API re-exports
  app.py               # Streamlit entry point (only Streamlit imports here)
  data_loader.py       # CSV loaders + adapter (joins/derivations to proposal shape)
  validators.py        # Required-column assertions + DashboardDataError
  metrics.py           # Pure functions: distribution, accuracy, faithfulness levels
  charts.py            # Plotly chart builders (pure: take DataFrame, return Figure)
  components.py        # Streamlit UI primitives (tabs, sidebar, tables, badges)
```

**Why not a single `src/dashboard.py`?** A monolithic file would force unit tests to import Streamlit (slow, fragile) and would conflate IO (CSV reads) with pure logic (metric computation). The split lets us test 90% of the dashboard with plain `pytest` and only the thin `app.py` glue requires Streamlit's runtime.

**Alternatives considered:**

- *Single file (`src/dashboard.py`)* — rejected: hurts testability, makes the adapter layer harder to isolate, and the spec's "modular layout preferred over a single `src/dashboard.py`" instruction is explicit.
- *Three-file split (`app.py`, `data.py`, `ui.py`)* — rejected: too coarse; we still want to unit-test `metrics.py` and `charts.py` independently.

### 2. Contract-bridging adapter in `data_loader.py`

The proposal specifies column names that do not match the current source. `data_loader.py` therefore contains an adapter layer that resolves the four proposal-defined tables to either (a) direct file loads when the file already exists in the proposal shape, or (b) joins / derivations from the current upstream outputs.

Adapter details (matches the "Contract-mismatch caveat" table in `proposal.md`):

- `prediction_results.csv`: `valid_news_count` and `invalid_future_news_count` are not emitted by the Forecast Model. `data_loader` derives them by joining `evidence_results.csv` (synthesized below) on `sample_id` and counting rows where `is_temporally_valid == True/False`. `rationale` is joined from `prediction_results.json` when present.
- `faithfulness_results.csv`: the current evaluator emits `confidence_after_removal` (proposal name: `confidence_without_cited_evidence`) and `verdict` (proposal name: `faithfulness_label`). `data_loader` renames `confidence_after_removal` → `confidence_without_cited_evidence` and maps `verdict` ∈ {`strong_/moderate_/weak_/decorative_/invalid_/unsupported_`} to the high/medium/low label using the documented thresholds (`>= 0.20` high, `>= 0.05` medium, else low). The dashboard treats the verdict as a richer alias of the label.
- `evidence_results.csv`: does not exist as a single artifact. `data_loader` synthesizes it from `prediction_results.json`'s `pro_evidence` / `counter_evidence` / `up_evidence` / `down_evidence` / `neutral_evidence` lists, emitting one row per evidence snippet with the proposal columns.
- `temporal_leakage_results.csv`: does not exist as a separate file. `data_loader` synthesizes it from the `TEMPORAL_LEAKAGE_BLOCKED` warnings in `prediction_results.json`, emitting one row per `news_id` with `leakage_minutes` computed as `(news_time - forecast_time) / 60`.

The adapter is the single source of truth for the dashboard's column contract. Downstream code (charts, components) consumes only the proposal-shape tables. This means a future change to the Forecast Model's output shape can be absorbed in one file (`data_loader.py`) without touching the chart / component layer.

**Why an adapter instead of changing the Forecast Model?** The Forecast Model's CSV contract is the "wire format" between pipeline stages; changing it would break downstream consumers that already depend on it. The dashboard is a new consumer with its own contract; it should adapt to the producer rather than the other way around.

### 3. Pure-function separation: `metrics.py` and `charts.py` have no Streamlit imports

`metrics.py` exposes pure functions:

- `prediction_distribution(df) -> Dict[str, int]` — counts of UP/DOWN/HOLD.
- `accuracy(df) -> Optional[float]` — accuracy if `label` is present, else `None`.
- `average_confidence(df) -> float` — mean of `confidence`.
- `average_confidence_drop(df) -> float` — mean of `confidence_drop`.
- `temporal_leakage_count(df) -> int` — count where `is_temporally_valid == False` (or by `temporal_validity < 1.0`).
- `average_temporal_validity(df) -> float` — mean of `temporal_validity`.
- `classify_faithfulness_level(confidence_drop: float) -> str` — returns `"high"` / `"medium"` / `"low"` per the documented thresholds.
- `leakage_severity(count: int) -> str` — returns `"ok"` / `"warning"` / `"critical"` per the documented thresholds.

`charts.py` exposes pure Plotly builders:

- `build_prediction_distribution_chart(df) -> go.Figure`
- `build_confidence_drop_chart(df) -> go.Figure` (per-sample scatter, color = faithfulness level)
- `build_temporal_leakage_chart(df) -> go.Figure` (count by ticker)
- `build_accuracy_by_ticker_chart(df) -> go.Figure` (bar)

Charts take a `pandas.DataFrame` and return a `plotly.graph_objects.Figure`; they never call `st.plotly_chart`. The `components.py` module wraps each chart in a `st.plotly_chart(fig, ...)` call.

**Why pure?** Pure functions are trivially testable. A `test_build_confidence_drop_chart` test can assert that the figure has the expected traces, x-axis label, and color mapping without spinning up a Streamlit app.

### 4. Streamlit layout: sidebar + 5 tabs

```
┌──────────────────────────────────────────────────────────┐
│  Title: Faithful Evidence-Centric Forecasting — Dashboard│
│  Caption: Academic visualization, not a trading tool.     │
├──────────────┬───────────────────────────────────────────┤
│  Sidebar     │  Tabs:                                     │
│  - Ticker    │  [Overview] [Evidence] [Confidence Drop]   │
│  - Predict.  │  [Temporal Leakage] [Case Detail]         │
│  - Faithful. │                                            │
│  - Date range│  <tab content>                            │
│  - Cited only│                                            │
│  - Leakage   │                                            │
│    only      │                                            │
└──────────────┴───────────────────────────────────────────┘
```

The sidebar is built in `components.py::render_sidebar(filters) -> filters` and returns the active filter state. The 5 tabs are built in `components.py::render_tabs(...)`. `app.py` is the only file that imports `streamlit` and is the only file that calls `st.tabs(...)`.

The 6 filters are applied in `metrics.py::apply_filters(df, filters) -> DataFrame` so the same filter logic is exercised by both the Streamlit app and the unit tests.

### 5. Cited / invalid evidence highlighting

Evidence rows in the synthesized `evidence_results` carry `is_cited` (bool) and `is_temporally_valid` (bool). The Evidence tab renders the table with:

- A **green checkmark** in the `is_cited` column when cited, faded when not.
- A **red badge** in the `is_temporally_valid` column when invalid; green check when valid.
- An `evidence_role` column showing `pro` / `counter` / `neutral` with a colored chip.
- A `support_score` column rendered as a percentage with a colored progress bar (red < 0.5, yellow < 0.8, green ≥ 0.8).

The highlighting is implemented in `components.py::render_evidence_table(df)`. The DataFrame itself is unchanged; the rendering layer adds the visual cues.

### 6. Faithfulness level thresholds

The thresholds are the same as the proposal (consistent with the temporal-retriever + evidence-selector + faithfulness-evaluator cascade):

- `confidence_drop >= 0.20` → `high`
- `0.05 <= confidence_drop < 0.20` → `medium`
- `confidence_drop < 0.05` → `low`

The thresholds are exposed as module-level constants in `metrics.py`:

```python
FAITHFULNESS_HIGH_THRESHOLD = 0.20
FAITHFULNESS_MEDIUM_THRESHOLD = 0.05
LEAKAGE_WARNING_THRESHOLD = 1
LEAKAGE_CRITICAL_THRESHOLD = 3
```

Hard-coding them in one place makes the thresholds easy to find and adjust in code review.

### 7. Temporal leakage severity

The proposal's severity rule (0 → OK, 1–3 → Warning, > 3 → Critical) is implemented in `metrics.py::leakage_severity`. The Temporal Leakage tab shows a colored banner (green / yellow / red) plus the leakage table. When the count is 0, the banner says "No temporal leakage detected — all cited evidence has `news_time <= forecast_time`."

### 8. Case Detail flow

The Case Detail tab contains a `st.selectbox` populated with all `sample_id`s visible under the current filters. Selecting a `sample_id` renders:

1. Header: ticker, forecast time, label (or "unlabeled"), prediction, original confidence.
2. Cited evidence table (filtered to `is_cited == True`).
3. Ablation summary: confidence after removal, confidence drop, faithfulness level (with color).
4. Interpretation paragraph (template-based, not LLM-generated):

   > "The model predicted **{prediction}** with confidence **{original_confidence:.0%}**. After removing the {n} cited evidence items, confidence dropped by **{drop:.0%}** to **{after:.0%}**. This corresponds to **{level}** faithfulness — the cited evidence appears to be {supportive / decorative / adversarial}."

The interpretation template is a string constant in `components.py`; the `{placeholder}` values are filled in by `.format(...)`. No LLM call is made.

### 9. Missing / empty file handling

`data_loader.py::load_all(output_dir) -> DashboardData` returns a `DashboardData` dataclass. Each field is either a populated DataFrame, an empty DataFrame with the correct schema, or `None` (file missing). The Streamlit app checks each field and shows a `st.warning(...)` banner with the file path when a file is missing or empty. The dashboard never raises; the user always sees a friendly message.

`validators.py::assert_columns(df, required, file_label)` raises `DashboardDataError` (a `ValueError` subclass) when required columns are missing. The app catches `DashboardDataError` and renders it as a `st.error(...)` with the column list.

### 10. Test plan

Tests live in `tests/test_dashboard_data_loader.py`, `tests/test_dashboard_validators.py`, `tests/test_dashboard_metrics.py`, and `tests/test_dashboard_filters.py`. They cover:

- **Data loader**: 11 scenarios — each proposal-shaped table loads from a healthy fixture, each loads from a fixture with one missing column (raises `DashboardDataError`), each loads when the file is missing (returns `None` or empty), the adapter correctly synthesizes `valid_news_count` / `invalid_future_news_count` / `evidence_results` / `temporal_leakage_results` from current-shape fixtures.
- **Validators**: required-column assertion, friendly error messages, multi-file validation.
- **Metrics**: prediction distribution counts, accuracy when label present/absent, average confidence, average confidence drop, temporal leakage count, average temporal validity, faithfulness level classification (high/medium/low boundary cases), leakage severity (ok/warning/critical boundary cases).
- **Filters**: ticker filter, prediction filter, faithfulness-level filter, date-range filter, cited-only filter, leakage-only filter, and consistency — the same filter applied to two DataFrames produces consistent results.

Fixtures live in `samples/dashboard/` (three small CSV sets: healthy, leakage, faithfulness-label) and are also generated by a small `_generate_fixtures.py` helper so the regression is byte-stable.

## Risks / Trade-offs

- **Adapter complexity** — the adapter layer is non-trivial (joins, derivations, threshold mapping). If the Forecast Model's output shape changes, the adapter is the only file that needs to change, but the adapter itself is ~150 lines and has its own test surface. → Mitigation: keep the adapter small and well-tested; document each derivation inline; consider exporting a `DashboardData` dataclass so the adapter has one well-defined return type.

- **Streamlit is heavyweight for a "view-only" tool** — Streamlit pulls in a server, a WebSocket layer, and a JS frontend. For a static visualization, plain HTML + a few matplotlib charts would be smaller. → Mitigation: Streamlit is in `requirements.txt` already (per the proposal's note) and the team is already familiar with it. The trade-off is intentional: demo-ability > runtime weight for an academic prototype.

- **Plotly charts are not pixel-identical across versions** — minor Plotly upgrades can shift axis labels, hover tooltips, etc. → Mitigation: snapshot tests use a small tolerance (compare figure data, not pixels); the test asserts on `fig.data[0].x` / `fig.data[0].y` / `fig.data[0].marker.color` rather than the rendered image.

- **The dashboard is read-only by construction but a careless future edit could break that** — a developer could add a `to_csv` button that overwrites `outputs/`. → Mitigation: the spec explicitly forbids mutation; the test plan includes a `test_dashboard_does_not_mutate_outputs` that snapshots `outputs/` before and after running the dashboard's data loader and asserts the two snapshots are equal.

- **The contract mismatch between the proposal and the current source is a paper-cut, not a show-stopper, but it is worth flagging in the README** — a future reader of the OpenSpec change may wonder why the dashboard's column contract doesn't match the Forecast Model's. → Mitigation: the proposal's "Contract-mismatch caveat" section documents this; the design restates it; the README will add a one-paragraph "Adapter layer" note explaining the bridge.

- **Streamlit reruns the entire script on every widget change** — with the 5 tabs and 6 filters, this can feel slow on large datasets (e.g., 10k rows). → Mitigation: cache the data load with `@st.cache_data` (Streamlit's standard pattern); cache the chart build with `@st.cache_data` keyed on the filtered DataFrame's hash. The cache survives across reruns and is invalidated only when the underlying file changes.

## Migration Plan

Not applicable — this is a new module. There is nothing to migrate. The dashboard is additive: it reads existing files and writes nothing.

## Open Questions

- **Should the dashboard auto-refresh on file change?** No for V1. Streamlit's file watcher is unreliable across platforms. Users can hit the "Rerun" button or refresh the browser. If V2 needs real-time, add `st.experimental_fragment` and a manual refresh button.

- **Should the dashboard support exporting filtered tables as CSV?** Tabled for V2. V1 is read-only with respect to disk.

- **Should the dashboard support dark mode?** Streamlit supports it via `config.toml`. V1 uses the default light theme for screenshot consistency in the final report. V2 can add dark mode if requested.
