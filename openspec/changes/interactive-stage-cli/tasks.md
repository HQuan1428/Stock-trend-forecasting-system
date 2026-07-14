# Tasks: Interactive Stage CLI

## 1. Schema validators + stage IO (T1)

- [x] 1.1 Nâng cấp `src/schema.py`: thêm `REQUIRED_SAMPLE_KEYS` (bảng key/type theo từng stage) và `validate_sample(sample, stage) -> list[str]`, giữ nguyên dataclass tài liệu
- [x] 1.2 Tạo `src/stage_io.py`: `load_envelope(path, stage)` (đọc JSON + validate, lỗi → stderr + exit 2), `dump_envelope(env, path)` (sort_keys, indent=2, ensure_ascii=False, trailing newline), `build_stage_parser(stage_name)` (argparse `--input`/`-o`)
- [x] 1.3 Viết `tests/test_schema_validation.py`: sample hợp lệ, thiếu key, sai type, message chứa sample_id

## 2. Per-stage process() + main() (T2)

- [x] 2.1 Tạo `src/ingest.py`: CSV → envelope (stdlib csv, group `(ticker, forecast_time)` giữ thứ tự, sinh sample_id, mặc định 0.0 cho cột giá thiếu) + `main()`
- [x] 2.2 Thêm `process()`/`main()` vào `src/retriever.py` (gọi `TemporalRetriever.retrieve` per-sample, ghi `valid_news`/`invalid_future_news`)
- [x] 2.3 Thêm `process()`/`main()` vào `src/evidence_extractor.py` (glue dựng extractor input từ valid_news — port từ `_run_group` bước 2 pipeline cũ, gắn `news_time` vào evidence)
- [x] 2.4 Thêm `process()`/`main()` vào `src/forecast_model.py` (dựng forecast request — port `_build_forecast_request`, gọi `predict()` per-sample, KHÔNG dùng `predict_batch` để tránh tự ghi file, kết quả vào key `forecast`)
- [x] 2.5 Thêm `process()`/`main()` vào `src/evidence_selector.py` (dựng selector request + `expected_labels`, gọi `select_batch` + `compute_coverage` B2 — port bước 4/4b, kết quả vào `selection`/`coverage`)
- [x] 2.6 Thêm `process()`/`main()` vào `src/faithfulness_evaluator.py` (gọi `evaluate(request, forecast)`, kết quả vào `faithfulness`)
- [x] 2.7 Thêm `process()`/`main()` vào `src/sufficiency_evaluator.py` (B1: cited_ids từ `selection`, kết quả vào `sufficiency`)
- [x] 2.8 Thêm `process()`/`main()` vào `src/market_analyzer.py` (B3: dùng `next_day_return`/`price_5d_return` của sample, kết quả vào `market`)
- [x] 2.9 Viết `tests/test_stage_cli.py`: happy path từng stage qua `main()` với tmp file; input hỏng → exit 2 + message; output stage N pass validator stage N+1; CLI vs `process()` cho cùng kết quả

## 3. Runner + export CSV (T3)

- [x] 3.1 Tạo `src/export_csv.py`: envelope cuối → 6 CSV (port `*_COLUMNS`, `_build_evidence_rows`, `_compute_leakage_minutes`, `_faithfulness_label` từ pipeline cũ) + `main()` chạy độc lập
- [x] 3.2 Tạo `src/runner.py`: chain `process()` các stage in-process, ghi `01_…08_*.json` + gọi export_csv, hỗ trợ `--stop-after`
- [x] 3.3 Viết `tests/test_runner.py`: end-to-end trên `data/sample_dataset.csv` (đủ file JSON + CSV), determinism (2 lần chạy byte-equal), `--stop-after` hoạt động
- [x] 3.4 So sánh `prediction_results.csv` mới với `git show HEAD:outputs/prediction_results.csv` — phải trùng nội dung (logic không đổi). Kết quả: prediction/evidence/sufficiency/market/leakage byte-identical; faithfulness khác do module code trong working tree đã đổi cách tính confidence_after_removal so với thời điểm commit CSV cũ (không liên quan glue)

## 4. Docs (T4)

- [x] 4.1 Viết lại `CLAUDE.md`: section Commands (lệnh CLI từng stage + runner) và Architecture (envelope flow, bỏ mọi tham chiếu pipeline/dashboard cũ)
- [x] 4.2 Cập nhật `README.md`: hướng dẫn chạy từng stage + end-to-end (kèm sửa code example từ API hàm cũ sang API class, bỏ section dashboard/samples đã xóa)

## 5. Verification (T5)

- [x] 5.1 `pytest tests/` toàn bộ pass — 410 tests (381 cũ + 29 mới)
- [x] 5.2 Demo tay: chạy chuỗi 9 lệnh CLI rời trên `data/sample_dataset.csv` (100 samples), inspect envelope trung gian OK; đã chuyển `src/__init__.py` sang lazy export để hết RuntimeWarning của runpy
- [x] 5.3 Kiểm tra determinism: runner 2 lần → `diff -r` rỗng; output CLI chain == output runner (byte-identical)
