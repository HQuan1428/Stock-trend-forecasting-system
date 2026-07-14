# Design: Envelope Dashboard

## Context

Kiến trúc hiện tại: chuỗi 9 stage CLI với accumulating envelope; `outputs/08_market.json` chứa toàn bộ state per-sample (news, valid/invalid_news, evidence, forecast, selection, coverage, faithfulness, sufficiency, market). Đã có dữ liệu thật: 100 samples, 21 tin leakage, accuracy 74%. Dashboard cũ (Streamlit 9 tab, đọc 6 CSV qua adapter) còn trong git history (`git show 1638855:src/dashboard/...`) — tham khảo pattern chart/màu được, nhưng lớp data hoàn toàn khác.

## Goals / Non-Goals

**Goals:**
- Đạt A7: ≥4 bảng/hình bắt buộc + radar (§9) + demo flow §11.1 + acceptance §4.2.
- Thể hiện trực quan B1–B4.
- Read-only tuyệt đối; logic tách khỏi Streamlit để pytest được.
- Thiếu/hỏng input → message hướng dẫn, không crash.

**Non-Goals:**
- Không re-run model/pipeline từ dashboard (toggle ablation dùng số đã tính sẵn).
- Không export PNG tự động (không thêm kaleido) — dùng nút camera của Plotly.
- Không auto-refresh khi file đổi; không multi-user/auth.
- Không đụng stage code, schema, runner.

## Decisions

### D1: Envelope 08_market.json là data source duy nhất

`data_loader.load_envelope_view(path)` đọc JSON, validate từng sample bằng `schema.validate_sample(sample, "export_csv")` (bảng key đầy đủ nhất), rồi build các view-model: DataFrame per-sample (flatten các metric), DataFrame evidence (explode), DataFrame leakage. Lỗi (thiếu file/JSON hỏng/schema fail) → raise `DashboardDataError` với message hướng dẫn chạy `python -m src.runner`; `app.py` bắt và hiển thị `st.error` + `st.stop()`.

- **Vì sao**: một file có đủ mọi thứ (kể cả news_text và per-evidence chi tiết cho Live Demo) — CSV không có; validate tái dùng đúng validator của ranh giới stage.
- **Alternative bị loại**: đọc 6 CSV + adapter như dashboard cũ — phải join theo sample_id và vẫn thiếu dữ liệu chi tiết.

### D2: Ba lớp thuần + một lớp render

`data_loader` (I/O + view-model) → `metrics` (tổng hợp: distribution, accuracy, avg, B1/B2/B3 aggregates) → `charts` (nhận số liệu đã tổng hợp, trả `plotly.graph_objects.Figure`) đều là hàm thuần import được không cần Streamlit. `components.py` + `app.py` chỉ render (`st.*`). Test toàn bộ logic bằng pytest với envelope fixture nhỏ dựng trong test — không cần server, không cần headless browser.

### D3: Toggle "Remove cited evidence" dùng ablation đã tính sẵn

Live Demo đọc `faithfulness.confidence_after_removal`, `prediction_after_removal`, `confidence_drop` — các con số do FaithfulnessEvaluator tính ở stage 6. Toggle chỉ đổi cách hiển thị (trước/sau + delta + banner verdict).

- **Vì sao**: giữ invariant "dashboard không gọi pipeline"; demo vẫn đúng kịch bản §11.1 ("bấm hoặc **mô phỏng** chức năng Remove cited evidence"); deterministic vì số liệu từ file.
- **Alternative bị loại**: gọi `ForecastModel.predict_without_evidence` live — phá invariant read-only, thêm code path thứ hai cho ablation.

### D4: Verdict banner map từ `faithfulness.verdict`

6 verdict nội bộ → 4 nhóm hiển thị: `strong/moderate/weak_faithful_candidate` → xanh "Evidence có dấu hiệu FAITHFUL" (kèm mức độ); `decorative_explanation_risk` → vàng "Evidence có thể chỉ là giải thích trang trí"; `invalid_temporal_leakage` → đỏ "Vi phạm temporal validity"; `unsupported_evidence` → cam "Evidence không ủng hộ prediction". Mapping là hàm thuần trong `metrics.py` (test được), text tiếng Việt.

### D5: Radar 5 trục gộp A + B metrics

Trung bình toàn dataset (hoặc theo filter ticker): `temporal_validity`, `evidence_support`, `normalized_drop` (= min(max(drop,0)/0.30, 1) — cùng công thức FaithfulnessMetrics), `sufficiency_score` (B1), `counterevidence_coverage` (B2). Tất cả đã ở [0,1] nên radar không cần scale thêm.

### D6: B4 đọc trace log qua API có sẵn

`agent_trace.load_trace_log("outputs/run_log.json")` + `summarize_trace` — file không tồn tại thì API trả `[]` → tab hiện `st.info` hướng dẫn, không lỗi. Dashboard không tự tạo/ghi log (read-only).

## Risks / Trade-offs

- [Envelope 549KB parse mỗi lần rerun Streamlit] → `@st.cache_data` trên hàm load theo mtime của file; 100 samples là nhỏ, không đáng ngại.
- [Deps streamlit/plotly làm nặng requirements] → chấp nhận: đề bài §13 gợi ý đúng stack này; pipeline core không import gì từ dashboard nên vẫn chạy được với stdlib.
- [Streamlit API đổi giữa các version] → dùng API ổn định (st.tabs, st.selectbox, st.toggle, st.dataframe, st.plotly_chart); không pin version trong requirements (nhất quán với style hiện tại).
- [Test không cover lớp render] → chấp nhận: smoke test import app.py + test toàn bộ hàm thuần; render layer mỏng nhất có thể.
