# Change: Interactive Stage CLI

## Why

Sau khi xóa `src/pipeline.py` (orchestrator monolithic) và dashboard, 8 module xử lý (A1–A7 + B1–B3) chỉ còn là các class Python thuần — không có cách nào chạy từng giai đoạn từ terminal, không chạy được end-to-end, và `schema.py` chỉ là tài liệu không kiểm tra gì. Cần biến mỗi giai đoạn thành một module tương tác được: chạy độc lập, inspect/chỉnh sửa được dữ liệu giữa các bước, và vẫn có một lệnh chạy trọn chuỗi cho demo.

## What Changes

- Thêm **per-stage CLI**: mỗi stage chạy độc lập `python -m src.<stage> --input <in>.json -o <out>.json`; output stage này là input stage sau.
- Thêm định dạng **accumulating JSON envelope**: một document `{"stage": ..., "samples": [...]}` đi qua chuỗi stage, mỗi stage chỉ bổ sung field vào sample, không xóa field của stage trước.
- Thêm stage mới `src/ingest.py`: đọc CSV đầu vào (stdlib `csv`, bỏ pandas), group theo `(ticker, forecast_time)` giữ thứ tự, sinh envelope đầu tiên.
- Nâng cấp `src/schema.py` từ tài liệu thành **validator thật** (stdlib-only): kiểm tra key/type của sample ở ranh giới mỗi stage, sai → exit code 2 với message rõ ràng.
- Thêm `src/stage_io.py`: helpers dùng chung cho CLI (load/dump envelope deterministic, argparse chung) — tránh lặp code ở 8 file stage.
- Thêm **thin runner** `src/runner.py`: orchestrator mỏng chạy end-to-end, gọi đúng các hàm `process()` mà CLI rời dùng (một code path duy nhất), ghi từng file JSON trung gian, hỗ trợ `--stop-after`.
- Thêm `src/export_csv.py`: bước cuối tùy chọn xuất các CSV kết quả như trước (prediction/evidence/faithfulness/sufficiency/market/leakage) phục vụ report.
- Mỗi stage module thêm 2 hàm `process(envelope) -> envelope` và `main(argv)` — **business logic của các class giữ nguyên 100%**.
- Cập nhật `CLAUDE.md`, `README.md` cho khớp kiến trúc mới.

## Capabilities

### New Capabilities

- `stage-envelope`: Định dạng accumulating JSON envelope và quy tắc schema validation ở ranh giới stage (key bắt buộc theo từng stage, exit code, tính deterministic của serialization).
- `stage-cli`: Contract CLI cho từng stage (`python -m src.<stage>`, tham số `--input`/`-o`, thứ tự chuỗi stage, hành vi khi input hỏng) bao gồm stage mới `ingest`.
- `pipeline-runner`: Thin orchestrator chạy end-to-end (`src/runner.py`) + xuất CSV (`src/export_csv.py`) — không re-implement logic stage, chỉ chain các `process()`.

### Modified Capabilities

<!-- Không có: business logic và requirement của các stage hiện hữu (evidence-extractor spec trong openspec/specs/) không đổi — chỉ thêm lớp adapter/CLI bên trên. -->

## Impact

- **Code mới**: `src/ingest.py`, `src/stage_io.py`, `src/runner.py`, `src/export_csv.py`.
- **Code sửa**: `src/schema.py` (thêm validators), 7 stage module hiện hữu (chỉ thêm `process()`/`main()` cuối file), `src/__init__.py` (export tối thiểu).
- **Docs**: `CLAUDE.md`, `README.md` viết lại phần Commands/Architecture.
- **Tests**: giữ nguyên 381 test hiện có; thêm `test_schema_validation.py`, `test_stage_cli.py`, `test_runner.py`.
- **Dependencies**: không thêm — vẫn chỉ `pytest` (ingest dùng stdlib `csv`).
- **Invariants giữ nguyên**: deterministic byte-for-byte, không ML/LLM/API, temporal validity bất khả xâm phạm, `TimeUtils` + `EvidenceExtractor.*_KEYWORDS` là single source of truth.
