# Kiến trúc tổng quan hệ thống

**Faithful Evidence-Centric Financial News Forecasting** — prototype học thuật dự báo xu hướng cổ phiếu (UP/DOWN/HOLD) từ tin tức và kiểm chứng tính faithful của evidence. Tài liệu này mô tả hệ thống gồm những phần nào, các phần giao tiếp với nhau ra sao, vì sao chọn kiến trúc này, và khi một phần gặp sự cố thì phần còn lại bị ảnh hưởng thế nào.

---

## 1. Hệ thống gồm những phần nào

Kiến trúc là **chuỗi 9 stage tuần tự** (pipeline dạng batch), mỗi stage là một module Python độc lập chạy được từ terminal, cộng một **runner mỏng** để chạy trọn chuỗi bằng một lệnh. Không có server, không database, không service chạy nền — toàn bộ là tiến trình chạy-rồi-thoát trên file.

```
data/sample_dataset.csv
     │
     ▼
┌────────────────────┐
│ 1. ingest          │  CSV → envelope: group tin theo (ticker, forecast_time)
├────────────────────┤
│ 2. retriever       │  A: chặn temporal leakage — tách valid_news / invalid_future_news
├────────────────────┤
│ 3. evidence_       │  A: keyword matching (rule-based) → evidence có polarity
│    extractor       │     + expected_direction
├────────────────────┤
│ 4. forecast_model  │  A: voting trên evidence → prediction UP/DOWN/HOLD + confidence
├────────────────────┤
│ 5. evidence_       │  A + B2: phân loại evidence pro/counter/neutral so với
│    selector        │     prediction + tính counterevidence coverage
├────────────────────┤
│ 6. faithfulness_   │  A: 3 metric — temporal_validity, evidence_support,
│    evaluator       │     confidence_drop (ablation: bỏ evidence cited, dự báo lại)
├────────────────────┤
│ 7. sufficiency_    │  B1: sufficiency score (chỉ dùng evidence cited)
│    evaluator       │     + counterfactual delta
├────────────────────┤
│ 8. market_analyzer │  B3: đối chiếu prediction với next_day_return + regime
├────────────────────┤
│ 9. export_csv      │  Envelope cuối → 6 file CSV kết quả
└────────────────────┘
     │
     ▼
outputs/  (8 envelope JSON trung gian + 6 CSV)
```

### Thành phần hỗ trợ (không phải stage)

| Thành phần | File | Vai trò |
|---|---|---|
| Runner | `src/runner.py` | Orchestrator mỏng: chain 9 stage in-process, ghi file trung gian sau mỗi stage, hỗ trợ `--stop-after`. Không chứa logic nghiệp vụ. |
| Schema validator | `src/schema.py` | Bảng `REQUIRED_SAMPLE_KEYS` (key/type bắt buộc trước mỗi stage, cộng dồn theo chuỗi) + `validate_sample()`. |
| Stage IO | `src/stage_io.py` | Đọc/ghi envelope deterministic, thân CLI dùng chung, quy ước exit code. |
| Metric thuần | `src/faithfulness_metrics.py` | Hàm tính toán thuần cho stage 6 (không state, không I/O). |
| Agent trace (B4) | `src/agent_trace.py` | Log SDLC (write/load/summarize) — **nằm ngoài chuỗi runtime**, minh chứng quy trình phát triển, không tham gia dự báo. |
| Dashboard | `src/dashboard/` (`app.py`, `components.py`, `data_loader.py`, `metrics.py`, `charts.py`) | Streamlit + Plotly, **chỉ đọc** `outputs/08_market.json`. Tách lớp: `data_loader`/`metrics`/`charts` là hàm thuần (test bằng pytest, không cần server); `app.py`/`components.py` chỉ render. Không ghi vào `outputs/`, không gọi lại stage nào, không re-run model — toggle "Remove cited evidence" chỉ hiển thị số ablation đã tính sẵn trong `faithfulness`. |

### Hai lớp trong mỗi stage

Mỗi stage module có cấu trúc 2 lớp tách bạch:

1. **Class nghiệp vụ** (ví dụ `TemporalRetriever`, `ForecastModel`) — thuật toán thuần, nhận/trả plain `dict`, không biết gì về file hay envelope.
2. **Adapter module-level** — `process(envelope) -> envelope` (glue: dựng request cho class từ sample, gọi class, merge kết quả) và `main(argv)` (CLI ~10 dòng).

CLI rời và runner **cùng gọi một hàm `process()`** — không tồn tại code path thứ hai, nên "chạy từng bước" và "chạy trọn chuỗi" không bao giờ lệch nhau (đã kiểm chứng: output hai cách chạy byte-identical).

---

## 2. Các phần nói chuyện với nhau như thế nào

### Accumulating envelope — hợp đồng dữ liệu duy nhất

Toàn bộ giao tiếp giữa các stage đi qua **một document JSON** dạng:

```json
{
  "stage": "<stage vừa chạy>",
  "samples": [
    {
      "sample_id": "AAPL_2025-03-12_0900",
      "ticker": "AAPL", "forecast_time": "2025-03-12 09:00", "label": "UP",
      "news": [...],                                  // ingest
      "valid_news": [...], "invalid_future_news": [...],  // + retriever
      "evidence": [...],                              // + extractor
      "forecast": {...},                              // + forecast_model
      "selection": {...}, "coverage": {...},          // + selector (B2)
      "faithfulness": {...},                          // + faithfulness
      "sufficiency": {...},                           // + B1
      "market": {...}                                 // + B3
    }
  ]
}
```

Quy tắc: mỗi stage **chỉ bổ sung** field vào sample dưới namespace riêng, không xóa/ghi đè field của stage trước. Hệ quả: file sau stage N chứa toàn bộ lịch sử tính toán đến N — người dùng `cat` file bất kỳ là thấy đầy đủ state, và stage sau luôn có đủ context (ví dụ faithfulness cần cả evidence gốc lẫn forecast).

### Hai chế độ vận chuyển, một hợp đồng

- **Chạy rời từng stage**: envelope đi qua **file JSON** — `python -m src.retriever --input 01_samples.json -o 02_retrieved.json`. Người dùng có thể dừng, xem, thậm chí sửa file giữa hai bước.
- **Chạy runner**: envelope đi qua **bộ nhớ** (dict truyền thẳng giữa các `process()`), nhưng vẫn ghi file trung gian sau mỗi stage để quan sát/resume.

### Kiểm soát ở ranh giới

Mỗi lần một stage đọc envelope, `validate_sample()` kiểm tra đủ key/đúng type cho stage đó. Sai → in message nêu đích danh `sample_id` + key lỗi ra stderr, **exit code 2**, không ghi output. Serialization deterministic (`sort_keys`, `indent=2`) đảm bảo cùng input → cùng file byte-for-byte.

### Dashboard — nhánh giao tiếp một chiều, tách biệt

Dashboard **không nằm trong chuỗi 9 stage** — nó là một tiến trình riêng (`streamlit run`), giao tiếp với pipeline duy nhất bằng cách **đọc file** `outputs/08_market.json`:

- Đọc lại `validate_sample()` (cùng validator stage dùng) trước khi flatten ra DataFrame — nếu envelope hỏng/thiếu, dashboard tự báo lỗi bằng tiếng Việt kèm hướng dẫn chạy lại runner, không đoán mò dữ liệu.
- Cache theo `mtime` của file: runner ghi đè `08_market.json` → dashboard tự nhận thấy, không cần thao tác thủ công (không tồn tại watcher hay push nào giữa 2 tiến trình, chỉ so mtime mỗi lần user tương tác lại trang).
- Đường đi **chỉ một chiều pipeline → dashboard**; dashboard không có API/hàm nào gọi ngược vào `src/*` stage.

---

## 3. Vì sao chọn kiến trúc này

