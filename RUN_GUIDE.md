# Hướng dẫn chạy Faithful Evidence-Centric Financial News Forecasting

Tài liệu này hướng dẫn cách cài đặt, chạy và kiểm thử toàn bộ pipeline theo từng bước. Bắt đầu từ môi trường trống đến khi xem được dashboard.

---

## 1. Chuẩn bị môi trường

### 1.1 Yêu cầu hệ thống
- **Python 3.10+** (đã thử nghiệm 3.14.4).
- **pip** >= 25.
- Hệ điều hành: Linux / macOS / WSL.

### 1.2 Clone và tạo venv

```bash
git clone <repo-url> Stock-trend-forecasting-system
cd Stock-trend-forecasting-system

# Tạo virtualenv trong thư mục project
python3 -m venv .venv

# Kích hoạt (bash/zsh)
source .venv/bin/activate
```

Trên Windows PowerShell dùng `.venv\Scripts\Activate.ps1`.

### 1.3 Cài dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` chỉ gồm 4 package: `pytest`, `streamlit`, `plotly`, `pandas`. Toàn bộ core pipeline (ingest → market_analyzer → export_csv) chỉ dùng **stdlib** — không cài thêm gì để chạy pipeline. Streamlit/Plotly/pandas chỉ phục vụ dashboard.

### 1.4 Kiểm tra cài đặt

```bash
pytest tests/test_schema_validation.py -v
```

Lệnh này chạy nhanh, không phụ thuộc file dữ liệu, giúp xác nhận môi trường hoạt động trước khi đi tiếp.

---

## 2. Hiểu dòng dữ liệu (data flow)

```
data/sample_dataset.csv
    │
    ▼
[1] src.ingest             → 01_samples.json          (CSV → envelope; group theo (ticker, forecast_time))
    │
    ▼
[2] src.retriever          → 02_retrieved.json        (valid_news / invalid_future_news)
    │
    ▼
[3] src.evidence_extractor → 03_evidence.json         (keyword matching → polarity + expected_direction)
    │
    ▼
[4] src.forecast_model     → 04_forecast.json         (UP/DOWN/HOLD + confidence)
    │
    ▼
[5] src.evidence_selector  → 05_selected.json         (pro/counter/neutral + B2 coverage)
    │
    ▼
[6] src.faithfulness_evaluator → 06_faithfulness.json (3 metric + verdict + ablation numbers)
    │
    ▼
[7] src.sufficiency_evaluator  → 07_sufficiency.json  (B1: sufficiency_score + counterfactual_delta)
    │
    ▼
[8] src.market_analyzer    → 08_market.json           (B3: market_consistent + regime)
    │
    ▼
[9] src.export_csv         → 6 file CSV trong outputs/
```

Mỗi bước **chỉ bổ sung** field vào sample (theo namespace: `forecast`, `selection`, `faithfulness`, ...). Không xóa field của bước trước. File ở cuối (08_market.json) chứa toàn bộ lịch sử tính toán — có thể `cat` để xem.

---

## 3. Cách A — Chạy trọn chuỗi (runner)

Dùng khi muốn chạy end-to-end cho demo hoặc đánh giá.

### 3.1 Lệnh đầy đủ

```bash
python -m src.runner --input data/sample_dataset.csv --output-dir outputs
```

### 3.2 Dừng sớm

```bash
# Chỉ chạy đến forecast_model (để xem dự báo thô, không có faithfulness)
python -m src.runner --input data/sample_dataset.csv --output-dir outputs --stop-after forecast_model
```

Các giá trị `--stop-after` hợp lệ (theo thứ tự chuỗi):
`ingest`, `retriever`, `evidence_extractor`, `forecast_model`, `evidence_selector`, `faithfulness_evaluator`, `sufficiency_evaluator`, `market_analyzer`, `export_csv`.

Khi dừng sớm, các file phía sau (kể cả CSV) sẽ **không** được ghi.

### 3.3 Kết quả mong đợi

Sau ~1–2 giây, terminal in ra:

```
src.runner: ok (100 samples)
  outputs/01_samples.json
  outputs/02_retrieved.json
  outputs/03_evidence.json
  outputs/04_forecast.json
  outputs/05_selected.json
  outputs/06_faithfulness.json
  outputs/07_sufficiency.json
  outputs/08_market.json
  outputs/prediction_results.csv
  outputs/evidence_results.csv
  outputs/faithfulness_results.csv
  outputs/sufficiency_results.csv
  outputs/market_consistency_results.csv
  outputs/temporal_leakage_results.csv
```

Trên dataset mẫu (100 sample) đo được: accuracy khoảng 74%, có khoảng 21 dòng `temporal_leakage_results.csv` (tin tương lai đã bị chặn).

