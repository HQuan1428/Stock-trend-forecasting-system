## 1. Module src/agent_trace.py

- [x] 1.1 Tạo file `src/agent_trace.py` với docstring mô tả mục đích (B4: Agentic SDLC trace log)
- [x] 1.2 Implement `write_trace_entry(entry: dict, path: str = "outputs/run_log.json") -> None` — đọc file hiện tại (hoặc `[]`), append entry, ghi lại
- [x] 1.3 Implement `load_trace_log(path: str = "outputs/run_log.json") -> list` — trả về list entries hoặc `[]` khi file missing/unreadable
- [x] 1.4 Implement `summarize_trace(entries: list) -> dict` — trả về dict với fields: `total`, `passed_quality_gates`, `failed_quality_gates`, `pass_rate`, `roles` (dict), `human_accepted`, `human_rejected`

## 2. Seed data: outputs/run_log.json

- [x] 2.1 Tạo `outputs/run_log.json` với ≥9 entries bao phủ 3 agent roles (Research Agent, Coding Agent, Testing/Review Agent) và 4 phases (B1, B2, B3, B4). Mỗi entry có đủ 6 required fields: `run_id`, `agent_role`, `task`, `output`, `human_review`, `quality_gate`. Thêm `timestamp`, `input`, `notes` tùy chọn.

## 3. Reflection document

- [x] 3.1 Tạo `openspec/changes/phase-b4-agentic-sdlc-maturity/reflection.md` mô tả:
  - 3 agent roles và nhiệm vụ cụ thể trong dự án
  - Con người kiểm soát bằng cách nào (approve spec, review, reject nếu cần)
  - Các quality gate đã áp dụng (pytest pass, pipeline no-error, spec review)
  - Bài học rút ra từ Agentic SDLC

## 4. Dashboard Data Loader

- [x] 4.1 Trong `src/dashboard/data_loader.py`, thêm hàm `load_agent_trace(output_dir: str) -> list` — đọc `run_log.json` từ `output_dir`, trả về `[]` nếu missing
- [x] 4.2 Thêm field `agent_trace: list` vào `DashboardData` dataclass (default `[]`)
- [x] 4.3 Trong `load_dashboard_data()`, gọi `load_agent_trace(output_dir)` và gán vào `data.agent_trace`

## 5. Dashboard UI

- [x] 5.1 Trong `src/dashboard/components.py`, thêm hàm `render_agentic_sdlc_tab(agent_trace: list)`:
  - Nếu `agent_trace` rỗng: hiện `st.info("No agent trace log found...")`
  - Hiện 3 metric card: total runs, quality gate pass rate, human acceptance rate
  - Hiện bảng trace log DataFrame với cột: `run_id`, `agent_role`, `task`, `human_review`, `quality_gate`
  - Hiện section "Reflection" với expander mô tả quy trình Agentic SDLC
- [x] 5.2 Trong `src/dashboard/app.py`, thêm tab "Agentic SDLC" và gọi `render_agentic_sdlc_tab(data.agent_trace)`
- [x] 5.3 Export `render_agentic_sdlc_tab` trong `__all__` của `components.py`

## 6. Tests

- [x] 6.1 Tạo `tests/test_agent_trace.py`:
  - Test `write_trace_entry` tạo file mới khi absent
  - Test `write_trace_entry` append vào file đã tồn tại
  - Test `load_trace_log` trả về `[]` khi file missing
  - Test `summarize_trace` tính đúng `pass_rate` và `roles`
  - Test `load_trace_log("outputs/run_log.json")` trả về ≥9 entries (integration với seed)
  - Test seed covers 3 agent roles bắt buộc

## 7. Verification

- [x] 7.1 Chạy `python3.14 -m src.pipeline --input data/sample_dataset.csv --output-dir outputs` — không lỗi (pipeline không đụng vào run_log.json)
- [x] 7.2 Kiểm tra `outputs/run_log.json` có ≥9 entries và 3 agent roles
- [x] 7.3 Chạy `pytest tests/ -v` — toàn bộ 546 tests pass
