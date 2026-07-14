# Tasks: Envelope Dashboard

## 1. Data layer + metrics (T1)

- [x] 1.1 Tạo `src/dashboard/__init__.py` + `src/dashboard/data_loader.py`: `DashboardDataError`, `load_dashboard_data(path)` (đọc JSON, validate bằng `schema.validate_sample(s, "export_csv")`, build DataFrame samples / evidence / leakage), cache-friendly (hàm thuần nhận path)
- [x] 1.2 Tạo `src/dashboard/metrics.py`: prediction_distribution, accuracy (tổng + theo ticker), avg confidence/drop, verdict→banner mapping (text tiếng Việt), radar aggregates (5 trục), leakage severity (OK/Warning/Critical), B1/B2/B3 aggregates — tất cả hàm thuần; import `faithfulness_label` từ `src.export_csv` (áp ở data_loader)
- [x] 1.3 Viết `tests/test_dashboard_data_loader.py` (envelope hợp lệ / thiếu file / JSON hỏng / sample fail schema) + `tests/test_dashboard_metrics.py` (từng hàm tổng hợp trên fixture nhỏ dựng trong test)

## 2. Charts (T2)

- [x] 2.1 Tạo `src/dashboard/charts.py`: build_prediction_distribution_chart, build_confidence_drop_chart (màu theo HIGH/MEDIUM/LOW), build_faithfulness_radar_chart (5 trục), build_class_confidences_chart (Live Demo), build_sufficiency_chart + build_coverage_chart + build_regime_chart (B-metrics) — nhận data đã tổng hợp, trả go.Figure, tham khảo màu từ dashboard cũ trong git history
- [x] 2.2 Viết `tests/test_dashboard_charts.py`: mỗi builder trả Figure đúng loại trace, đúng số điểm dữ liệu, không đụng I/O

## 3. UI (T3)

- [x] 3.1 Tạo `src/dashboard/components.py`: banner cảnh báo leakage, metric row, bảng evidence có filter, banner verdict, khối so sánh confidence trước/sau
- [x] 3.2 Tạo `src/dashboard/app.py`: page config + load (st.cache_data theo mtime, bắt DashboardDataError → st.error + st.stop) + 6 tab (Live Demo, Overview, Evidence, Faithfulness, Temporal Leakage, B-metrics) theo design D1–D6
- [x] 3.3 Viết `tests/test_dashboard_app.py`: smoke import app module (không chạy server), test hàm chọn sample theo ticker/date, kiểm tra mọi verdict nội bộ đều có banner mapping

## 4. Deps + docs (T4)

- [x] 4.1 requirements.txt: thêm streamlit, plotly, pandas
- [x] 4.2 README.md: section Dashboard (lệnh chạy, 6 tab, cách export PNG bằng nút camera Plotly cho 4 figure §9) ; CLAUDE.md: command `streamlit run src/dashboard/app.py` + invariant dashboard read-only đọc envelope

## 5. Verification (T5)

- [x] 5.1 `pytest tests/` toàn bộ pass — 438 tests (410 cũ + 28 dashboard mới)
- [x] 5.2 Verify trên `outputs/` thật: server headless HTTP 200 không error log; AppTest thực thi app — 6 tab, 2 selectbox, toggle Remove-cited hoạt động, verdict banner render; §4.2 OK (sample DOWN có evidence DOWN kèm news_time); leakage 21 dòng; case 0 valid_news hiển thị banner giải thích
- [x] 5.3 Read-only OK (listing outputs/ trước/sau giống hệt); chạy từ cwd không có outputs/ → error banner hướng dẫn chạy runner, không traceback
