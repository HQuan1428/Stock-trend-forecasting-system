# Design: Interactive Stage CLI

## Context

Repo hiện có 8 stage class thuần Python trong `src/` (retriever, evidence_extractor, evidence_selector, forecast_model, faithfulness_evaluator [+faithfulness_metrics], sufficiency_evaluator, market_analyzer) và `agent_trace.py` (B4, ngoài chuỗi runtime). Orchestrator cũ `src/pipeline.py::PipelineRunner` đã bị xóa; toàn bộ glue logic của nó vẫn xem lại được qua `git show HEAD:src/pipeline.py` (694 dòng, dùng pandas, ghi 6 CSV).

Người dùng đã chốt 3 quyết định:
1. CLI từng stage — mỗi stage một lệnh, JSON file làm handoff.
2. Vẫn giữ orchestrator mỏng cho end-to-end.
3. Schema validation thật ở ranh giới stage, stdlib-only.

## Goals / Non-Goals

**Goals:**
- Mỗi stage chạy độc lập từ terminal, dữ liệu trung gian inspect/chỉnh được bằng editor thường.
- Một code path duy nhất: CLI rời và runner cùng gọi `process(envelope)`.
- Fail sớm và rõ ràng ở ranh giới stage khi input sai format (exit code 2, message chỉ đích danh sample/key lỗi).
- Deterministic byte-for-byte: cùng input → cùng file output (JSON `sort_keys=True, indent=2`, CSV cột cố định).
- Không thêm dependency (requirements.txt giữ nguyên `pytest`).

**Non-Goals:**
- Không đổi business logic/thuật toán của bất kỳ stage class nào.
- Không REPL/interactive shell, không dashboard, không parallelism.
- Không enforce schema bằng thư viện ngoài (pydantic/jsonschema).
- `agent_trace.py` (B4) không trở thành runtime stage.

## Decisions

### D1: Accumulating envelope thay vì file rời từng stage-shape

Một document `{"stage": str, "samples": [...]}` đi xuyên chuỗi; mỗi stage bổ sung field vào sample (`valid_news`, `evidence`, `forecast`, ...), không xóa field cũ.

- **Vì sao**: user inspect được toàn bộ state tại mọi thời điểm; stage sau tự nhiên có đủ context (faithfulness cần cả input + forecast); tránh phải join nhiều file.
- **Alternative bị loại**: mỗi stage một shape input riêng biệt tối thiểu — ít dư thừa hơn nhưng bắt user tự join file, và glue logic phân tán khó kiểm.
- **Trade-off chấp nhận**: file trung gian to dần về cuối chuỗi (dataset mẫu 146 dòng → không đáng kể).

### D2: `process(envelope) -> envelope` là API chung của mọi stage

Mỗi stage module thêm hàm module-level `process()` (glue: dựng request cho class từ sample, gọi class, merge kết quả) và `main(argv)` (~10 dòng, dùng `stage_io`). Class giữ nguyên.

- **Vì sao**: runner import và gọi đúng hàm mà CLI dùng → không có 2 code path; test được `process()` thuần không cần subprocess.
- **Alternative bị loại**: glue tập trung trong runner (như `_run_group` cũ) — chính là kiến trúc monolithic vừa bỏ.
- `process()` phải pure + deterministic: không đọc/ghi file, không phụ thuộc thời gian thực.

### D3: Port glue từ pipeline cũ, không viết lại

Nguồn: `git show HEAD:src/pipeline.py`. Mapping:
- Dựng extractor input từ `valid_news` (bước 2 của `_run_group`) → `evidence_extractor.process`
- `_build_forecast_request` → `forecast_model.process`
- Dựng selector request + `expected_labels` cho B2 (bước 4/4b) → `evidence_selector.process`
- `_faithfulness_label` (HIGH ≥0.20 / MEDIUM ≥0.05 / LOW), `_build_evidence_rows`, `_compute_leakage_minutes`, các `*_COLUMNS` tuple → `export_csv.py`
- Grouping `(ticker, forecast_time)` giữ thứ tự + sinh `sample_id` (từ `PipelineRunner.run`) → `ingest.py`, thay pandas bằng stdlib `csv`.

### D4: Schema validation = bảng khai báo trong `schema.py`, không thư viện ngoài

`REQUIRED_SAMPLE_KEYS: dict[stage_name, dict[key, type]]` + `validate_sample(sample, stage) -> list[str]` (trả list message lỗi, không raise). `stage_io.load_envelope(path, stage)` gọi validator; có lỗi → in từng message ra stderr, exit 2. Dataclass hiện có giữ nguyên làm tài liệu.

- **Vì sao**: đủ bắt lỗi "nối sai stage" / "sửa tay làm hỏng file" — nhu cầu thật duy nhất; type-check sâu hơn không đáng thêm dependency.

### D5: Thứ tự chuỗi và tên file trung gian cố định

```
ingest → retriever → evidence_extractor → forecast_model
       → evidence_selector (B2) → faithfulness_evaluator
       → sufficiency_evaluator (B1) → market_analyzer (B3) → export_csv
```
Runner ghi `01_samples.json` … `08_market.json` vào `--output-dir`, rồi các CSV. Forecast chạy TRƯỚC selector (selector cần prediction) — đúng thứ tự pipeline cũ. `--stop-after <stage>` dừng sớm.

### D6: Exit codes

`0` thành công; `2` input không hợp lệ (file thiếu, JSON hỏng, schema fail); traceback bình thường cho bug nội bộ (không nuốt lỗi).

## Risks / Trade-offs

- [Kết quả lệch so với pipeline cũ khi port glue] → Verification bắt buộc: so `prediction_results.csv` mới với `git show HEAD:outputs/prediction_results.csv` — logic không đổi thì kết quả phải trùng.
- [`forecast_model.predict_batch` mặc định tự ghi `outputs/*.csv`] → `process()` gọi `predict()` per-sample (không gọi `predict_batch`), việc ghi file chỉ nằm ở `stage_io`/`export_csv`.
- [Envelope key trùng tên field có sẵn trong sample CSV] → namespace kết quả stage dưới key riêng (`forecast`, `selection`, `faithfulness`, ...) thay vì merge phẳng.
- [Drift giữa schema validator và output thật của stage] → test `test_stage_cli.py` xích các stage: output stage N phải pass validator của stage N+1.
