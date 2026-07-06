## 1. Pipeline — wire compute_coverage()

- [x] 1.1 Trong `src/pipeline.py::_run_group()`, import `CLASSIFICATION_TABLE` từ `src.evidence_selector`
- [x] 1.2 Sau bước Evidence Selector (sau khi có `selector_result` và `forecast["prediction"]`), xây dựng `expected_labels` bằng cách áp dụng `CLASSIFICATION_TABLE[(prediction, expected_direction)]` cho từng candidate trong `selector_request["evidence_candidates"]`
- [x] 1.3 Gọi `compute_coverage(selector_result, expected_labels)` và lưu kết quả vào `coverage_result`
- [x] 1.4 Bổ sung 2 field vào `faithfulness_row` trong `_run_group()`:
  - `counterevidence_coverage`: `float(coverage_result["counterevidence_coverage"])`
  - `counterevidence_detected`: `bool(coverage_result["counterevidence_detected_rate"] == 1.0)`
- [x] 1.5 Cập nhật `FAITHFULNESS_COLUMNS` tuple trong `src/pipeline.py` — thêm `"counterevidence_coverage"` và `"counterevidence_detected"` ở cuối tuple

## 2. Data Loader — cập nhật column contract

- [x] 2.1 Trong `src/dashboard/data_loader.py`, thêm `"counterevidence_coverage"` và `"counterevidence_detected"` vào `FAITHFULNESS_COLUMNS` (hoặc nơi tương đương định nghĩa schema)
- [x] 2.2 Trong `_normalize_faithfulness()` (hoặc hàm load faithfulness tương đương), fill missing columns với default: `counterevidence_coverage → 0.0`, `counterevidence_detected → False` — đảm bảo CSV cũ không gây crash

## 3. Dashboard — hiển thị metric card

- [x] 3.1 Trong `src/dashboard/components.py::render_confidence_drop_tab()`, thêm 1 metric card hiển thị `avg_counterevidence_coverage = faithfulness_df["counterevidence_coverage"].mean()` (format: `"{:.0%}".format(value)`)
- [x] 3.2 Đặt metric card cùng hàng với các card faithfulness hiện có (HIGH/MEDIUM/LOW counts)

## 4. Tests

- [x] 4.1 Trong `tests/test_pipeline.py`, thêm assertion kiểm tra `faithfulness_results.csv` có cột `counterevidence_coverage` và `counterevidence_detected` sau khi chạy `run_pipeline()`
- [x] 4.2 Trong `tests/test_pipeline.py`, kiểm tra sample có cả UP/DOWN evidence cho cùng prediction: `counterevidence_detected == True`
- [x] 4.3 Trong `tests/test_pipeline.py`, kiểm tra sample chỉ có 1 chiều evidence: `counterevidence_detected == False`
- [x] 4.4 Trong `tests/test_dashboard_data_loader.py`, thêm test: load faithfulness CSV thiếu 2 cột mới → không raise, giá trị default là `0.0` / `False`

## 5. Verification

- [x] 5.1 Chạy `python -m src.pipeline --input data/sample_dataset.csv --output-dir outputs` — không có lỗi
- [x] 5.2 Kiểm tra `outputs/faithfulness_results.csv` có cột `counterevidence_coverage` và `counterevidence_detected`
- [x] 5.3 Chạy `pytest tests/ -v` — toàn bộ tests pass
