## 1. Enrich data/sample_dataset.csv với simulated market data

- [x] 1.1 Viết script một lần `scripts/add_market_data.py` (hoặc inline) để thêm 3 cột `next_day_return`, `price_5d_return`, `volume_change` vào `data/sample_dataset.csv` — dùng hash-based seed cho determinism (seed = `hash(ticker + str(forecast_time)) % 1000`)
- [x] 1.2 Chạy script và verify `data/sample_dataset.csv` có đủ 9 cột, mỗi group (ticker, forecast_time) nhận cùng giá trị

## 2. Module src/market_analyzer.py

- [x] 2.1 Tạo file `src/market_analyzer.py` với docstring mô tả mục đích (B3: Market Consistency + Regime Analysis)
- [x] 2.2 Implement `_classify_regime(price_5d_return)` → `"bull"` / `"bear"` / `"sideways"` theo ngưỡng `±0.02`
- [x] 2.3 Implement `_is_market_consistent(prediction, next_day_return)` → bool theo ngưỡng `±0.005`
- [x] 2.4 Implement class `MarketAnalyzer` với method `analyze(prediction, next_day_return, price_5d_return)` trả về dict 5 fields: `market_consistent`, `market_consistency_score`, `regime`, `next_day_return`, `price_5d_return`

## 3. Pipeline — tích hợp MarketAnalyzer

- [x] 3.1 Trong `src/pipeline.py`, import `MarketAnalyzer` từ `src.market_analyzer`
- [x] 3.2 Thêm `MARKET_COLUMNS` tuple: `("sample_id", "ticker", "forecast_time", "prediction", "next_day_return", "price_5d_return", "market_consistent", "regime", "market_consistency_score")`
- [x] 3.3 Trong `_run_group()`, sau bước Sufficiency (B1), đọc `next_day_return` và `price_5d_return` từ `group_rows[0]` (với default `0.0` nếu thiếu cột), gọi `MarketAnalyzer().analyze(prediction, next_day_return, price_5d_return)`, build `market_row`
- [x] 3.4 Trong `PipelineRunner.run()`, thu thập `market_rows` và ghi `market_consistency_results.csv` bằng `_write_csv(market_rows, MARKET_COLUMNS, market_path)`
- [x] 3.5 Thêm `market_consistency_results_csv` vào summary dict và print statement của `PipelineRunner.run()` / `main()`

## 4. Dashboard Data Loader

- [x] 4.1 Trong `src/dashboard/data_loader.py`, thêm `MARKET_COLUMNS` tuple
- [x] 4.2 Thêm field `market: Optional[pd.DataFrame] = None` vào `DashboardData` dataclass
- [x] 4.3 Trong `load_dashboard_data()`, đọc `market_consistency_results.csv` — missing → `None` (non-fatal), empty → empty DataFrame

## 5. Dashboard UI

- [x] 5.1 Trong `src/dashboard/components.py`, thêm hàm `render_market_tab(market_df)`:
  - Nếu `market_df` là `None` hoặc rỗng: hiện `st.info("Market consistency results not available...")`
  - Hiện 2 metric card: overall consistency rate (`market_consistent.mean()` format `:.0%`) và số samples
  - Hiện breakdown by regime: group by `regime`, tính `market_consistency_score.mean()` cho từng regime
  - Hiện bảng `market_df` với các cột chính
- [x] 5.2 Trong `src/dashboard/app.py`, thêm tab "Market" vào list tabs và gọi `render_market_tab(data.market)`
- [x] 5.3 Export `render_market_tab` trong `__all__` của `components.py`

## 6. Tests

- [x] 6.1 Tạo `tests/test_market_analyzer.py`:
  - Test `_classify_regime`: bull khi >0.02, bear khi <-0.02, sideways trong khoảng
  - Test `_is_market_consistent`: UP+positive return → True; UP+negative return → False; HOLD+neutral → True; HOLD+strong move → False
  - Test `MarketAnalyzer.analyze()`: `market_consistency_score` là 0.0 hoặc 1.0; `regime` là một trong 3 giá trị hợp lệ
- [x] 6.2 Trong `tests/test_pipeline.py`, thêm test: pipeline tạo `market_consistency_results.csv` với 9 cột đúng
- [x] 6.3 Trong `tests/test_pipeline.py`, thêm test: số dòng `market_consistency_results.csv` bằng số nhóm (ticker, forecast_time)
- [x] 6.4 Trong `tests/test_pipeline.py`, thêm test: pipeline không crash khi input CSV thiếu `next_day_return` / `price_5d_return`

## 7. Verification

- [x] 7.1 Chạy `python3.14 -m src.pipeline --input data/sample_dataset.csv --output-dir outputs` — không lỗi, `market_consistency_results.csv` xuất hiện
- [x] 7.2 Kiểm tra `outputs/market_consistency_results.csv` có đủ 9 cột, `market_consistency_score` chỉ chứa 0.0 hoặc 1.0, `regime` chỉ chứa bull/bear/sideways
- [x] 7.3 Chạy `pytest tests/ -v` — toàn bộ 535 tests pass
