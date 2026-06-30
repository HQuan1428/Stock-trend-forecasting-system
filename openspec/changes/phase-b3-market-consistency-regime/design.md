## Context

Phase A–B2 đã có đủ metrics để đo tính faithful của evidence (confidence_drop, sufficiency, counterevidence_coverage). Phase B3 thêm góc nhìn bên ngoài: prediction có thực sự khớp với thực tế thị trường không? Và hiệu quả đó có phụ thuộc vào chế độ thị trường không?

Dữ liệu `sample_dataset.csv` hiện tại không có market data thực. Ta dùng dữ liệu simulated (synthetic) phù hợp với prototype scope.

## Goals / Non-Goals

**Goals:**
- Module `src/market_analyzer.py` thuần pure-function, deterministic, không IO.
- Pipeline ghi `outputs/market_consistency_results.csv` với 9 cột chuẩn.
- Dashboard có tab "Market Consistency" hiển thị market consistency rate và breakdown by regime.
- `sample_dataset.csv` được bổ sung 3 cột simulated market data.

**Non-Goals:**
- Không dùng real market data hoặc external price API.
- Không thay đổi bất kỳ output CSV hiện có.
- Không implement backtesting hay portfolio simulation.

## Decisions

**D1 — Simulated market data trong CSV, không trong code**

Thêm `next_day_return`, `price_5d_return`, `volume_change` vào `data/sample_dataset.csv` thay vì hard-code. Lý do: giữ pipeline đọc từ CSV như hiện tại; market_analyzer nhận dữ liệu qua `group_row` dict từ pipeline.

**D2 — Synthetic data generation strategy**

Mỗi (ticker, forecast_time) group trong `sample_dataset.csv` được gán:
- `next_day_return`: float ngẫu nhiên trong `[-0.05, +0.05]`, seeded bằng `hash(ticker + forecast_time) % 1000` để đảm bảo deterministic.
- `price_5d_return`: float ngẫu nhiên trong `[-0.04, +0.04]`, seeded tương tự.
- `volume_change`: float ngẫu nhiên trong `[-0.3, +0.3]` (informational, không dùng trong scoring).

Tất cả rows của cùng một group chia sẻ cùng giá trị (lấy từ row đầu tiên của group).

**D3 — Consistency thresholds**

Ngưỡng `±0.005` (0.5%) cho UP/DOWN, ngưỡng `±0.02` (2%) cho regime. Lý do:
- 0.5% loại bỏ noise nhỏ trong ngày — đây là mức thực tiễn phổ biến trong financial NLP.
- 2% cho regime — tương đương "significant trend" trong 5 ngày.

**D4 — MarketAnalyzer nhận group_row + prediction, không nhận selector_result**

```python
MarketAnalyzer.analyze(prediction, next_day_return, price_5d_return)
```
Nhận scalar values thay vì dict phức tạp để module độc lập hoàn toàn với Evidence Selector và Forecast Model.

**D5 — Pipeline fallback khi CSV thiếu market columns**

Nếu `next_day_return` / `price_5d_return` không có trong input CSV, pipeline dùng `0.0` làm default. `market_consistent = True` (vì HOLD matches 0.0), `regime = "sideways"`. Không raise exception.

**D6 — CSV schema 9 cột**

```
sample_id, ticker, forecast_time, prediction,
next_day_return, price_5d_return,
market_consistent, regime, market_consistency_score
```

`volume_change` không đưa vào output CSV (informational only, không tính score). Giữ output minimal.

## Risks / Trade-offs

**[Risk] Simulated data không reflect thực tế** → Acceptable: đây là academic prototype. Label rõ "synthetic" trong dashboard.

**[Risk] Hash-based seed cho `next_day_return` có thể có collision** → Low probability, và determinism quan trọng hơn uniqueness ở đây.

**[Risk] `next_day_return = 0.0` (default khi thiếu cột) → `market_consistent = True` cho HOLD** → Được ghi chú trong dashboard bằng informational message khi market data bị missing.

**[Risk] Thêm cột vào `sample_dataset.csv` có thể ảnh hưởng test đang check số cột** → Kiểm tra: không có test nào kiểm tra số cột CSV đầu vào, chỉ có test kiểm tra output columns.
