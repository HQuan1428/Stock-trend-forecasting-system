## Why

The faithful evidence-centric financial news forecasting project now has six independently implemented and tested stages — Temporal Retriever, Evidence Extractor, Evidence Selector, Forecast Model, Faithfulness Metrics, and Visualization Dashboard — but no way to run them together. A reviewer must hand-wire `read_csv → group → retriever → extractor → selector → forecast → faithfulness → write_csv` for every run, and the sample dataset (`data/sample_dataset.csv`) has never been exercised end-to-end. We need a single command that takes raw news rows in, runs every stage in order, and writes the four CSVs the dashboard already expects to `outputs/`. The dashboard already exists and is read-only; this change does not change it, but it guarantees the four files it consumes are always produced by one reproducible command.

## What Changes

- Add `src/pipeline.py` as the single orchestration entry point. It groups rows by `(ticker, forecast_time)`, runs the six existing modules in order, and writes the four required output CSVs.
- Add `src/schema.py` with lightweight dataclasses for `NewsRecord`, `EvidenceItem`, `ForecastResult`, `FaithfulnessResult`, and `PipelineResult` so the data flow is explicit and the integration is testable without passing loose dicts between stages.
- Add a CLI entry point invoked as `python -m src.pipeline --input <csv> --output-dir <dir>` with `--forecast-time-column`, `--news-time-column`, `--ticker-column` overrides; defaults match `data/sample_dataset.csv` (`forecast_time`, `news_time`, `ticker`).
- Add a thin writer module (`src/pipeline/writers.py` or inline in `pipeline.py`) that materializes the four CSVs (`prediction_results.csv`, `evidence_results.csv`, `faithfulness_results.csv`, `temporal_leakage_results.csv`) with the column contracts documented in the spec.
- Reuse existing module APIs: `src.retriever.retrieve_valid_news`, `src.evidence_extractor.extract_evidence` / `extract_evidence_batch`, `src.evidence_selector.select_evidence` / `select_evidence_batch`, `src.forecast_model.predict` / `predict_batch` / `predict_without_evidence`, and `src.faithfulness_evaluator.FaithfulnessEvaluator` / `evaluate_batch`. No existing function is rewritten.
- Add `tests/test_pipeline.py` covering ten scenarios: runs without error, future-news exclusion, valid-news flow-through, all four output files created, confidence-drop finite value, `invalid_future_news_count > 0` for a group with future rows, dashboard contract columns present, batch vs single record equivalence, evidence-role labelling correctness, and a `data/sample_dataset.csv` smoke test.
- Update `README.md` with a "Run the pipeline" section showing the canonical command, the four output files, and a one-paragraph end-to-end description.
- No new heavy dependencies. `pandas` and `streamlit` are already in `requirements.txt`. No LLM, FinBERT, GPU, or external API.

### Non-goals

- Real-time streaming, authentication, or production deployment.
- Trading signals or any buy/sell recommendation logic.
- Replacing any existing module's algorithm — the rule-based retriever, extractor, selector, forecaster, and faithfulness evaluator are reused as black boxes.
- Changing the dashboard's column contract. The pipeline writes the columns the dashboard already consumes (post-adapter).
- Backtesting, hyperparameter search, or model accuracy improvements.

## Capabilities

### New Capabilities

- `end-to-end-forecasting-pipeline`: A single CLI-runnable pipeline that loads a news CSV, partitions rows by `(ticker, forecast_time)`, runs the six existing stages in order, and writes the four dashboard-ready output CSVs. Includes the orchestration module, the shared data-contract module, the CLI entry point, and the integration tests. The pipeline MUST never pass future news into the Evidence Extractor, Evidence Selector, Forecast Model, or Faithfulness Evaluator; future rows are only used for `temporal_leakage_results.csv` and `invalid_future_news_count`.

### Modified Capabilities

_None._ This change introduces a new capability. The existing `temporal-retriever`, `evidence-extractor`, `evidence-selector`, `forecast-model-basic`, `faithfulness-evaluator`, and `visualization-dashboard` specs are unaffected — the pipeline reuses their public APIs without changing requirements.

## Impact

- New code: `src/pipeline.py` (orchestrator + CLI), `src/schema.py` (shared dataclasses), and a writer helper (either inside `pipeline.py` or as `src/pipeline/__init__.py` for the package).
- New tests: `tests/test_pipeline.py` with the ten scenarios above.
- New sample: optional, `data/sample_dataset.csv` is reused (no new fixture needed; the pipeline runs on it as the smoke test).
- Documentation: `README.md` gains a "Run the pipeline" section with the canonical command, output file table, and a one-paragraph end-to-end flow description.
- Dependencies: no new packages. `pandas` (CSV I/O), `numpy` (used transitively by existing modules) are already required.
- Downstream consumers: the dashboard (`src/dashboard/app.py`) is the only documented consumer of the four `outputs/*.csv` files. The pipeline guarantees those four files always exist after a run, removing the dashboard's missing-file warning in the happy path.
- Side-effects on existing tests: none. The pipeline reuses existing module APIs; existing tests for the retriever, extractor, selector, forecaster, faithfulness evaluator, and dashboard stay green.

## Agentic SDLC — AI Agent tham gia ở bước nào

Dự án sử dụng AI agent trong toàn bộ SDLC theo mô hình có kiểm soát:

| Bước SDLC | AI Agent hỗ trợ | Con người kiểm soát |
|-----------|----------------|---------------------|
| **Requirement** | Research Agent phân tích bài toán, đề xuất acceptance criteria, tạo `proposal.md` | Review proposal, xác nhận scope, reject nếu scope không hợp lý |
| **Design** | Research Agent đề xuất kiến trúc module, schema dữ liệu, viết `design.md` | Chọn thiết kế phù hợp, điều chỉnh API contract |
| **Implementation** | Coding Agent sinh code theo spec (`tasks.md`), implement từng task | Đọc hiểu code, chạy test thủ công, chỉnh sửa nếu cần |
| **Testing** | Testing/Review Agent sinh test case, chạy `pytest`, kiểm tra output CSV | Review test coverage, thêm edge case nếu thiếu |
| **Evaluation** | Review Agent phân tích kết quả, gợi ý metric, viết `reflection.md` | Không overclaim, ghi rõ limitation |
| **Operation** | Agent ghi trace log vào `outputs/run_log.json` | Xem trace log trên dashboard Agentic SDLC tab |

Ba agent role bắt buộc: **Research Agent**, **Coding Agent**, **Testing/Review Agent**. Mỗi run được ghi vào `outputs/run_log.json` với `quality_gate` và `human_review` status. Xem `openspec/changes/phase-b4-agentic-sdlc-maturity/reflection.md` để biết chi tiết.
