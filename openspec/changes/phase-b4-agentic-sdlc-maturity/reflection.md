# Reflection: Agentic SDLC trong Dự Án Faithful Evidence-Centric Forecasting

`outputs/run_log.json` ghi 40 entry (R001-R040), bao phủ toàn bộ lịch sử dự án — từ scaffold ban đầu (2026-06-21) đến dashboard envelope hiện tại (2026-07-13), không chỉ riêng Phase B.

## 3 Agent Roles và nhiệm vụ cụ thể

### 1. Research Agent (12 entry)
**Nhiệm vụ**: Phân tích bài toán, xác định gap trong hệ thống hiện có, viết OpenSpec (proposal.md + design.md + spec.md).

**Thực tế đã làm trong dự án**:
- Thiết kế kiến trúc pipeline A1-A7 ban đầu từ ChuDe1.md (R001), viết spec cho từng module nền tảng: temporal-retriever, evidence-extractor, evidence-selector, forecast-model-basic, faithfulness-evaluator (R003, R006, R008, R010, R012).
- Phân tích causal chain khi keyword dictionary V1 làm accuracy sập xuống ~27% (100/100 sample dự báo HOLD), viết spec enrich-evidence-keywords-v2 rồi v3, mỗi lần đối chiếu thực nghiệm trực tiếp với `data/sample_dataset.csv` (R016, R019).
- Phân tích gap Phase B (B1 sufficiency, B2 counterevidence coverage, B3 market consistency, B4 agentic trace), xác định ngưỡng (`±0.005`, `±0.02`) và thiết kế schema output (R023, R029).
- Phân tích nợ kiến trúc của `pipeline.py` monolithic (694 dòng, không debug được từng giai đoạn), đề xuất chuyển sang accumulating envelope + per-stage CLI (R035); sau đó phát hiện dashboard v1 đã bị xóa khi dọn repo, đề xuất envelope-dashboard 6 tab (R038).

### 2. Coding Agent (18 entry)
**Nhiệm vụ**: Implement module theo spec đã được human approve, integrate vào pipeline, cập nhật dashboard.

**Thực tế đã làm trong dự án**:
- Implement lần lượt `src/retriever.py`, `src/evidence_extractor.py`, `src/evidence_selector.py`, `src/forecast_model.py`, `src/faithfulness_evaluator.py` theo đúng spec đã approve (R004, R007, R009, R011, R013).
- Vá keyword dictionary 2 vòng (V2 rồi V3) khi Testing Agent báo accuracy chưa đạt, giữ nguyên vocabulary cũ verbatim mỗi lần mở rộng (R017, R020).
- Implement `SufficiencyEvaluator`, `MarketAnalyzer`, `EvidenceSelector.compute_coverage()`, `agent_trace.py` cho Phase B (R024, R027, R030); fix riêng 1 edge case sufficiency_score khi cited_evidence_ids rỗng (R026).
- Refactor toàn bộ 9 module sang OOP class facade cộng thêm, không đổi behavior (R032); fix bug IndexError dashboard sau khi Testing Agent phát hiện (R034).
- Dứt điểm xóa `pipeline.py` monolithic, dựng lại kiến trúc envelope 9-stage + CLI rời (`ingest.py`, `stage_io.py`, `runner.py`, `export_csv.py`, nâng `schema.py` thành validator thật) (R036), rồi dựng lại dashboard trên kiến trúc mới (R039).

### 3. Testing/Review Agent (10 entry)
**Nhiệm vụ**: Viết test cases từ spec scenarios, verify output, review code quality, chạy pipeline thực để bắt bug số liệu (không chỉ đọc code).

**Thực tế đã làm trong dự án**:
- Viết test cho từng module nền tảng ngay sau khi implement (R005 temporal leakage scenarios).
- Chạy pipeline thật trên sample dataset và tự phát hiện 2 lần liên tiếp accuracy không đạt (V1: 27% vì 100% HOLD; V2: vẫn 51/100 sample false-HOLD) — đây là phát hiện từ số liệu thực tế, không phải từ đọc code (R015, R018).
- Phát hiện bug logic `sufficiency_score` trả sai giá trị ở edge case cited_evidence_ids rỗng bằng cách viết test trước khi tin code đúng (R025).
- Verify byte-for-byte output trước/sau refactor OOP, phát hiện thêm 1 bug độc lập (IndexError `_TAB_LABELS` dashboard thiếu 3/8 tab) trong lúc verify (R033).
- Verify CLI rời và runner cho ra output giống hệt nhau, verify schema validation trả đúng exit code, verify dashboard tuân thủ invariant read-only tuyệt đối (R037, R040).