### 3.4 Determinism (tái lập byte-for-byte)

```bash
# Chạy 2 lần, so sánh
diff -r <(python -m src.runner --input data/sample_dataset.csv --output-dir /tmp/run1) \
        <(python -m src.runner --input data/sample_dataset.csv --output-dir /tmp/run2)
```

Output phải rỗng. Toàn bộ stage là **pure function** (không phụ thuộc giờ hệ thống, không random, không có side effect), nên chạy lại luôn ra kết quả giống hệt.

---

## 4. Cách B — Chạy từng stage rời

Dùng khi muốn **inspect**, **sửa tay**, hoặc **chạy thử** một giai đoạn đơn lẻ. Mỗi stage nhận 1 envelope JSON, xuất 1 envelope JSON mới dưới namespace riêng của nó.

### 4.1 Chuỗi lệnh đầy đủ

```bash
mkdir -p outputs

# 1. Ingest — CSV → envelope
python -m src.ingest --input data/sample_dataset.csv -o outputs/01_samples.json

# 2. Retriever — phân loại valid / invalid_future news
python -m src.retriever --input outputs/01_samples.json -o outputs/02_retrieved.json

# 3. Evidence Extractor — keyword matching
python -m src.evidence_extractor --input outputs/02_retrieved.json -o outputs/03_evidence.json

# 4. Forecast Model — UP/DOWN/HOLD + confidence
python -m src.forecast_model --input outputs/03_evidence.json -o outputs/04_forecast.json

# 5. Evidence Selector — pro/counter/neutral + B2 coverage
python -m src.evidence_selector --input outputs/04_forecast.json -o outputs/05_selected.json

# 6. Faithfulness Evaluator — 3 metric + verdict
python -m src.faithfulness_evaluator --input outputs/05_selected.json -o outputs/06_faithfulness.json

# 7. Sufficiency Evaluator (B1) — sufficiency + counterfactual
python -m src.sufficiency_evaluator --input outputs/06_faithfulness.json -o outputs/07_sufficiency.json

# 8. Market Analyzer (B3) — consistency + regime
python -m src.market_analyzer --input outputs/07_sufficiency.json -o outputs/08_market.json

# 9. Export CSV — envelope cuối → 6 CSV
python -m src.export_csv --input outputs/08_market.json --output-dir outputs
```

### 4.2 Quy ước tham số

- Tất cả các stage (trừ `ingest`) đều dùng `--input <file.json> -o <file.json>`.
- `ingest` đọc CSV nên chỉ cần `--input <file.csv>`.
- `runner` và `export_csv` dùng `--output-dir <dir>` thay vì `-o <file>`.

### 4.3 Cùng code path với runner

Quan trọng: `python -m src.<stage>` và `python -m src.runner` **gọi cùng một hàm `process(envelope)`**. Có thể kiểm chứng:

```bash
# Cách 1: chạy rời
mkdir -p /tmp/run_cli
python -m src.ingest --input data/sample_dataset.csv -o /tmp/run_cli/01_samples.json
for stage in retriever evidence_extractor forecast_model evidence_selector faithfulness_evaluator sufficiency_evaluator market_analyzer; do
  i=$(echo $stage | sed 's/.*//')  # noop, giữ chỉ
done
python -m src.runner --input data/sample_dataset.csv --output-dir /tmp/run_runner

# Cách 2: compare
diff -r /tmp/run_cli /tmp/run_runner
```

Phải ra rỗng — không có "chạy lẻ khác chạy chuỗi".

---

## 5. Mẹo kiểm tra giữa các bước

### 5.1 Xem cấu trúc envelope ở mỗi bước

```bash
# Stage 2: xem bao nhiêu tin bị loại vì temporal leakage
python -c "
import json
env = json.load(open('outputs/02_retrieved.json'))
for s in env['samples'][:3]:
    print(s['sample_id'], '| valid:', len(s['valid_news']), '| future:', len(s['invalid_future_news']))
"

# Stage 4: xem prediction của 5 sample đầu
python -c "
import json
env = json.load(open('outputs/04_forecast.json'))
for s in env['samples'][:5]:
    f = s['forecast']
    print(f\"{s['sample_id']:35s} {f['prediction']:5s} conf={f['confidence']:.2f} score={f['score']:+d}\")
"

# Stage 6: xem verdict phân bố
python -c "
import json
from collections import Counter
env = json.load(open('outputs/06_faithfulness.json'))
c = Counter(s['faithfulness']['verdict'] for s in env['samples'])
for k, v in sorted(c.items(), key=lambda x: -x[1]):
    print(f'{v:3d}  {k}')
"
```

### 5.2 Inspect 1 sample cụ thể bằng `jq` (nếu có cài)

