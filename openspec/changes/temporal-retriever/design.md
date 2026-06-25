## Context

The project "Faithful Evidence-Centric Financial News Forecasting" predicts stock movement from financial news and evaluates whether the cited evidence is relevant, temporally valid, and faithful to each prediction. A forecast is generated at a specific moment in time — `forecast_time`. Any news article published **after** that moment could not, by definition, have been available to a market participant at the forecast instant. If such "future news" leaks into the Evidence Extractor or Forecast Model, the model is effectively peeking into the future. The resulting accuracy numbers, attention maps, and "explanations" become invalid — and worse, the prototype would teach students the wrong lesson about how real forecasting systems must respect causality.

The pipeline order is:

```
News -> Temporal Retriever -> Evidence Extractor -> Evidence Selector -> Forecast Model -> Faithfulness Evaluator -> Dashboard
```

The Temporal Retriever is the **first** filtering module. It must guarantee that every later stage only ever sees news whose `news_time <= forecast_time`. Price data (if any) is loaded by the pipeline driver and is not an input to the retriever.

## Goals / Non-Goals

**Goals:**

- Guarantee temporal correctness: no future news reaches the Evidence Extractor.
- Provide a deterministic, rule-based, ML-free filter that a student can read in one sitting.
- Preserve every input item in the output (`valid_news`, `invalid_future_news`, or `errors`) for traceability.
- Produce structured counts and a derived `temporal_validity` ratio for the dashboard.
- Make leakage regressions reproducible via unit tests and sample data.

**Non-Goals:**

- Implementing the Evidence Extractor, Evidence Selector, Forecast Model, Faithfulness Evaluator, or Dashboard (these belong to later changes).
- Building a real-time news crawler or any external integration.
- Training or calling ML / LLM models.
- Cross-lingual or semantic normalization of news text.
- Authoritative timezone resolution across the world; we accept the documented UTC-as-project-local assumption below.

## Decisions

### Decision 1: Filter is purely rule-based, no ML/LLM

- **Rationale:** The filter is a binary classification by timestamp. An ML model would add cost, nondeterminism, training-data risk, and another way to leak future information. A simple `datetime.parse` + comparison is provably correct.
- **Alternatives considered:** (a) LLM-based filtering — rejected (cost, nondeterminism, opaque). (b) Database-level `WHERE` query — rejected (overkill for an in-memory student prototype).

### Decision 2: Run before every downstream module

- **Rationale:** Once future news reaches the Evidence Extractor, it can pollute embeddings, retrieved evidence lists, and forecast inputs. Filtering at the very front is the only way to make the guarantee hold end-to-end.
- **Alternatives considered:** (a) Filter inside the Evidence Extractor — rejected (scatters responsibility, easy to forget in new code paths).

### Decision 3: Preserve future news in `invalid_future_news`

- **Rationale:** Operators and the future dashboard need to see *which* news was filtered out and *why*. Silent deletion hides leakage and makes the faithfulness evaluator unable to penalize misuse. Preservation also makes it possible to debug "why is my temporal_validity low?" without rerunning the data pipeline.
- **Alternatives considered:** (a) Drop future news silently — rejected (defeats traceability, violates the spec). (b) Log to a side file — rejected (output should be self-contained).

### Decision 4: Behavior for malformed `news_time`

- **Chosen behavior:** Items with missing, empty, or unparseable `news_time` are **excluded from both groups** and reported in the output `errors` list as structured error objects (e.g. `{"news_id": "...", "reason": "missing_or_malformed_news_time", "raw_value": "..."}`). The retriever returns a normal output object — it does **not** raise — so a single bad row never aborts the pipeline.
- **Rationale:** A failing row should not block the rest of the dataset. Reporting it structurally is more useful for the dashboard than a raised exception, and keeps the retriever composable.
- **Alternatives considered:** (a) Raise `TemporalValidationError` and abort — rejected (one bad row would block all forecasting; bad UX for batch use). (b) Treat malformed timestamps as "ancient past" and place in `valid_news` — rejected (silently misleading, could feed the model with bogus evidence).

### Decision 5: Timezone handling — project-local timezone is UTC

- **Chosen behavior:**
  - **The project-local timezone is UTC.** Naive timestamps (no offset, e.g. `"2025-03-12 09:00"`) are interpreted as UTC.
  - If `forecast_time` carries an explicit timezone (e.g. `"2025-03-12T09:00:00+07:00"` or `"...Z"`), the retriever parses it as timezone-aware and converts to UTC before comparison.
  - Each `news_time` is parsed independently. If a `news_time` has a timezone and `forecast_time` does not (or vice versa), the retriever normalizes both to UTC by attaching the UTC offset to the naive value.
  - The module docstring MUST state "Project-local timezone: UTC" so the assumption is discoverable.
