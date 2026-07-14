# Forecast Model — Design (V3: Attention Evidence Aggregator + FinBERT)

## Context

Baseline V1 rule-based chỉ đếm số `expected_direction` và clamp `[0.5, 0.95]`.
Đồ án môn Công nghệ mới yêu cầu model thật để faithful evidence analysis
(B-metrics) có ý nghĩa. Kiến trúc V3 gồm 2 phần:

1. **FinBERT** (ProsusAI/finbert, **frozen**) — làm nguồn embedding polarity
   cho evidence extractor. Thay keyword matching.
2. **Attention Evidence Aggregator** (PyTorch, **trainable**) — forecast
   model mới: cho mỗi nhóm evidence của một sample, học weighted average
   pooling qua attention, kết hợp với 2 price features (`price_5d_return`,
   `volume_change`) từ sample B3 fields, đưa qua MLP head để ra 3 class
   probabilities.

Audit trước khi viết design (đã làm):
- Audit 0.1 grep: `rule_based_v1`/`_vote`/`_compute_confidence` chỉ nằm
  trong `forecast_model.py` (sẽ xoá). `POSITIVE_KEYWORDS`/`NEGATIVE_KEYWORDS`
  chỉ nằm trong `evidence_extractor.py` + `test_evidence_extractor.py`
  (sẽ rewrite).
- Audit 0.2: import OK, không hàm mồ côi.
- Audit 0.5: `faithfulness_metrics.py`/`sufficiency_evaluator.py` không ép
  `[0.5, 0.95]`, chỉ dùng `class_confidences` với fallback. **Không cần sửa**.

## Goals / Non-Goals

**Goals**
- FinBERT restore từ `origin/AI-coding`, lazy-load, CPU-safe cho test.
- Attention Evidence Aggregator viết trong `src/stages/forecast_model.py`,
  train trên Google Colab T4, checkpoint commit vào repo.
- `MODEL_VERSION = "attention_evidence_v1"`.
- Public API của `ForecastModel` không đổi (`predict`,
  `predict_without_evidence`, `predict_batch`,
  `compute_accuracy_and_confusion`).
- Pipeline runtime vẫn deterministic trong tolerance `1e-6` float (qua
  `model.eval() + torch.no_grad()` + seed cố định).
- Notebook Colab minh hoạ `torch.compile` vs eager (1 cell).

**Non-Goals**
- Không thay stage nào khác ngoài `forecast_model.py` +
  `evidence_extractor.py` (evidence_selector/faithfulness/sufficiency/market
  đều KHÔNG phụ thuộc cách tính — đã verify ở audit 0.5).
- Không thay vị trí stage trong pipeline.
- Không dựng lại rule-based code dưới dạng "song song baseline" — chỉ
  số liệu cũ (nếu có) dùng để tham chiếo trong report; KHÔNG chạy lại
  rule-based ở production.
- Không thay đổi schema envelope (`forecast` key trong sample vẫn là dict
  có cùng field set).
- KHÔNG thêm constant label/class into model — model chỉ nhận feature
  numeric, label dùng chỉ trong training.

## Decisions

**D1 — Kiến trúc model (đúng Plan.md §2.1-2.4)**

```python
# Evidence item features (7-dim):
# [pos_prob, neg_prob, neutral_prob, support_score, dir_up, dir_down, dir_hold]
feature = [0.82, 0.10, 0.08, 0.82, 1.0, 0.0, 0.0]

class AttentionEvidenceAggregator(nn.Module):
    def __init__(self):
        super().__init__()
        self.proj = nn.Linear(7, 32)
        self.attn = nn.Linear(32, 1)
        self.head = nn.Sequential(
            nn.Linear(34, 16),  # 32 (group vec) + 2 (price features)
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(16, 3),
        )

    def forward(self, evidence_features, price_features):
        # evidence_features: (N, 7) — N có thể = 0 (empty batch)
        # price_features: (2,) — [price_5d_return, volume_change]
        if evidence_features.shape[0] == 0:
            group = torch.zeros(32)
        else:
            h = self.proj(evidence_features)            # (N, 32)
            scores = self.attn(h)                       # (N, 1)
            weights = torch.softmax(scores, dim=0)      # (N, 1), sum=1
            group = (weights * h).sum(dim=0)            # (32,)
        combined = torch.cat([group, price_features])   # (34,)
        logits = self.head(combined)                    # (3,)
        return F.softmax(logits, dim=-1)                # {UP, DOWN, HOLD}
```

