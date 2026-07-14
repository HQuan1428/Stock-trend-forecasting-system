# Tasks: Forecast Model V3 — Attention Evidence Aggregator + FinBERT

## 1. OpenSpec change folder (Task 1)
- [x] 1.1 Tạo `openspec/changes/forecast-model-attention/` + `.openspec.yaml`
- [x] 1.2 `proposal.md` (why / what changes / impact)
- [x] 1.3 `design.md` (D1-D8)
- [x] 1.4 `tasks.md` (file này)
- [x] 1.5 `specs/forecasting/spec.md` (delta — viết sau khi code xong, điền
      scenario cuối cùng)

## 2. Restore FinBERT + đổi Evidence Extractor (Plan.md Task 1)
- [ ] 2.1 Verify branch `origin/AI-coding` tồn tại + extract file:
      ```bash
      git ls-remote origin AI-coding
      git show origin/AI-coding:src/finbert_sentiment.py > src/finbert_sentiment.py
      ```
      Đảm bảo `FinbertSentimentScorer`, `FinbertLoadError` đầy đủ.
- [ ] 2.2 `tests/test_finbert_sentiment.py` — restore từ
      `origin/AI-coding:tests/test_finbert_sentiment.py` (nếu thiếu, viết
      tay: test load-failure graceful khi offline).
- [ ] 2.3 `src/stages/evidence_extractor.py`:
      - Import `FinbertSentimentScorer` từ `src.finbert_sentiment`.
      - Xoá `_find_keyword_occurrences`, `POSITIVE_KEYWORDS`,
        `NEGATIVE_KEYWORDS`, `KEYWORD_TO_POLARITY`, `KEYWORDS`,
        `_MAX_TOKEN_GAP`, `_resolve_overlaps`. Giữ
        `POLARITY_TO_DIRECTION`, `SUPPORT_SCORES`, `EXTRACTION_METHOD`.
      - Thêm `FinbertSentimentScorer` instance trong `__init__` hoặc lazy.
      - `extract()` → gọi `scorer.score(texts)`, build evidence dicts với
        thêm `sentiment_probs` field. `polarity` = argmax over
        `sentiment_probs`, `expected_direction` map theo
        `POLARITY_TO_DIRECTION`.
      - `EXTRACTION_METHOD = "finbert_sentiment_v1"`.
      - Empty case: nếu input text empty → trả 1 neutral evidence với
        `sentiment_probs = {"positive": 0.0, "negative": 0.0, "neutral":
        1.0}`, `support_score = 0.5`.
- [ ] 2.4 `requirements.txt`: thêm `torch`, `transformers` (cuối file).
- [ ] 2.5 Rewrite `tests/test_evidence_extractor.py`: bỏ test keyword
      matching cũ, thêm test FinBERT path (mock `FinbertSentimentScorer`
      nếu cần).
- [ ] 2.6 Chạy `pytest tests/test_evidence_extractor.py tests/test_finbert_sentiment.py -v`.

## 3. Viết `AttentionEvidenceAggregator` (Plan.md Task 2)
- [ ] 3.1 Trong `src/stages/forecast_model.py` — XOÁ hẳn (theo Plan §2.5):
      `_vote`, `_compute_confidence`, `_compute_evidence_strength`,
      `_compute_conflict_ratio`, `_compute_class_confidences`,
      `_partition_evidence._copy_evidence`-like không còn cần cho rule-based,
      `_build_rationale`, `MODEL_VERSION = "rule_based_v1"`. KHÔNG giữ code
      chết.
- [ ] 3.2 Thêm `import torch`, `import torch.nn as nn`, `import torch.nn.functional as F`.
- [ ] 3.3 `class AttentionEvidenceAggregator(nn.Module)` theo D1 design.md:
      proj 7→32, attn 32→1, head Linear(34,16)→ReLU→Dropout(0.3)→Linear(16,3).
