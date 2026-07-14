# Change: Envelope Dashboard

## Why

A7 (1.0 điểm bắt buộc trong ChuDe1.md) yêu cầu dashboard chạy được với tối thiểu 4 bảng/hình, và §11.1 yêu cầu kịch bản demo 5 phút tương tác (chọn ticker/date → xem tin hợp lệ → prediction → evidence → "Remove cited evidence" → kết luận faithful). Dashboard cũ đã bị xóa khi dọn repo; kiến trúc mới (accumulating envelope) đã chạy ra output thật trong `outputs/` nhưng chưa có lớp trực quan hóa nào — B1–B4 cũng chưa có chỗ thể hiện.

## What Changes

- Thêm package `src/dashboard/` (Streamlit + Plotly): `app.py` (entry, 6 tab), `data_loader.py` (load + validate envelope, build view-model thuần), `metrics.py` (tổng hợp thuần), `charts.py` (Plotly figure builders thuần), `components.py` (khối UI tái dùng).
- **Data source duy nhất**: `outputs/08_market.json` (envelope cuối, chứa toàn bộ state mọi stage) — không join CSV, không adapter.
- 6 tab: **Live Demo** (kịch bản §11.1 với toggle "Remove cited evidence" dùng số liệu ablation đã tính sẵn), **Overview** (prediction distribution + accuracy), **Evidence** (bảng evidence có filter), **Faithfulness** (confidence drop chart + radar 5 trục), **Temporal Leakage** (banner + bảng cảnh báo), **B-metrics** (B1 sufficiency, B2 coverage, B3 market/regime, B4 agent trace).
- Thêm lại dependencies: `streamlit`, `plotly`, `pandas`.
- Cập nhật `README.md` (section Dashboard + cách export figure PNG cho báo cáo) và `CLAUDE.md` (command + invariant dashboard).

## Capabilities

### New Capabilities

- `envelope-dashboard`: Lớp trực quan hóa read-only trên envelope cuối — contract dữ liệu vào (validate bằng `schema.validate_sample`), 6 tab với nội dung bắt buộc theo A7/§9/§11.1/§4.2, hành vi khi thiếu/hỏng input, và invariant read-only (không mutate `outputs/`, không gọi pipeline, không re-run model).

### Modified Capabilities

<!-- Không có: các stage và envelope format không đổi — dashboard chỉ là consumer read-only. -->

## Impact

- **Code mới**: `src/dashboard/` (5 file). Không sửa stage/schema/runner nào.
- **Reuse, không viết lại**: `export_csv.faithfulness_label` + `compute_leakage_minutes`, `schema.validate_sample`, `agent_trace.load_trace_log`/`summarize_trace`.
- **Dependencies**: requirements.txt thêm streamlit/plotly/pandas (pipeline core vẫn stdlib-only — deps chỉ phục vụ lớp trực quan).
- **Tests**: thêm `test_dashboard_data_loader.py`, `test_dashboard_metrics.py`, `test_dashboard_charts.py`, `test_dashboard_app.py` — logic nằm ở hàm thuần nên test không cần chạy Streamlit server.
- **Docs**: README.md, CLAUDE.md.
