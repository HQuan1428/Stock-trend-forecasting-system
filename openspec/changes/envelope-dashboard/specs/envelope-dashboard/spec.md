# Spec: Envelope Dashboard

## ADDED Requirements

### Requirement: Dashboard đọc envelope read-only

Dashboard SHALL đọc duy nhất `outputs/08_market.json` (envelope cuối), validate từng sample bằng `schema.validate_sample(sample, "export_csv")`. Dashboard MUST NOT ghi/sửa bất kỳ file nào trong `outputs/`, MUST NOT gọi stage/pipeline, và MUST NOT re-run model.

#### Scenario: Envelope hợp lệ

- **WHEN** chạy `streamlit run src/dashboard/app.py` với `outputs/08_market.json` do runner sinh ra
- **THEN** dashboard render đủ 6 tab và không file nào trong `outputs/` bị thay đổi

#### Scenario: Thiếu envelope

- **WHEN** `outputs/08_market.json` không tồn tại hoặc không phải JSON hợp lệ
- **THEN** dashboard hiển thị message lỗi hướng dẫn chạy `python -m src.runner`, không crash, không traceback

### Requirement: Live Demo theo kịch bản demo 5 phút

Tab Live Demo SHALL thực hiện tuần tự kịch bản ChuDe1.md §11.1: chọn một ticker → chọn một forecast_time (lọc theo ticker) → hiển thị bảng valid_news (kèm `news_time`) → hiển thị prediction UP/DOWN/HOLD + confidence + phân rã class_confidences → hiển thị cited evidence (pro/counter) kèm thời gian xuất bản và rationale → toggle "Remove cited evidence" hiển thị confidence trước/sau và prediction sau ablation (số liệu lấy từ `faithfulness` đã tính sẵn) → banner kết luận faithful theo verdict.

#### Scenario: Demo một sample có evidence

- **WHEN** người dùng chọn ticker AAPL và một forecast_time có evidence cited
- **THEN** thấy đủ: bảng valid_news, prediction + confidence, danh sách evidence kèm news_time, rationale; bật toggle thì thấy confidence trước/sau và banner kết luận

#### Scenario: Cảnh báo tin tương lai trong demo

- **WHEN** sample được chọn có `invalid_future_news` không rỗng
- **THEN** tab hiển thị banner cảnh báo nêu số tin bị loại và độ trễ (leakage minutes) của từng tin

#### Scenario: Acceptance criteria §4.2 — prediction DOWN

- **WHEN** người dùng chọn một sample có prediction DOWN và evidence ủng hộ
- **THEN** hiển thị ít nhất 1 evidence có `expected_direction = DOWN` kèm thời gian xuất bản của nó

### Requirement: Bốn hình bắt buộc A7 + radar

Dashboard SHALL có đủ: (1) bar chart prediction distribution, (2) bảng evidence toàn dataset có filter (ticker/role/cited), (3) confidence drop chart per sample tô màu theo faithfulness_label HIGH/MEDIUM/LOW (dùng `export_csv.faithfulness_label`, không định nghĩa lại ngưỡng), (4) cảnh báo temporal leakage (banner mức độ + bảng tin vi phạm sort theo leakage_minutes giảm dần, tính bằng `export_csv.compute_leakage_minutes`), và (5) radar chart 5 trục: temporal_validity, evidence_support, normalized_drop, sufficiency_score, counterevidence_coverage.

#### Scenario: Đủ hình trên dữ liệu thật

- **WHEN** dashboard chạy trên envelope 100 samples của `data/sample_dataset.csv`
- **THEN** cả 5 hình/bảng trên đều render với dữ liệu không rỗng (leakage table có 21 dòng)

### Requirement: Panel B-metrics

Dashboard SHALL hiển thị: B1 — phân bố sufficiency_score và counterfactual_delta; B2 — phân bố counterevidence_coverage và tỉ lệ detected; B3 — tỉ lệ market_consistent và breakdown regime bull/bear/sideways; B4 — summary trace log qua `agent_trace.load_trace_log`/`summarize_trace`, hiển thị `st.info` hướng dẫn khi log không tồn tại (không lỗi).

#### Scenario: B4 không có trace log

- **WHEN** `outputs/run_log.json` không tồn tại
- **THEN** panel B4 hiển thị message hướng dẫn thay vì lỗi, các panel B1–B3 vẫn render bình thường

### Requirement: Logic tách khỏi lớp render

Toàn bộ logic load/tổng hợp/dựng figure SHALL nằm trong hàm thuần (`data_loader.py`, `metrics.py`, `charts.py`) import và test được bằng pytest mà không cần Streamlit server. `app.py`/`components.py` chỉ gọi `st.*` để render.

#### Scenario: Test không cần server

- **WHEN** chạy `pytest tests/test_dashboard_*.py`
- **THEN** toàn bộ test pass mà không khởi động Streamlit server hay browser