| Quyết định | Lý do | Phương án bị loại |
|---|---|---|
| **Chuỗi stage CLI rời** thay vì orchestrator monolithic | Đây là đồ án về *faithfulness* — giá trị nằm ở việc quan sát được dữ liệu biến đổi qua từng bước (demo được, debug được, chấm điểm được). Phiên bản đầu là một `pipeline.py` 694 dòng ôm toàn bộ glue: chạy được end-to-end nhưng không thể chạy/kiểm tra một giai đoạn riêng lẻ. | Monolithic runner (đã dùng, đã bỏ). |
| **Accumulating envelope** | Stage sau tự nhiên có đủ context; người dùng không phải join nhiều file; hợp đồng dữ liệu là một chỗ duy nhất. Trade-off: file to dần về cuối (49 KB → 549 KB trên dataset 100 sample — chấp nhận được cho quy mô học thuật). | Mỗi stage một shape input tối thiểu — ít dư thừa nhưng bắt người dùng tự ghép file. |
| **`process()` là code path duy nhất** cho cả CLI lẫn runner | Loại trừ nguyên một lớp bug "chạy lẻ đúng, chạy chuỗi sai" (hoặc ngược lại). | Glue tập trung trong runner — chính là kiến trúc monolithic vừa bỏ. |
| **Validate ở ranh giới, stdlib-only** | Lỗi thật cần bắt là "nối sai thứ tự stage" và "sửa tay làm hỏng file" — bảng key/type khai báo là đủ, không đáng thêm pydantic/jsonschema vào dependency (requirements chỉ có `pytest`). | Thư viện validation ngoài. |
| **Deterministic tuyệt đối** (rule-based, không ML/LLM/API, không random, không phụ thuộc giờ hệ thống) | Yêu cầu nghiên cứu: kết quả tái lập được; yêu cầu vận hành: chạy lại là cách phục hồi sự cố an toàn nhất. Đã kiểm chứng: 2 lần chạy → `diff -r` rỗng. | — |
| **Defense in depth cho temporal validity** | Invariant quan trọng nhất của đề tài (không dùng tin tương lai). Retriever lọc ở stage 2, ForecastModel lọc lại lần nữa ở stage 4 (`TEMPORAL_LEAKAGE_BLOCKED` warning) — kể cả khi ai đó sửa file trung gian nhét tin tương lai vào, dự báo vẫn không dùng nó. | Tin tưởng một điểm lọc duy nhất. |

---

## 4. Khi một phần gặp sự cố, phần còn lại bị ảnh hưởng ra sao

Tính chất nền tảng: các stage **ghép nối lỏng qua file, chạy tuần tự, không giữ state ngoài file output**. Vì vậy sự cố chỉ lan **về phía sau** (downstream), không bao giờ lan ngược.

### Ma trận sự cố

