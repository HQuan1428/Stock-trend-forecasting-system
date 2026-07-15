## Context

`CLAUDE.md` yêu cầu hỏi trước khi thêm real financial data / external API / crawler — đã xác nhận với người dùng qua phiên brainstorming trước khi viết change này.

Trước khi viết design này, nguồn dữ liệu đã được **xác minh thật** (không đoán) qua network, trong một implementation trước đó (commit `d85cc57`, dangling — branch chứa nó đã bị xoá cục bộ nhưng commit object vẫn truy cập được qua `git show`):

- **Giá**: `query1.finance.yahoo.com/v8/finance/chart/<TICKER>` trả JSON OHLCV thật, không cần API key, chỉ cần header `User-Agent` hợp lệ (không có header → HTTP 429). Stooq (`stooq.com/q/d/l/`) là fallback CSV free/keyless.
- **Tin tức**: `benstaf/FNSPID-nasdaq-100-1news-per-row-random` trên Hugging Face — subset 127,181 dòng (Parquet, ~289 MB) của **FNSPID** (Zihan Dong et al., *"FNSPID: A Comprehensive Financial News Dataset in Time Series"*, KDD 2024, arXiv:2402.06698): `Date` (timestamp thật), `Article_title`, `Stock_symbol`. Không cần auth. License **CC BY-NC-4.0**.
- Bản FNSPID gốc (`Zihan1004/FNSPID`, 15.7M dòng, CSV thô 5.7–23.2 GB) tồn tại nhưng không thực tế để tải cho một dataset ~400 dòng — bản subset Nasdaq-100 đủ và đúng tinh thần "nhẹ, học thuật".

Kiến trúc pipeline đã đổi từ khi implementation gốc được viết: `src/pipeline.py` (monolithic, `PipelineRunner`) không còn tồn tại trên `develop`. Kiến trúc hiện tại là chuỗi stage `src/runner.py` → `src/stages/{ingest,retriever,evidence_extractor,forecast_model,evidence_selector,faithfulness_evaluator,sufficiency_evaluator,market_analyzer}.py` → `src/export_csv.py`, mỗi stage đọc/ghi một envelope JSON. `src/stages/ingest.py` là stage đầu tiên đọc trực tiếp CSV, với `REQUIRED_COLUMNS = (news_id, ticker, forecast_time, news_time, news_text)` và đọc thêm 2 cột optional `next_day_return`, `price_5d_return` (mặc định `0.0` nếu thiếu). Script khôi phục ở change này sinh đúng 9 cột này — không cần sửa `ingest.py` hay bất kỳ stage nào.

## Goals / Non-Goals

**Goals:**
- `data/real_dataset.csv` với dữ liệu **thật 100%**: giá thật, tin thật (headline + timestamp thật), label suy ra từ giá thật.
- Tương thích tuyệt đối với input contract hiện tại của `src/stages/ingest.py` — không sửa một dòng code nào trong `src/`.
- ≥3 ticker, ≥300 dòng (rubric C1).
- Script tái chạy được (idempotent), có cache để không tải lại 289 MB mỗi lần.
- Không leak tương lai vào bất kỳ feature nào (`price_5d_return` chỉ dùng dữ liệu trước `forecast_time`).

**Non-Goals:**
- Không sửa `data/sample_dataset.csv` hay bất kỳ test/fixture nào dựa trên nó.
- Không biến bất kỳ stage nào dưới `src/` thành online/non-deterministic — mọi network call nằm trong `scripts/fetch_real_data.py`, chạy tách biệt, một lần.
- Không cố "chọn lọc" headline để khớp keyword dictionary hiện có — sampling phải trung lập để không làm sai lệch kết quả đánh giá faithfulness (xem Risk).
- Không tự động chạy `scripts/data_sources/fetch_alpha_vantage.py` / `fetch_kaggle_news.py` — cả hai cần key riêng của người dùng, chỉ chạy thủ công khi cần.
- Không chạy script này qua network trong phiên làm việc hiện tại — chỉ khôi phục code/docs, người dùng tự chạy sau.

## Decisions

**D1 — Đổi 1 trong 4 ticker: AAPL / GOOGL / AMZN / MSFT (không phải META)**

`data/sample_dataset.csv` (synthetic) dùng AAPL/GOOGL/AMZN/META. Khi lọc `benstaf/FNSPID-nasdaq-100-1news-per-row-random` theo `Stock_symbol`, **META có 0 dòng** trong subset này. MSFT có 594 dòng, phủ tốt 2022–2023. Quyết định: dùng **AAPL, GOOGL, AMZN, MSFT** cho dataset thật, ghi rõ lý do đổi ticker trong `data/README.md` — đây là ràng buộc thật của nguồn dữ liệu thật, không phải lựa chọn tùy tiện.

**D2 — Gộp `GOOG` và `GOOGL` thành một ticker `GOOGL`**

FNSPID gắn tin Alphabet dưới cả hai symbol (`GOOG`: 1744 dòng, `GOOGL`: 479 dòng). Coi `Stock_symbol in {GOOG, GOOGL}` là một thực thể, xuất ra dưới tên `GOOGL` để nhất quán với ticker hiện có trong `data/sample_dataset.csv`.

