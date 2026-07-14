## Why

Phase A và B1/B2 đánh giá tính faithful của evidence bằng cách đo confidence drop, sufficiency, và counterevidence coverage — nhưng chưa so sánh prediction với biến động giá thực tế và chưa phân tích hiệu quả dự báo theo chế độ thị trường (bull/bear/sideways). B3 bổ sung 2 metric này để hoàn thiện pipeline đánh giá faithful evidence.

## What Changes

- Thêm 3 cột mô phỏng vào `data/sample_dataset.csv`: `next_day_return`, `price_5d_return`, `volume_change` (dữ liệu synthetic, giữ prototype scope).
- Tạo module mới `src/market_analyzer.py` với 2 chức năng:
  - **Market Consistency**: so sánh prediction với dấu `next_day_return` → `market_consistent` (bool) + `market_consistency_score` (float 0.0/1.0).
  - **Regime Classification**: phân loại chế độ thị trường từ `price_5d_return` → `regime` (bull/bear/sideways).
- Pipeline ghi `outputs/market_consistency_results.csv` (8 cột) sau Faithfulness Evaluator.
- Dashboard thêm tab "Market Consistency" hiển thị accuracy-by-regime và bảng per-sample.
- Không thay đổi bất kỳ output CSV hiện có.

## Capabilities

### New Capabilities

- `market-consistency`: Đo mức độ prediction (UP/DOWN/HOLD) của mô hình khớp với biến động giá thực tế ngày hôm sau (`next_day_return`), và phân loại chế độ thị trường (`regime`) để thống kê accuracy theo regime trong dashboard.

### Modified Capabilities

*(không có — không thay đổi schema cũ)*

## Impact

- **`data/sample_dataset.csv`**: thêm 3 cột simulated market data — breaking nếu test nào check số cột chính xác (không có trong codebase hiện tại).
- **`src/market_analyzer.py`** (mới): module thuần pure-function, không IO, không external API.
- **`src/pipeline.py`**: thêm import và bước mới, ghi `market_consistency_results.csv`.
- **`src/dashboard/data_loader.py`**: thêm `MARKET_COLUMNS`, field `market` trong `DashboardData`.
- **`src/dashboard/components.py`**: thêm `render_market_tab()`.
- **`src/dashboard/app.py`**: thêm tab "Market Consistency".
- **`tests/test_market_analyzer.py`** (mới): unit tests cho module.
- **`tests/test_pipeline.py`**: thêm assertions cho `market_consistency_results.csv`.