**D2 — Checkpoint path cứng**

`models/evidence_aggregator_v1.pt`. Runtime `predict()` load khi khởi tạo
class instance (lazy, cached). Nếu file không tồn tại → raise `ForecastModelError`
(đồ án commit checkpoint vào repo nên luôn có).

**D3 — Determinism: seed reproducibility**

`_predict_core`:
```python
def _predict_core(self, input_data, ...):
    torch.manual_seed(SEED)  # SEED = 42
    self.model.eval()
    with torch.no_grad():
        ... forward ...
```
2 lần gọi `predict()` cùng input → cùng output trong tolerance `1e-6` float.
Test `test_determinism` đổi sang `pytest.approx(..., abs=1e-6)` thay vì
`assert a == b` strict.

**D4 — Feature extraction (FinBERT output → tensor)**

Mỗi evidence dict (sau `evidence_extractor.process`):
```python
{
    "evidence_id": ...,
    "news_id": ...,
    "news_time": ...,
    "evidence_text": <đoạn FinBERT input>,
    "polarity": "positive" | "negative" | "neutral",
    "expected_direction": "UP" | "DOWN" | "HOLD",
    "support_score": float,  # max of sentiment_probs
    "sentiment_probs": {"positive": p, "negative": p, "neutral": p},
}
```

Trong `forecast_model.py._build_evidence_features(evidence_list)`:
```python
def _build_evidence_features(evidence_list):
    feats = []
    for e in evidence_list:
        sp = e["sentiment_probs"]
        direction = e["expected_direction"]
        feats.append([
            float(sp["positive"]),
            float(sp["negative"]),
            float(sp["neutral"]),
            float(e["support_score"]),
            1.0 if direction == "UP" else 0.0,
            1.0 if direction == "DOWN" else 0.0,
            1.0 if direction == "HOLD" else 0.0,
        ])
    return torch.tensor(feats, dtype=torch.float32)  # (N, 7)
```

Price features lấy từ sample dict (key `price_5d_return`, `volume_change`)
với default `0.0` khi thiếu (đã được ingest chuẩn hoá rồi).

**D5 — Training data flow**

`scripts/train_evidence_aggregator.py`:
1. `build_training_data(csv_path)` → chạy `ingest.process_csv` →
   `retriever.process` → `evidence_extractor.process` trên
   `data/real_dataset.csv` → list of (evidence_features_tensor,
   price_features_tensor, label_index).
2. Split 70/15/15 theo group bằng `random.Random(42).shuffle(group_ids)`.
3. `train_model(data, device, epochs, lr)` — Adam + CrossEntropyLoss,
   early-stop theo val loss (patience=5).
4. `evaluate_model(model, split)` — accuracy, macro-F1, confusion matrix.
5. `benchmark_compile(model, split, device='cuda')` — eager vs
   `torch.compile(model, backend='inductor')`, đo `time.perf_counter()`
   (cần `torch.cuda.synchronize()` nếu CUDA).
6. Save checkpoint best val → `models/evidence_aggregator_v1.pt`.

CLI:
```
python3 scripts/train_evidence_aggregator.py --device cpu --epochs 2  # dry-run
python3 scripts/train_evidence_aggregator.py --device cuda --epochs 50  # Colab
```

**D6 — Notebook Colab (Plan.md §4)**

`notebooks/train_evidence_aggregator_colab.ipynb` — chỉ 7 cells:
1. `!git clone` + `cd`.
2. `!pip install -r requirements.txt`.
3. Verify GPU (`torch.cuda.is_available()`, `!nvidia-smi`).
4. `from scripts.train_evidence_aggregator import build_training_data, train_model, evaluate_model; data = build_training_data('data/real_dataset.csv'); model, history = train_model(data, device='cuda', epochs=50)`.
5. `evaluate_model(model, data.test)` — in kết quả.
6. `benchmark_compile(model, data.test, device='cuda')` — in `eager_ms`,
   `compiled_ms`, `speedup`.
