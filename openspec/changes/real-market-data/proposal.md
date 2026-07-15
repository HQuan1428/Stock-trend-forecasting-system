## Why

`data/sample_dataset.csv` là 144 dòng viết tay; `next_day_return`, `price_5d_return`, `volume_change` được sinh bằng `hash(ticker + forecast_time)`, không có tương quan thật với thị trường. `ChuDe1.md` §7 (C1) thưởng +1.0 điểm cộng cho nhóm dùng dữ liệu giá/tin thật với ≥3 ticker và ≥300 mẫu, có xử lý temporal leakage.

Một thiết kế + implementation đầy đủ cho đúng bài toán này đã tồn tại trong lịch sử git (commit `d85cc57`, trên một branch đã bị xoá cục bộ, không nằm trong `develop`) — nguồn dữ liệu đã được verify thật qua network, và output đã đúng schema. Change này khôi phục + adapt lại phần đó cho kiến trúc stage hiện tại (`src/runner.py` + `src/stages/`), không thiết kế lại từ đầu.

## What Changes

- Thêm script một lần `scripts/fetch_real_data.py`: tải giá thật (Yahoo Finance chart API mặc định, hoặc Stooq CSV qua `--price-source stooq`, cả hai đều free/keyless) và tin thật (tập con Nasdaq-100 của FNSPID trên Hugging Face, free/keyless, CC BY-NC-4.0) cho 4 ticker AAPL/GOOGL/AMZN/MSFT, ghép thành `data/real_dataset.csv` đúng 9-cột schema hiện có: `news_id, ticker, forecast_time, news_time, news_text, label, next_day_return, price_5d_return, volume_change`.
- Schema này đã khớp 100% với input contract của `src/stages/ingest.py` hiện tại (`REQUIRED_COLUMNS` + 2 cột B3 optional) — **không sửa bất kỳ file nào dưới `src/`**. Chạy dataset thật qua đúng pipeline hiện có bằng `python -m src.runner --input data/real_dataset.csv --output-dir outputs_real`.
- `label`, `next_day_return`, `price_5d_return` tính từ giá đóng cửa thật theo đúng công thức `ChuDe1.md` §7.2 (`return = (close_t+1 − close_t)/close_t`, ngưỡng ±0.5%).
- Khôi phục `scripts/data_sources/` (`fetch_alpha_vantage.py`, `fetch_kaggle_news.py`, `README.md`, `__init__.py`) — 2 nguồn dự phòng cần API key riêng của người dùng, không tự động chạy, không được import bởi `fetch_real_data.py` hay bất kỳ test nào.
- Khôi phục `.env.example` (tài liệu hoá 4 biến optional: `ALPHAVANTAGE_API_KEY`, `KAGGLE_USERNAME`, `KAGGLE_KEY`, `HF_TOKEN`; `.env` thật của người dùng đã tồn tại, gitignored, giữ nguyên).
- Khôi phục `tests/test_fetch_real_data.py` — unit test thuần cho logic join/label/sampling, không gọi mạng thật (mock `urllib.request.urlopen`).
- `data/sample_dataset.csv` và mọi module dưới `src/` **không đổi**.

## Capabilities

### New Capabilities

- `real-market-data`: một script độc lập, có chạm mạng, sinh ra `data/real_dataset.csv` — dataset thật (giá thật + tin thật + label thật) tương thích 100% với input contract hiện có của `src/stages/ingest.py`. Đây là ranh giới duy nhất trong toàn bộ dự án được phép gọi network; `src/runner.py` và mọi stage vẫn giữ nguyên tính chất offline, deterministic.

### Modified Capabilities

*(không có — không đổi schema hay hành vi của bất kỳ stage nào trong `src/`)*

## Impact

- **`scripts/fetch_real_data.py`** (mới, khôi phục từ `d85cc57`): duy nhất file trong repo được phép gọi network (Yahoo Finance/Stooq + Hugging Face). Không nằm trong `src/`, không được `src/runner.py` hay bất kỳ stage nào import.
- **`scripts/data_sources/`** (mới, khôi phục): 2 script credential-gated, chạy thủ công, không ảnh hưởng pipeline mặc định.
- **`data/real_dataset.csv`** (mới, committed): ~350–450 dòng, 4 ticker, dữ liệu 2022–2023, đúng 9 cột schema hiện có.
- **`data/raw_cache/`** (mới, gitignored): cache Parquet/JSON tải về, không commit.
- **`requirements.txt`**: thêm `numpy`, `pyarrow`, `python-dotenv`, `kaggle`.
- **`.gitignore`**: thêm `data/raw_cache/`.
- **`data/README.md`**: thêm mục "Real dataset (real_dataset.csv) — C1 bonus", lệnh chạy dùng `src.runner` thay vì `src.pipeline` cũ.
- **`tests/test_fetch_real_data.py`** (mới, khôi phục): unit test cho các hàm join/label/sampling thuần túy, không gọi mạng trong test suite.
- **Không đổi**: mọi file dưới `src/`, `data/sample_dataset.csv`, mọi output CSV schema, mọi test hiện có phải vẫn pass nguyên.
- **Giấy phép dữ liệu**: FNSPID là CC BY-NC-4.0 (phi thương mại) — phù hợp phạm vi học thuật, ghi rõ trong `data/README.md`.