**D3 — Cửa sổ thời gian 2022-01-01 → 2023-12-31**

Cả 4 ticker đều có ≥270 dòng tin trong khoảng này. Giá được tải rộng hơn (2021-12-01 → 2024-01-15) để có đủ 5 ngày giao dịch lịch sử trước dòng tin sớm nhất và 1 ngày giao dịch sau dòng tin muộn nhất.

**D4 — Quy ước ghép tin ↔ forecast_time ↔ label**

```
forecast_day = ngày giao dịch kế tiếp gần nhất SAU ngày công bố tin
               (theo lịch giao dịch thật lấy từ chuỗi giá đã tải,
               tự động bỏ qua cuối tuần/ngày nghỉ)
forecast_time = f"{forecast_day} 09:00"
next_day_return = (close[forecast_day + 1 phiên] − close[forecast_day]) / close[forecast_day]
price_5d_return = (close[forecast_day] − close[forecast_day − 5 phiên]) / close[forecast_day − 5 phiên]
volume_change   = (volume[forecast_day] − volume[forecast_day − 1 phiên]) / volume[forecast_day − 1 phiên]
label = "UP" nếu next_day_return > 0.005; "DOWN" nếu < -0.005; else "HOLD"
```

Vì `forecast_day` luôn là phiên giao dịch **sau** ngày công bố tin, và `price_5d_return` chỉ dùng giá **trước** `forecast_time`, thiết kế này không có lookahead bias theo xây dựng — không cần một bước lọc leakage riêng để "chứng minh" tính hợp lệ (khác với `data/sample_dataset.csv`, vốn có leakage rows cài đặt có chủ đích để test retriever). Hai dataset có vai trò khác nhau, không trùng lặp: `sample_dataset.csv` chứng minh retriever xử lý leakage đúng; `real_dataset.csv` chứng minh pipeline chạy được trên dữ liệu thật không có leakage sẵn.

Dòng tin ở rìa cửa sổ (không đủ 5 phiên lịch sử trước, hoặc không có phiên sau) bị loại — logged nhưng không raise.

**D5 — Sampling trung lập, không chọn theo keyword**

Với mỗi ticker, sort tin theo ngày tăng dần, lấy tối đa 100 dòng bằng chỉ số cách đều (`numpy.linspace`) trên toàn bộ cửa sổ thời gian — **không** lọc/ưu tiên theo việc headline có khớp keyword dictionary hiện có. Nếu tự chọn tin "dễ" thì kết quả đo faithfulness sẽ lạc quan giả tạo. Kỳ vọng rõ ràng: nhiều headline thật sẽ không khớp keyword nào → evidence neutral → nhiều `HOLD` hơn so với `sample_dataset.csv`. Đây là kết quả cần báo cáo trung thực.

**D6 — `news_id` có tiền tố riêng**

Dùng tiền tố `R` (`R0001`, `R0002`, …) để không bao giờ trùng với `news_id` số nguyên của `data/sample_dataset.csv`.

**D7 — Cache tách biệt khỏi output, gitignore**

`scripts/fetch_real_data.py` tải Parquet (FNSPID) và JSON (Yahoo/Stooq) vào `data/raw_cache/`, thêm vào `.gitignore`. Chỉ `data/real_dataset.csv` (sản phẩm cuối, nhỏ) được commit. Script kiểm tra cache trước khi tải lại (idempotent).

**D8 — Không đổi input mặc định của pipeline; dùng `src.runner`, không phải `src.pipeline`**

`src/runner.py` (`python -m src.runner --input ...`) vẫn không có default input cố định — người dùng luôn truyền `--input` tường minh. Chạy dataset thật là **opt-in**: `python -m src.runner --input data/real_dataset.csv --output-dir outputs_real`. `src/stages/ingest.py`, `src/runner.py`, mọi stage khác giữ nguyên — khác với thiết kế gốc (nhắm `src/pipeline.py`, nay không còn tồn tại), quyết định này thay thế tham chiếu đó bằng kiến trúc hiện hành mà không đổi bản chất quyết định.

## Risks / Trade-offs

**[Risk] FNSPID license CC BY-NC-4.0 — phi thương mại** → Chấp nhận được: đồ án học thuật, không thương mại hóa. Ghi rõ trong `data/README.md`.

**[Risk] `Article` (nội dung đầy đủ) trong FNSPID có thể rất dài** → `news_text` chỉ dùng `Article_title` (ngắn, sạch hơn), nhất quán với độ dài `news_text` trong `data/sample_dataset.csv`.

**[Risk] Bản subset Nasdaq-100 là "random 1-news-per-row"** → Không đại diện đầy đủ cho mọi tin trong ngày của một ticker. Chấp nhận được cho quy mô đồ án; ghi rõ giới hạn này trong báo cáo.

**[Risk] Rule-based keyword dictionary hiện tại được tune trên câu viết tay, sẽ có hit-rate thấp trên headline thật** → Phát hiện nghiên cứu có giá trị, không phải bug. Không che giấu trong báo cáo.

**[Risk] Yahoo Finance chart API không có SLA công khai, có thể đổi response shape** → Script fail rõ ràng (exception, không silent-default) nếu response thiếu field mong đợi; script one-shot có cache nên rủi ro vận hành thấp.