```bash
# Sample đầu tiên ở stage faithfulness
jq '.samples[0].faithfulness' outputs/06_faithfulness.json

# Đếm evidence theo polarity
jq '[.samples[].evidence[] | .polarity] | group_by(.) | map({(.[0]): length}) | add' \
  outputs/03_evidence.json
```

### 5.3 Xem faithfulness label HIGH/MEDIUM/LOW

```bash
column -ts, outputs/faithfulness_results.csv | head -10
```

---

## 6. Dashboard — trực quan hóa kết quả

Sau khi đã chạy pipeline xong (đã có `outputs/08_market.json`):

```bash
streamlit run src/dashboard/app.py
```

Trình duyệt mở `http://localhost:8501`. Đăng nhập không cần thiết.

Dashboard có **6 tab**:

| Tab | Nội dung | Điểm trong ChuDe1.md |
|---|---|---|
| 🎬 Live Demo | Kịch bản demo 5 phút: chọn ticker → chọn ngày → xem valid news → xem prediction → toggle "Remove cited evidence" → kết luận | §11.1, A7 |
| 📊 Overview | Phân bố prediction, accuracy theo ticker | A7 |
| 📄 Evidence | Bảng evidence dataset-wide, có filter ticker/role/cited | A7 |
| 🔍 Faithfulness | Confidence drop chart, radar 5 trục | §9, A7 |
| ⏰ Temporal Leakage | Banner + bảng tin tương lai đã chặn | §4.2 |
| 🧪 B-metrics | B1 sufficiency, B2 coverage, B3 market/regime, B4 agent trace | B1–B4 |

**Dashboard tuyệt đối read-only** — không ghi vào `outputs/`, không gọi lại pipeline, không re-run model. Toggle "Remove cited evidence" chỉ hiển thị số ablation đã tính sẵn ở stage 6.

**Cache tự invalidate khi pipeline chạy lại**: dashboard cache theo `mtime` của `08_market.json`, không cần nhấn nút clear.

---

## 7. Test

### 7.1 Chạy toàn bộ

```bash
pytest tests/
```

### 7.2 Chạy theo nhóm

```bash
# Test cho core (temporal, evidence, forecast, faithfulness)
pytest tests/test_temporal_retriever.py tests/test_evidence_extractor.py \
       tests/test_forecast_model.py tests/test_faithfulness_evaluator.py -v

# Test cho B-metrics
pytest tests/test_sufficiency_evaluator.py tests/test_market_analyzer.py -v

# Test cho dashboard (không cần Streamlit server, chỉ test hàm thuần)
pytest tests/test_dashboard_*.py -v

# Test cho CLI + runner
pytest tests/test_stage_cli.py tests/test_runner.py -v
```

### 7.3 Một test case cụ thể

```bash
pytest tests/test_forecast_model.py::test_predict_up -v
pytest tests/test_temporal_leakage.py -v
```

### 7.4 Coverage

```bash
pytest tests/ --cov=src
```

---

## 8. Lỗi thường gặp và cách xử lý

### 8.1 `ModuleNotFoundError: No module named 'src'`

Nguyên nhân: chạy lệnh ngoài thư mục project, hoặc trong subfolder.

```bash
# Đảm bảo đang ở root
cd /home/quannh/my-space/Stock-trend-forecasting-system
python -m src.runner ...
```

Hoặc:
```bash
PYTHONPATH=. python -m src.runner ...
```

### 8.2 Lỗi CSV: `input CSV is missing required columns`

```
src.ingest: input CSV is missing required columns: ['news_text', 'forecast_time']
```

→ File CSV đầu vào thiếu một trong các cột bắt buộc: `news_id`, `ticker`, `forecast_time`, `news_time`, `news_text`. Cột `label`, `next_day_return`, `price_5d_return` tùy chọn. Kiểm tra header file CSV.

### 8.3 Lỗi `envelope failed validation for stage '...'`

```
src.forecast_model: envelope failed validation for stage 'forecast_model':
  sample 'AAPL_...': missing required key 'evidence'
```

→ Đang chạy stage không đúng thứ tự, hoặc file envelope đầu vào bị sửa/hỏng. Phải chạy đúng thứ tự:
`01_samples` → `02_retrieved` → `03_evidence` → ... Mỗi file chỉ hợp lệ làm input cho đúng 1 stage kế tiếp.

Khắc phục nhanh: chạy lại runner từ đầu (`python -m src.runner ...`).

### 8.4 `ModuleNotFoundError: No module named 'streamlit'`

```bash
pip install -r requirements.txt
```

### 8.5 `Address already in use` khi chạy Streamlit

Đổi port:
```bash
streamlit run src/dashboard/app.py --server.port 8502
```