- **Rationale:** Financial data industry convention is UTC. UTC is deterministic (no DST) and aligns with how market timestamps are recorded in production systems. Rejecting all naive timestamps would force every consumer to switch to UTC-only and rewrite the existing data; treating naive as UTC is forgiving but unambiguous.
- **Alternatives considered:** (a) Reject any naive timestamp — rejected (breaks the existing sample data and forces a project-wide change beyond the retriever's scope). (b) Use Asia/Ho_Chi_Minh or another fixed offset — rejected (introduces DST-free local offset assumptions that differ from the rest of the financial-data ecosystem).

### Decision 6: Output preserves input order

- **Chosen behavior:** Both `valid_news` and `invalid_future_news` preserve the order in which items appeared in the input list. The retriever does **not** sort by `news_time`.
- **Rationale:** Sorting adds nondeterminism across equal timestamps and surprises downstream code that expects stream order. Order preservation matches the "filter, do not transform" intent.

### Decision 7: Filter by time only — ticker is metadata, not a filter

- **Chosen behavior:** The retriever filters strictly by time. If `ticker` is provided on the input, it is echoed into the response for downstream consumers to use, but the retriever does not subset the news list by ticker.
- **Rationale:** Mixing ticker filtering into the temporal filter complicates traceability and confuses the leakage question. A separate ticker filter (or a per-ticker pipeline call) belongs in a later change.

### Decision 8: Pure function with a small dataclass

- **Chosen behavior:** Expose `retrieve_valid_news(forecast_time, news, ticker=None) -> RetrievalResult` as a pure function. `RetrievalResult` is a small dataclass with the fields listed in the spec. No global state, no I/O.
- **Rationale:** Pure functions are easy to unit-test, easy to reuse from notebooks, and easy to reason about.

### Decision 9: Implementation lives in `src/retriever.py`

- **Rationale:** This matches the existing repository structure described in `AGENTS.md`, which already lists `src/retriever.py` as the home for this module.

### Decision 10: `temporal_validity` denominator includes malformed items

- **Chosen behavior:** `temporal_validity = valid_count / total_count`, where `total_count = len(news)` (the request payload length, including items that land in `errors`). This means a malformed item lowers `temporal_validity` even though it is not strictly "future news".
- **Rationale:** A low `temporal_validity` should signal data-quality issues broadly, not just temporal leakage. Splitting the ratio into `valid / (valid + invalid_future)` would hide malformed items from the dashboard and make "why is my validity 0.4?" harder to debug.
- **Alternatives considered:** (a) `valid_count / (valid_count + invalid_future_count)` — rejected (hides malformed items from observability). (b) Three-way ratio with `errors` — rejected (over-engineered for the baseline; a later change can add a `malformed_ratio` field without breaking this contract).

## Risks / Trade-offs

- **[Risk] Wrong timezone assumption** → Mitigation: the module docstring MUST state "Project-local timezone: UTC" so the assumption is discoverable; the sample dataset and tests are written against UTC. A follow-up change can introduce per-call `tz` overrides if needed.
- **[Risk] Malformed timestamp handling diverges from a "fail loud" culture** → Mitigation: malformed items are surfaced in `errors` (not swallowed), and a unit test asserts that the `errors` list is populated correctly. The dashboard can later visualize these.
- **[Risk] Datetime parser accepts too many formats** → Mitigation: the parser uses `datetime.fromisoformat` (with a small fallback for `" "` separators) and rejects everything else with a structured error. No fuzzy parsing.
- **[Risk] Future-dated news might be legitimate (delayed feeds)** → Mitigation: that is exactly what `invalid_future_news` is for. Downstream consumers and the dashboard can decide whether to warn, retry, or escalate.
- **[Risk] Single comparison bug breaks the entire guarantee** → Mitigation: a regression test specifically named for the temporal leakage scenario (1-second-in-the-future, equal timestamps, and 6-hours-in-the-future) is mandatory.

## Migration Plan

Not applicable for this change — there is no production deployment. The retriever is a new module; existing code paths do not yet depend on it. The rollout is:

1. Implement `src/retriever.py` and `TemporalValidationError`.
2. Add unit tests under `tests/test_temporal_retriever.py` and a dedicated regression suite under `tests/test_temporal_leakage.py`.
3. Verify the existing `data/sample_dataset.csv` already covers the three temporal scenarios (past / equal / future — rows 1, 2, 3). Add `data/README.md` mapping row IDs to scenario labels for downstream and human reference. (No CSV extension is needed.)
4. Verify `pytest tests/` passes and `openspec validate temporal-retriever` is green.

## Open Questions

- **Should the dashboard (later change) highlight `temporal_validity < 1.0` as a warning?** → Out of scope here; tracked as a dashboard requirement in a future change.
- **Should we later add an optional `lookback_window` argument?** → Out of scope. The current retriever only enforces "no future news", not "news from the last N hours". A future change can add lookback without breaking this contract.
- **Should `errors` be merged with `invalid_future_news` for the dashboard?** → Out of scope; keeping them separate is cleaner for downstream code. The dashboard change can decide how to render them.