---

## Human Control Points (Quality Gates)

Quy trình Agentic SDLC trong dự án này không tự động hoàn toàn — con người kiểm soát tại các điểm chính:

| Quality Gate | Mô tả | Kết quả |
|---|---|---|
| **Spec Review** | User đọc proposal.md + design.md trước khi approve | Accepted (toàn bộ 40 entry) |
| **pytest gate** | Toàn bộ test suite phải pass sau mỗi change | 36/40 entry passed ngay; 4 entry fail lần đầu, fix xong pass |
| **Pipeline/output review** | Chạy pipeline thật, xem CSV/JSON output để verify số liệu hợp lý (không chỉ code chạy không lỗi) | Phát hiện 3/4 quality-gate-fail từ số liệu thực (R015, R018, R033), không phải từ đọc code |
| **Refactor safety review** | So sánh output byte-for-byte trước/sau mỗi lần refactor lớn | Passed (OOP refactor, envelope refactor) |

**Con người không approve thì AI agent không tiến hành implement.** Quy trình: `/opsx:propose` → user review → user duyệt → `/opsx:apply` → `/opsx:archive`.

### 4 lần quality gate "failed" thật sự trong lịch sử dự án

| Entry | Vấn đề bị bắt | Ai bắt | Cách phát hiện |
|---|---|---|---|
| R015 | Keyword dictionary V1 quá thưa → accuracy 27% | Testing/Review Agent | Chạy pipeline thật, đọc số liệu CSV, không phải review code |
| R018 | V2 vẫn còn 51/100 sample false-HOLD | Testing/Review Agent | So label thật với prediction trên toàn bộ sample |
| R025 | `sufficiency_score` sai khi cited_evidence_ids rỗng | Testing/Review Agent | Viết test edge case trước khi tin code |
| R033 | IndexError `_TAB_LABELS` thiếu tab sau refactor | Testing/Review Agent | Chạy dashboard thật trong lúc verify byte-for-byte |

Cả 4 lần đều được Coding Agent fix ngay ở entry kế tiếp, quality_gate quay lại "passed" trước khi merge tiếp bước sau — không có bug nào bị mang sang giai đoạn sau.

---

## Bài học rút ra từ Agentic SDLC

1. **Spec trước, code sau** — OpenSpec workflow buộc Research Agent viết spec rõ ràng trước. Boundary condition (ngưỡng `±0.005`, `±0.02`, timezone=UTC, verdict labels...) được quyết định ở design.md, không phải quyết định ngẫu hứng trong lúc code.

2. **Human-in-the-loop tại spec level hiệu quả hơn tại code level** — review proposal + design trước khi có 1 dòng code nào, một quyết định sai ở tầng design (ví dụ ngưỡng consistency) sẽ lan ra toàn bộ implementation; phát hiện sớm tiết kiệm chi phí sửa.

3. **Testing Agent phải chạy thực tế, không chỉ đọc code** — cả 2 lần bắt được accuracy collapse (R015, R018) đều đến từ việc chạy pipeline trên dữ liệu thật và so sánh số liệu, không phải từ code review tĩnh. Đây là quality gate quan trọng nhất trong toàn bộ trace.

4. **Refactor lớn cần bước "so byte-for-byte" riêng** — 2 lần refactor kiến trúc lớn nhất dự án (OOP hóa R032, xóa pipeline.py dựng lại envelope R036) đều đi kèm một bước verify độc lập so sánh output cũ/mới, và cả 2 lần đều bắt thêm được bug phụ không liên quan trực tiếp đến refactor (R033).

5. **Trace log = accountability** — `run_log.json` ghi lại chính xác ai làm gì, input/output, và kết quả quality gate qua toàn bộ vòng đời dự án (không chỉ 1 phase), cho phép audit lại vì sao một quyết định kỹ thuật (ví dụ V1→V2→V3 keyword) từng tồn tại.

6. **AI không thay thế human judgment** — AI agent đề xuất threshold, kiến trúc, vocabulary dựa trên phân tích dữ liệu và domain knowledge. Nhưng quyết định cuối cùng có áp dụng hay không luôn thuộc về con người (user approve từng spec trước khi Coding Agent được phép implement).