### 8.6 Pipeline chạy nhưng accuracy thấp (~27%)

Đây là kết quả thật khi keyword dictionary quá thưa (V1). Phiên bản hiện tại đã dùng **V3 dictionary** (28 positive + 28 negative keyword, bao gồm cụm từ mềm như "warns", "pauses", "introduces"), accuracy ~74% trên dataset mẫu. Nếu tự dựng CSV khác, có thể accuracy sẽ khác.

### 8.7 Muốn chạy lại từ đầu

```bash
rm -f outputs/*.json outputs/*.csv
python -m src.runner --input data/sample_dataset.csv --output-dir outputs
```

---

## 9. Workflow khuyến nghị cho người mới

1. **Đọc `CLAUDE.md`** (5 phút) — để nắm kiến trúc, invariants.
2. **Chạy runner trọn chuỗi** (3 phút):
   ```bash
   python -m src.runner --input data/sample_dataset.csv --output-dir outputs
   ```
3. **Mở dashboard** (1 phút):
   ```bash
   streamlit run src/dashboard/app.py
   ```
4. **Thử tab Live Demo** — chọn ticker, chọn ngày, bật toggle "Remove cited evidence" để thấy ablation chạy.
5. **Chạy thử 1 stage rời** (5 phút): xóa `outputs/03_evidence.json`, chạy lại stage 3 quan sát output.
6. **Đọc `ARCHITECTURE.md`** (10 phút) — để hiểu file nào làm gì, tại sao.
7. **Đọc `TECHNICAL_ISSUES.md`** (10 phút) — để hiểu lịch sử quyết định kỹ thuật.
8. **Khi cần thêm feature**: tuân thủ OpenSpec — đọc `openspec/changes/<change>/proposal.md` trước khi sửa code.

---

## 10. Cấu trúc file quan trọng cần nhớ

| File | Vai trò |
|---|---|
| `data/sample_dataset.csv` | Dữ liệu đầu vào (100 sample, 4 ticker, có label + giá B3) |
| `outputs/01_samples.json` … `08_market.json` | 8 envelope trung gian |
| `outputs/*.csv` | 6 file kết quả cuối |
| `outputs/run_log.json` | B4: trace phát triển (40 entry), KHÔNG dùng cho prediction |
| `src/retriever.py::TimeUtils` | Single source of truth cho UTC parsing |
| `src/evidence_extractor.py::{POSITIVE_KEYWORDS, NEGATIVE_KEYWORDS}` | Single source of truth cho polarity |
| `src/forecast_model.py::ForecastModel` | Thuật toán dự báo duy nhất — mọi nơi cần predict đều gọi đây |
| `openspec/changes/<ten>/` | Spec-driven: proposal + design + tasks + specs/ |

---

## 11. Tài liệu liên quan

- `README.md` — tổng quan dự án + hướng dẫn tiếng Anh.
- `CLAUDE.md` — quick reference cho AI agent: lệnh, kiến trúc, invariants.
- `AGENTS.md` — quy tắc đóng góp + tech stack.
- `ARCHITECTURE.md` — chi tiết kiến trúc, ma trận sự cố, đánh giá tổng thể.
- `TECHNICAL_ISSUES.md` — 11 vấn đề đã gặp và cách giải quyết.
- `setup-system.md` — hướng dẫn cài Python/venv (đã cũ về lệnh `pipeline`, ưu tiên file này).
- `openspec/changes/<ten-change>/proposal.md` — điểm bắt đầu khi muốn hiểu/thêm 1 module.
- `ChuDe1.md` — yêu cầu đồ án gốc (A1–A7 + B1–B4).

---

## 12. Nguyên tắc cứng (bất khả xâm phạm)

Nhắc lại để khỏi quên khi sửa code:

1. **Temporal validity bất khả xâm phạm**: tin có `news_time > forecast_time` không được dùng để dự báo. `TemporalRetriever` lọc trước; `ForecastModel._filter_temporal` lọc lại ở defence-in-depth — nếu sửa file trung gian nhét tin tương lai vào, dự báo vẫn không dùng.
2. **Determinism tuyệt đối**: cùng input → cùng output byte-for-byte. Không gọi API trong `process()`, không phụ thuộc `datetime.now()`, không random.
3. **No ML/LLM/external API**: toàn bộ baseline là rule-based, không model download, không network call.
4. **`TimeUtils.parse_utc` và `EvidenceExtractor.*_KEYWORDS` là single source of truth** — đừng tự viết lại parse UTC hay định nghĩa lại polarity ở module khác.
5. **Không thêm API key, secret, khuyến nghị mua/bán**, không crawl web, không add database, không thay đổi kiến trúc lớn khi chưa hỏi.