- [ ] 3.4 `class ForecastModel`:
      - `MODEL_VERSION = "attention_evidence_v1"`.
      - `__init__` lazy-load checkpoint từ `models/evidence_aggregator_v1.pt`
        (raise `ForecastModelError` nếu thiếu).
      - `_build_evidence_features(evidence_list) -> torch.Tensor` theo D4.
      - `_build_price_features(sample) -> torch.Tensor` (lấy
        `price_5d_return` + `volume_change` với default 0.0).
      - `_forward(evidence_list, price_features) -> Dict[str, float]`.
      - `_predict_core(...)` refactor: `torch.manual_seed(SEED)`,
        `model.eval()`, `torch.no_grad()`, gọi `_forward`, map ra dict.
- [ ] 3.5 Public API giữ nguyên: `predict()`, `predict_without_evidence()`,
      `predict_batch()`, `compute_accuracy_and_confusion()`. `build_forecast_request()`
      và `process()` ở cuối file giữ nguyên (downstream dùng).
- [ ] 3.6 Warning codes (`TEMPORAL_LEAKAGE_BLOCKED`, `INVALID_EVIDENCE`,
      `DUPLICATE_EVIDENCE_ID`, `MALFORMED_NEWS_TIME`, `INPUT_ERROR`) —
      giữ logic nhưng viết lại theo PyTorch dict.
- [ ] 3.7 Temporal-filter, dedup: giữ (KHÔNG sửa — temporal validator vẫn
      dùng `TimeUtils.parse_utc`).
- [ ] 3.8 `_default_error_result`: trả `prediction = "HOLD"`,
      `confidence = 0.5`, `class_confidences = {UP: 0.25, DOWN: 0.25,
      HOLD: 0.5}` (uniform khi không có model output).
- [ ] 3.9 `CSV_COLUMNS` giữ nguyên schema.

## 4. Training script `scripts/train_evidence_aggregator.py` (Plan.md Task 3)
- [ ] 4.1 Module docstring mô tả script train 1 lần cho
      `AttentionEvidenceAggregator`. CLI argparse:
      `--device {cpu,cuda}`, `--epochs N`, `--lr X`, `--batch-size B`,
      `--checkpoint-path PATH`.
- [ ] 4.2 `build_training_data(csv_path) -> List[(features, label)]`:
      - Chạy `ingest.process_csv` → `retriever.process` →
        `evidence_extractor.process` trên `data/real_dataset.csv`.
      - Cho mỗi sample: build (evidence_features_tensor,
        price_features_tensor, label_index) theo D4 design.
      - Label mapping: `{"UP": 0, "DOWN": 1, "HOLD": 2}`.
      - Skip sample nếu `sample["label"]` không hợp lệ.
- [ ] 4.3 Split 70/15/15 theo group, seed `42`,
      `random.Random(42).shuffle(group_ids)`.
- [ ] 4.4 `train_model(data, device, epochs, lr, batch_size) -> (model,
      history)`:
      - Adam (`lr=1e-3`), `CrossEntropyLoss()`.
      - Early-stop theo val loss, patience=5.
      - Lưu `best_state_dict` theo val loss.
- [ ] 4.5 `evaluate_model(model, split) -> dict`: accuracy, macro-F1,
      confusion matrix 3×3. Tái dùng pattern `ForecastModel.compute_accuracy_and_confusion`
      (đơn giản hoá — chỉ cần accuracy+F1 cho train report).
- [ ] 4.6 `benchmark_compile(model, split, device) -> dict`:
      warm-up 5 pass, đo avg trên 50 pass, `torch.cuda.synchronize()`
      nếu CUDA. Trả `{eager_ms, compiled_ms, speedup}`.
- [ ] 4.7 `main()`: orchestrate 4.2-4.6, save best checkpoint xuống
      `args.checkpoint_path`. In summary.

## 5. Colab notebook (Plan.md Task 4)
- [ ] 5.1 Tạo `notebooks/train_evidence_aggregator_colab.ipynb` (JSON
      format chuẩn Jupyter nbformat v4).
- [ ] 5.2 7 cells theo D6 design.md (clone, pip, gpu check, train,
      eval, benchmark, save).
