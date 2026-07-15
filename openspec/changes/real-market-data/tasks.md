## 1. Restore `scripts/fetch_real_data.py`

- [x] 1.1 Tạo `scripts/__init__.py` (empty)
- [x] 1.2 Khôi phục `scripts/fetch_real_data.py` từ `git show d85cc57:scripts/fetch_real_data.py`, giữ nguyên toàn bộ logic (không phụ thuộc `src/pipeline.py` hay bất kỳ module nào dưới `src/` — chỉ đọc/ghi CSV/JSON/Parquet độc lập)
- [x] 1.3 Cập nhật docstring đầu file: đổi ví dụ lệnh chạy pipeline từ `python -m src.pipeline --input data/real_dataset.csv --output-dir outputs_real` sang `python -m src.runner --input data/real_dataset.csv --output-dir outputs_real`
- [x] 1.4 Verify `python3 -c "import scripts.fetch_real_data"` không lỗi import (numpy/pandas/pyarrow phải có trong `requirements.txt`, xem mục 4)

## 2. Restore `scripts/data_sources/` (nguồn dự phòng, cần API key riêng)

- [x] 2.1 Khôi phục `scripts/data_sources/__init__.py`, `fetch_alpha_vantage.py`, `fetch_kaggle_news.py` từ `git show d85cc57:scripts/data_sources/<file>`
- [x] 2.2 Khôi phục `scripts/data_sources/README.md` (runbook: cách lấy key free, biến môi trường, lệnh chạy, output path)
- [x] 2.3 Verify cả 2 script KHÔNG được import bởi `scripts/fetch_real_data.py`, bất kỳ module nào dưới `src/`, hay bất kỳ file test nào (`grep -rn "fetch_alpha_vantage\|fetch_kaggle_news" src/ tests/ scripts/fetch_real_data.py` phải rỗng)

## 3. Restore `.env.example`

- [x] 3.1 Khôi phục `.env.example` ở repo root từ `git show d85cc57:.env.example` (4 biến optional: `ALPHAVANTAGE_API_KEY`, `KAGGLE_USERNAME`, `KAGGLE_KEY`, `HF_TOKEN`)
- [x] 3.2 Verify `.env` thật (đã tồn tại, gitignored) không bị ghi đè hay commit

## 4. Dependencies + gitignore

- [x] 4.1 Thêm vào `requirements.txt`: `numpy`, `pyarrow`, `python-dotenv`, `kaggle` — KHÔNG thêm `torch`/`transformers`/`datasets` (thuộc scope C2/FinBERT, ngoài phạm vi change này)
- [x] 4.2 Thêm `data/raw_cache/` vào `.gitignore`
- [x] 4.3 Verify `.env` và `.envrc` vẫn có trong `.gitignore` (đã có sẵn, không cần đổi)

## 5. Docs

- [x] 5.1 Thêm mục "Real dataset (`real_dataset.csv`) — C1 bonus" vào `data/README.md`, nội dung tương đương bản khôi phục từ `d85cc57:data/README.md` nhưng đổi mọi lệnh `python -m src.pipeline` thành `python -m src.runner --output-dir outputs_real`
- [x] 5.2 Trong mục docs, ghi rõ: ticker AAPL/GOOGL/AMZN/MSFT (không phải META), lý do đổi; license FNSPID CC BY-NC-4.0; và ghi chú kỳ vọng hit-rate thấp của keyword extractor trên dữ liệu thật (không phải bug)

## 6. Tests

- [x] 6.1 Khôi phục `tests/test_fetch_real_data.py` từ `git show d85cc57:tests/test_fetch_real_data.py` nguyên trạng (test thuần các hàm `normalize_ticker`, `build_dataset`, `sample_evenly`, `fetch_price_series_stooq`, price-source selection — network mock qua `unittest.mock.patch`)
- [x] 6.2 Chạy `pytest tests/test_fetch_real_data.py -v` — toàn bộ pass, không có lệnh gọi mạng thật nào trong test suite
- [x] 6.3 Chạy toàn bộ `pytest tests/` — xác nhận không có test nào khác bị ảnh hưởng (không sửa gì dưới `src/`)

## 7. Manual verification (người dùng tự chạy, không chạy trong phiên implement)

- [ ] 7.1 `python3 scripts/fetch_real_data.py` — tạo `data/real_dataset.csv`, kiểm tra ≥300 dòng, ≥3 ticker, cột đúng 9 cột
- [ ] 7.2 `python -m src.runner --input data/real_dataset.csv --output-dir outputs_real` chạy thành công hết chuỗi stage, sinh đủ 8 envelope + 6 CSV
- [ ] 7.3 `streamlit run src/dashboard/app.py` mở được, trỏ `--output-dir outputs_real` hiển thị đúng không crash
