## Why

Phase A chỉ tính `confidence_drop` khi xóa toàn bộ cited evidence — chưa trả lời được câu hỏi: *"Nếu chỉ dùng cited evidence thì mô hình có đủ để ra prediction không? Và nếu thay cited evidence bằng neutral thì confidence thay đổi bao nhiêu?"*. Đây là 2 metric bắt buộc của Phase B1 (0.75 điểm) để đánh giá sâu hơn tính faithful của evidence.

## What Changes

- Tạo module mới `src/sufficiency_evaluator.py` với 2 chức năng:
  - **Sufficiency**: chạy lại `predict()` chỉ với cited evidence → tính `sufficiency_confidence` và `sufficiency_score`.
  - **Counterfactual Perturbation**: thay cited evidence bằng neutral placeholder → chạy lại `predict()` → tính `counterfactual_confidence` và `counterfactual_delta`.
- Pipeline gọi `SufficiencyEvaluator` sau Faithfulness Evaluator, ghi ra `outputs/sufficiency_results.csv`.
- Dashboard thêm 1 tab "Sufficiency & Counterfactual" hiển thị kết quả.
- Không thay đổi `faithfulness_results.csv` hiện có.

## Capabilities

### New Capabilities

- `sufficiency-evaluation`: Đo mức độ cited evidence *đủ* để ra cùng prediction (sufficiency_score) và mức độ prediction thay đổi khi cited evidence bị thay bằng neutral (counterfactual_delta).

### Modified Capabilities

*(không có — faithfulness_results.csv không đổi schema)*

## Impact

- **`src/sufficiency_evaluator.py`** (mới): module thuần pure-function, không IO, reuse `src.forecast_model.predict`.
- **`src/pipeline.py`**: thêm bước 6.5 (sau Faithfulness Evaluator), ghi `sufficiency_results.csv` ra `outputs/`.
- **`src/dashboard/data_loader.py`**: thêm `sufficiency` DataFrame vào `DashboardData`.
- **`src/dashboard/components.py`**: thêm `render_sufficiency_tab()`.
- **`src/dashboard/app.py`**: thêm tab "Sufficiency" vào layout.
- **`tests/test_sufficiency_evaluator.py`** (mới): unit tests cho module.
- **`tests/test_pipeline.py`**: thêm assertions cho `sufficiency_results.csv`.
- Không breaking — file output mới, không sửa schema cũ.