- [ ] 5.3 KHÔNG có logic trong cell — chỉ `!command` hoặc gọi hàm.

## 6. Rewrite `tests/test_forecast_model.py` (Plan.md Task 6)
- [ ] 6.1 Xoá: `test_compute_confidence_*`, `test_class_confidences_*`,
      `test_vote_and_confidence_for_canonical_scenarios`,
      `test_evidence_strength_and_conflict_ratio_formulas`,
      `test_confidence_clamping`, test assert `score == X`.
- [ ] 6.2 Giữ: dedup, temporal-filter, warning, partition pro-counter,
      CSV/JSON shape của `predict_batch`,
      `compute_accuracy_and_confusion` shape, edge cases,
      `_validate_request_envelope`, `build_forecast_request`.
- [ ] 6.3 Đổi `test_determinism`: `assert a == pytest.approx(b, abs=1e-6)`
      (per-field).
- [ ] 6.4 Thêm test mới cho Attention aggregator:
      - `test_load_real_checkpoint` — `ForecastModel()` không raise (cần
        `models/evidence_aggregator_v1.pt`).
      - `test_forward_shape_empty_evidence` — empty input → output
        (3,) tensor, softmax sum = 1.
      - `test_predict_returns_valid_label_and_confidence_sums_to_one`
        — fixture cố định, tolerance `1e-6`.
      - `test_predict_without_evidence_changes_prediction_or_confidence`
        — với fixture `removed_evidence_ids`, kết quả trong tolerance
        khác prediction ban đầu HOẶC `class_confidences` khác.
- [ ] 6.5 Chạy `pytest tests/test_forecast_model.py -v` — xanh hết.

## 7. Dọn docstring + invariant (Plan.md Task 5)
- [ ] 7.1 `src/stages/forecast_model.py` docstring: bỏ "MUST NOT call any
      LLM/FinBERT/transformer", thay bằng mô tả Attention + FinBERT input.
- [ ] 7.2 `CLAUDE.md`: sửa invariant "Không có ML/LLM/external API" →
      "Forecast Model V3 dùng Attention Evidence Aggregator (PyTorch,
      trainable qua `scripts/train_evidence_aggregator.py`, checkpoint
      commit vào repo) + FinBERT (ProsusAI/finbert, frozen) làm
      extractor. Không có external API lúc runtime." Đồng thời sửa
      architecture diagram đoạn forecast_model.
- [ ] 7.3 `README.md` (nếu có phần tương ứng) — đồng bộ với 7.2.

## 8. Verification cuối (Plan.md Task 7)
- [ ] 8.1 `pytest tests/ -q` — xanh hết.
- [ ] 8.2 `python -m src.runner --input data/real_dataset.csv --output-dir
      /tmp/outsA` rồi `/tmp/outsB` — diff với tolerance `1e-6` float
      trên mọi file `*.json` và `*.csv` (dùng helper
      `tests/scripts/diff_tolerant.py` hoặc sed inline).
- [ ] 8.3 `04_forecast.json` có `model_version: "attention_evidence_v1"` trên
      tất cả sample.
- [ ] 8.4 Doc-tree OpenSpec: sau khi code xong, sửa
      `openspec/changes/forecast-model-attention/specs/forecasting/spec.md`
      (delta spec) — điền scenarios mới, không pin số cứng (vì accuracy
      còn phụ thuộc training).
- [ ] 8.5 Archive OpenSpec change: di chuyển
      `openspec/changes/forecast-model-attention/` →
      `openspec/changes/archive/2026-07-14-forecast-model-attention/`.
- [ ] 8.6 Sync spec chính: copy delta spec →
      `openspec/specs/forecasting/spec.md` (OVERWRITE V1 cũ).

## 9. Deliverables cho user (Colab)
- [ ] 9.1 Script + notebook đã sẵn sàng.
- [ ] 9.2 Báo cáo cho user: checkpoint path, accuracy trên 70/15/15,
      macro-F1, benchmark table.
