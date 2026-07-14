## Why

Baseline pipeline V1 (`src/stages/forecast_model.py`) hiện là rule-based vote
trên số lượng `expected_direction` (UP/DOWN/HOLD) — quá yếu để mô hình hoá tương
tác evidence-mạnh và confidence nhuyễn. Đồ án môn học yêu cầu một model thật (ML/DL)
để chứng minh kiến trúc **Attention Evidence Aggregator** có thể nắm được tương
tác giữa nhiều evidence và cải thiện faithful analysis (B-metrics).

Vì V1 vẫn đang là baseline production và 6 nơi downstream chỉ đọc các field
scalar (`prediction`/`confidence`/`class_confidences`/`score`), ta **xoá hẳng
rule-based code** (giữ lại trong git history) và thay bằng một pipeline DL
gồm 2 phần:

- **FinBERT** (ProsusAI/finbert, frozen) restore từ `origin/AI-coding` — thay
  keyword-matching trong `src/stages/evidence_extractor.py`.
- **Attention Evidence Aggregator** (PyTorch nn.Module) trong
  `src/stages/forecast_model.py` — trainable, train trên Google Colab T4,
  checkpoint được commit vào `models/evidence_aggregator_v1.pt`.

## What Changes

### Modified Capabilities

- `forecasting` — `src/stages/forecast_model.py` được rewrite từ rule-based vote
  sang PyTorch `AttentionEvidenceAggregator`:
  - 7 đặc trưng mỗi evidence item (`[pos_prob, neg_prob, neutral_prob,
    support_score, dir_up, dir_down, dir_hold]`).
  - `nn.Linear(7, 32)` projection → `nn.Linear(32, 1)` attention scores,
    softmax theo chiều evidence → weighted average pooling.
  - Concat với `[price_5d_return, volume_change]` (từ sample B3 fields) → head
    `Linear(34, 16) → ReLU → Dropout(0.3) → Linear(16, 3) → softmax`.
  - `MODEL_VERSION = "attention_evidence_v1"`.
  - `predict()`/`predict_without_evidence()` gọi `model.eval() + torch.no_grad()`
    + seed cố định để đảm bảo **seed reproducibility** (không strict byte — đồ án
    không yêu cầu trading production).

- `evidence-extraction` — `src/stages/evidence_extractor.py`:
  - Restore `src/finbert_sentiment.py` từ `origin/AI-coding`.
  - Thay `_match_keywords`/`POSITIVE_KEYWORDS`/`NEGATIVE_KEYWORDS` bằng
    `FinbertSentimentScorer.score(texts)`. Mỗi evidence item có thêm field
    `sentiment_probs = {"positive": p, "negative": p, "neutral": p}` (feature cho
    Attention model).
  - `EXTRACTION_METHOD = "finbert_sentiment_v1"`.
  - **Gãy invariant cũ** "`EvidenceExtractor.POSITIVE_KEYWORDS` là single source
    of truth cho polarity" — không còn áp dụng cho V3. Downstream đã được audit
    (Task 0.5) — không phụ thuộc vào `POSITIVE_KEYWORDS` ngoài `tests/test_evidence_extractor.py`,
    test này sẽ viết lại.

### New Capabilities

- `evidence-aggregation-ml` — `scripts/train_evidence_aggregator.py` + `notebooks/train_evidence_aggregator_colab.ipynb`:
  trainable PyTorch model với CLI argparse (`--device cpu|cuda --epochs N --lr X`),
  Adam + CrossEntropyLoss, early-stop theo val loss, evaluate (`accuracy`,
  macro-F1, confusion matrix), benchmark eager vs `torch.compile` (Colab T4).
  Checkpoint được lưu vào `models/evidence_aggregator_v1.pt`, **commit vào
  repo** (offline-friendly, runtime pipeline load từ path cứng).

## Impact

- **`src/finbert_sentiment.py` (mới)**: restore từ `origin/AI-coding`, CPU-safe
  lazy-load, giữ nguyên logic.
- **`src/stages/evidence_extractor.py` (sửa)**: thay keyword matching bằng
  FinBERT call. Output schema mở rộng 1 field (`sentiment_probs`). Stage `process()`
  shape không đổi (chỉ thêm field trong mỗi evidence dict).
- **`src/stages/forecast_model.py` (rewrite)**: xoá `_vote`/`_compute_confidence`,
  `MODEL_VERSION = "attention_evidence_v1"`, thêm `AttentionEvidenceAggregator`
  nn.Module, `load_checkpoint(path)`. Public API (`predict()`,
  `predict_without_evidence()`, `predict_batch()`,
  `compute_accuracy_and_confusion()`) giữ nguyên.
- **`scripts/train_evidence_aggregator.py` (mới)**: train script với argparse.
- **`notebooks/train_evidence_aggregator_colab.ipynb` (mới)**: thin wrapper
  clone repo + pip + chạy train script + benchmark.
- **`models/evidence_aggregator_v1.pt` (mới)**: checkpoint, commit vào repo.
- **`tests/test_forecast_model.py` (rewrite)**: bỏ test theo rule-based
  (đã liệt kê trong Task 0.4 audit), thêm test cho Attention aggregator với
  checkpoint cố định + tolerance `1e-6` float.
- **`tests/test_evidence_extractor.py` (rewrite)**: bỏ test theo keyword matching.
- **`tests/test_finbert_sentiment.py` (mới)**: restore từ `origin/AI-coding`.
- **`requirements.txt`**: thêm `torch`, `transformers` (core, không optional).
- **`CLAUDE.md`, `README.md`**: sửa dòng invariant "no ML", architecture diagram.
- **Không gãy**: 6 nơi downstream (`evidence_selector`, `faithfulness_*`,
  `sufficiency_evaluator`, `market_analyzer`, `export_csv`, `dashboard/*`) — chỉ
  đọc field, không phụ thuộc cách tính.
- **Runner x2 diff**: không còn byte-identical strict — chuyển sang tolerance
  `1e-6` float (đồ án không cần byte-deterministic, nhưng cần test x2 diff pass).