7. Save checkpoint + hướng dẫn commit `models/evidence_aggregator_v1.pt`.

KHÔNG có logic trong cell nào — chỉ gọi hàm.

**D7 — FinBERT integration (Plan.md §1)**

Restore `src/finbert_sentiment.py` từ `origin/AI-coding` (đã verify branch tồn tại):
```bash
git show origin/AI-coding:src/finbert_sentiment.py > src/finbert_sentiment.py
```

Trong `evidence_extractor.py`:
- Thay `_find_keyword_occurrences` bằng `FinbertSentimentScorer().score(texts)`
  (lazy, model load on first call).
- Mỗi evidence item giữ nguyên schema cũ + thêm `sentiment_probs`.
- `EXTRACTION_METHOD = "finbert_sentiment_v1"`.
- Empty keyword-match edge case: nếu 0 sentence → trả 1 neutral evidence
  với `sentiment_probs = {"positive": 0.0, "negative": 0.0, "neutral": 1.0}`.

`tests/test_finbert_sentiment.py` restore từ `origin/AI-coding`. Khi FinBERT
load fails (offline), test chỉ assert load failure handling — không yêu cầu
network/model.

**D8 — Test rewrite**

Cũ (`tests/test_forecast_model.py`):
- Xoá: `test_compute_confidence_*`, `test_class_confidences_*`,
  `test_vote_and_confidence_for_canonical_scenarios`,
  `test_evidence_strength_and_conflict_ratio_formulas` (công thức V1 cũ).
- Xoá: assert `score == X` (giờ `score` không còn ý nghĩa, là field 0).
- Giữ: test dedup/temporal/warning/partition pro-counter/CSV/JSON shape/
  `compute_accuracy_and_confusion` shape/edge cases.
- Đổi `test_determinism` từ `assert a == b` sang
  `assert a == pytest.approx(b, abs=1e-6)` (toàn dict — phải so từng
  field).

Mới (thêm):
- `test_attention_aggregator_load_checkpoint` — load
  `models/evidence_aggregator_v1.pt` thành công.
- `test_forward_shape` — input empty → output (3,) tensor.
- `test_predict_with_real_checkpoint` — gọi `predict()` 1 fixture,
  assert `prediction in {UP,DOWN,HOLD}`,
  `sum(class_confidences.values()) == approx(1.0, abs=1e-6)`,
  `confidence == class_confidences[prediction]` (trong tolerance).

Cũ (`tests/test_evidence_extractor.py`):
- Xoá: test assert theo keyword matching cụ thể.
- Thêm: test FinBERT path (mock `FinbertSentimentScorer`).

## Risks / Trade-offs

**[Risk] FinBERT download lúc train/test** → Mitigation:
- FinBERT `lazy-load`, CPU-safe, raise `FinbertLoadError` graceful nếu
  không có network/model.
- Test offline skip nếu không load được (mark `pytest.skip`).

**[Risk] Forecast_aggregator accuracy trên 395 sample có thể tệ hơn V1 rule-based** → Acceptable:
đồ án học thuật ưu tiên kiến trúc + faithful analysis hơn accuracy.

**[Risk] Checkpoint không commit (LFS hoặc kích thước lớn)** → Mitigation:
- Checkpoint nhỏ (~32+16*34 + 16*3 ≈ 1.7K params × 4 bytes ≈ 7KB).
- Không cần Git LFS.

**[Risk] `torch.compile` benchmark trên Colab T4 có thể không ổn định giữa các lần chạy** → Mitigation:
- Warm-up 5 forward pass trước khi đo.
- Average trên 50 passes.

**[Risk] Determinism: `torch.no_grad() + eval()` trên CPU có thể có sai số 1e-7 do floating point
operation order** → Mitigation:
- Dùng `pytest.approx(..., abs=1e-6)`.
- `torch.use_deterministic_algorithms(True)` cho softmax.

**[Risk] Audit 0.5 chỉ đọc code, không test chạy thật** → Mitigation:
- Task 8 (verify cuối) chạy `pytest tests/` toàn bộ + runner x2 diff.