| Sự cố | Phạm vi ảnh hưởng | Phần KHÔNG bị ảnh hưởng | Phục hồi |
|---|---|---|---|
| CSV đầu vào thiếu cột/không tồn tại | `ingest` dừng ngay, exit 2, **không file nào được ghi** | Toàn bộ (chưa có gì chạy) | Sửa CSV, chạy lại từ đầu |
| Stage N crash giữa chừng (bug nội bộ → traceback) | Stage N không ghi output; stage N+1… không có input để chạy | File `01…(N-1)` **vẫn nguyên vẹn và hợp lệ** — mỗi file được ghi trọn một lần sau khi stage hoàn tất, không có ghi dở | Sửa bug, chạy lại **từ stage N** bằng CLI rời với file N-1 — không phải chạy lại từ đầu |
| File trung gian bị sửa tay làm hỏng schema | Stage kế tiếp từ chối chạy: exit 2, message nêu đích danh `sample_id` + key lỗi | Các file khác; stage trước | Sửa file hoặc tái sinh nó từ file trước đó |
| File trung gian bị nhét tin tương lai (schema vẫn hợp lệ) | Lớp lọc thứ hai trong ForecastModel loại tin đó + ghi warning `TEMPORAL_LEAKAGE_BLOCKED` — invariant temporal **không thể bị phá từ một điểm** | Kết quả dự báo | Không cần — hệ thống tự vệ |
| Một sample lỗi trong batch 100 sample | Validator liệt kê **tất cả** lỗi của mọi sample trong một lần chạy rồi dừng cả envelope (fail-fast, không xử lý nửa vời) | — | Sửa đúng các sample được nêu tên |
| Runner bị ngắt (Ctrl-C) giữa chuỗi | Như "stage N crash": file đã ghi vẫn dùng được | File đã ghi | Chạy tiếp bằng CLI rời, hoặc chạy lại runner — vì deterministic, kết quả y hệt |
| Cột giá B3 (`next_day_return`, `price_5d_return`) thiếu trong CSV | Chỉ chất lượng kết quả B3 giảm (mặc định 0.0 → market_consistent tính trên số 0) — **không lỗi, không chặn chuỗi** | Toàn bộ stage khác | Bổ sung cột nếu cần B3 thật |
| `export_csv` lỗi | Chỉ mất 6 CSV; toàn bộ kết quả vẫn nằm đầy đủ trong `08_market.json` | 8 envelope JSON | Chạy lại riêng `python -m src.export_csv` |
| `agent_trace.py` (B4) hỏng | **Không ảnh hưởng gì** đến chuỗi dự báo — nằm ngoài runtime | Tất cả | Độc lập |
| Dashboard (Streamlit) crash | Chỉ mất giao diện xem — pipeline không biết dashboard tồn tại, không có đường ghi ngược | Toàn bộ pipeline, `outputs/` | Khởi động lại `streamlit run` |
| Pipeline chưa chạy / `08_market.json` chưa tồn tại | Dashboard hiện lỗi tiếng Việt + hướng dẫn chạy runner, `st.stop()` — không crash, không hiện dữ liệu sai | Pipeline (chưa chạy nên không có gì hỏng) | Chạy `python -m src.runner ...` |

### Ba cơ chế giới hạn sự cố

1. **Fail-fast tại ranh giới, không nuốt lỗi**: input hỏng → dừng ngay với message chỉ đích danh chỗ hỏng (exit 2); bug nội bộ → traceback nổi lên nguyên vẹn. Không có trạng thái "chạy tiếp với dữ liệu sai" — với một hệ thống mà mục đích là *đo lường sự trung thực*, kết quả sai lệch âm thầm nguy hiểm hơn dừng hẳn.
2. **File trung gian = checkpoint tự nhiên**: sự cố ở đâu, chuỗi đứt ở đó, và mọi thứ trước điểm đứt là điểm khôi phục sẵn dùng.
3. **Determinism = phục hồi an toàn**: mọi chiến lược phục hồi quy về "chạy lại" — và chạy lại luôn cho đúng kết quả cũ, không có side effect tích lũy.

### Giới hạn đã biết (trade-off chấp nhận)

- **Không có xử lý per-sample khi lỗi giữa batch**: một sample làm class raise sẽ dừng cả stage (thay vì bỏ qua sample đó). Chấp nhận vì quy mô học thuật nhỏ và fail-fast được ưu tiên hơn tính liên tục.
- **Không chạy song song**: chuỗi tuần tự đơn tiến trình. Với 100 sample chạy dưới 2 giây — không đáng đánh đổi determinism.
- **Envelope phình to theo chiều dài chuỗi**: hệ quả trực tiếp của thiết kế accumulating; sẽ thành vấn đề nếu dataset lớn gấp ~1000 lần, khi đó cần chuyển sang tham chiếu file thay vì nhúng.

---

## 5. Đánh giá tổng thể

**Điểm mạnh**: ranh giới thành phần rõ (mỗi stage một trách nhiệm, một hợp đồng dữ liệu); quan sát được toàn bộ dòng dữ liệu; một code path duy nhất; không dependency ngoài `pytest`; invariant quan trọng nhất (temporal validity) được bảo vệ hai lớp; 410 unit test xanh; xác minh thực nghiệm trên dataset mẫu 100 sample: accuracy 74%, 21 tin tương lai bị chặn, output tái lập byte-for-byte.

**Phù hợp cho**: demo học thuật, nghiên cứu faithfulness, chấm điểm theo giai đoạn — đúng mục tiêu đồ án.

**Không phù hợp cho** (và không nhắm tới): giao dịch thật, dữ liệu streaming, quy mô lớn, multi-user.
