## Why

Tiêu chí B4 yêu cầu minh chứng rằng dự án áp dụng **Agentic SDLC** — quy trình phát triển phần mềm có sự tham gia của AI agent với ít nhất 3 vai trò khác nhau, có trace log, quality gate, và reflection. Hiện tại pipeline không có cơ chế ghi lại quá trình agent làm việc (proposal, code, review) hay quality gate pass/fail, nên cần bổ sung để đáp ứng tiêu chí chấm điểm.

## What Changes

- Tạo module mới `src/agent_trace.py` với 3 hàm: `write_trace_entry()`, `load_trace_log()`, `summarize_trace()`.
- Tạo seed file `outputs/run_log.json` ghi lại 3+ agent role đã thực sự làm việc trong dự án (Research → Coding → Testing/Review), cùng với human review và quality gate status.
- Dashboard thêm tab "Agentic SDLC" hiển thị bảng trace log, quality gate statistics, và reflection notes.
- Thêm `reflection.md` vào change này mô tả AI agent đã đóng vai trò gì trong từng giai đoạn SDLC.

## Capabilities

### New Capabilities

- `agentic-sdlc-trace`: Module `src/agent_trace.py` cho phép ghi/đọc trace log (`outputs/run_log.json`) và tổng hợp thống kê (passed/failed quality gates, agent role distribution). Dashboard render tab "Agentic SDLC" từ trace log.

### Modified Capabilities

*(không có — không thay đổi schema output cũ)*

## Impact

- **`src/agent_trace.py`** (mới): pure functions, không IO ngoại trừ đọc/ghi `run_log.json`.
- **`outputs/run_log.json`** (mới): seed data ghi lại lịch sử agent trace của dự án này.
- **`openspec/changes/phase-b4-agentic-sdlc-maturity/reflection.md`** (mới): reflection document mô tả agentic SDLC workflow.
- **`src/dashboard/data_loader.py`**: thêm `load_agent_trace()` đọc `run_log.json`.
- **`src/dashboard/components.py`**: thêm `render_agentic_sdlc_tab()`.
- **`src/dashboard/app.py`**: thêm tab "Agentic SDLC".
- **`tests/test_agent_trace.py`** (mới): unit tests cho module.
- Không thay đổi bất kỳ pipeline output CSV hiện có.
