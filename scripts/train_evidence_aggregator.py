"""Train the Attention Evidence Aggregator (V3).

One-shot offline trainer. The pipeline does NOT call this — it loads the
checkpoint at ``models/evidence_aggregator_v1.pt`` written by this script.
Run:

    python3 scripts/train_evidence_aggregator.py --device cpu --epochs 2      # dry-run / smoke test
    python3 scripts/train_evidence_aggregator.py --device cuda --epochs 50     # Colab T4

The script:
1. Builds per-sample (evidence_features, price_features, label) tuples by
   chaining ``ingest`` → ``retriever`` → ``evidence_extractor`` on the
   given CSV (default ``data/real_dataset.csv``).
2. Splits 70 / 15 / 15 by group with seed 42.
3. Trains ``AttentionEvidenceAggregator`` with ``Adam`` and
   ``CrossEntropyLoss``. Early-stops on validation loss (patience=5).
4. Evaluates on the held-out test split (accuracy, macro-F1, 3×3 confusion).
5. (CUDA only) Benchmarks eager vs ``torch.compile`` average over 50
   forward passes.
6. Saves the best validation checkpoint to
   ``models/evidence_aggregator_v1.pt`` (override via
   ``--checkpoint-path``).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import torch
from torch import nn

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.stages.evidence_extractor import process as extractor_process  # noqa: E402
from src.stages.forecast_model import (  # noqa: E402
    AttentionEvidenceAggregator,
    DEFAULT_CHECKPOINT_PATH,
)
from src.stages.ingest import process_csv  # noqa: E402
from src.stages.retriever import process as retriever_process  # noqa: E402

DEFAULT_CSV = REPO_ROOT / "data" / "real_dataset.csv"
LABEL_TO_INDEX: Dict[str, int] = {"UP": 0, "DOWN": 1, "HOLD": 2}


@dataclass
class Sample:
    """One training record."""

    sample_id: str
    evidence_features: torch.Tensor  # shape (N, 7); (0, 7) if N == 0
    price_features: torch.Tensor  # shape (2,)
    label_index: int


@dataclass
class Split:
    train: List[Sample]
    val: List[Sample]
    test: List[Sample]


# ---------------------------------------------------------------------------
# Step 1: Build training data
# ---------------------------------------------------------------------------


def build_feature_for_evidence_item(item: Dict[str, Any]) -> List[float]:
    sp = item.get("sentiment_probs") or {}
    direction = item.get("expected_direction", "HOLD")
    return [
        float(sp.get("positive", 0.0)),
        float(sp.get("negative", 0.0)),
        float(sp.get("neutral", 0.0)),
        float(item.get("support_score", 0.0) or 0.0),
        1.0 if direction == "UP" else 0.0,
        1.0 if direction == "DOWN" else 0.0,
        1.0 if direction == "HOLD" else 0.0,
    ]


def build_training_data(
    csv_path: Path,
    *,
    skip_invalid_labels: bool = True,
) -> List[Sample]:
    """Run the pipeline up to evidence_extractor, return one Sample per group."""
    env = process_csv(str(csv_path))
    env = retriever_process(env)
    env = extractor_process(env)

    samples: List[Sample] = []
    for s in env["samples"]:
        label = s.get("label", "")
        if skip_invalid_labels and label not in LABEL_TO_INDEX:
            continue
        evidence_items = s.get("evidence", [])
        rows: List[List[float]] = []
        for item in evidence_items:
            if not isinstance(item, dict):
                continue
            if "sentiment_probs" not in item:
                continue
            rows.append(build_feature_for_evidence_item(item))
        evidence_tensor = (
            torch.tensor(rows, dtype=torch.float32)
            if rows
            else torch.zeros((0, 7), dtype=torch.float32)
        )
        price_tensor = torch.tensor(
            [
                float(s.get("price_5d_return", 0.0) or 0.0),
                float(s.get("volume_change", 0.0) or 0.0),
            ],
            dtype=torch.float32,
        )
        samples.append(
            Sample(
                sample_id=str(s.get("sample_id", "")),
                evidence_features=evidence_tensor,
                price_features=price_tensor,
                label_index=LABEL_TO_INDEX[label],
            )
        )
    return samples


# ---------------------------------------------------------------------------
# Step 2: 70 / 15 / 15 group-level split (seed 42)
# ---------------------------------------------------------------------------


def split_samples(samples: List[Sample], *, seed: int = 42) -> Split:
    rng = random.Random(seed)
    ids = list(range(len(samples)))
    rng.shuffle(ids)
    n_total = len(ids)
    n_train = int(n_total * 0.70)
    n_val = int(n_total * 0.15)
    train_ids = ids[:n_train]
    val_ids = ids[n_train : n_train + n_val]
    test_ids = ids[n_train + n_val :]
    return Split(
        train=[samples[i] for i in train_ids],
        val=[samples[i] for i in val_ids],
        test=[samples[i] for i in test_ids],
    )


# ---------------------------------------------------------------------------
# Step 3: Training loop
# ---------------------------------------------------------------------------


def collate(batch: Sequence[Sample]) -> Tuple[List[torch.Tensor], torch.Tensor]:
    """Stack a list of variable-shape Samples into a list-of-tensors and a label tensor.

    Padding is not necessary because the model handles variable-N via
    batch=1-style forward (one group per call).
    """
    evidences = [s.evidence_features for s in batch]
    prices = torch.stack([s.price_features for s in batch])
    labels = torch.tensor([s.label_index for s in batch], dtype=torch.long)
    return evidences, labels


def train_model(
    data: Split,
    *,
    device: str,
    epochs: int,
    lr: float,
    batch_size: int,
    patience: int = 5,
    seed: int = 42,
) -> Tuple[AttentionEvidenceAggregator, List[Dict[str, Any]]]:
    """Run the training loop. Returns the best-validation model + history."""
    torch.manual_seed(seed)
    model = AttentionEvidenceAggregator().to(device)
    model.train()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.CrossEntropyLoss()
    history: List[Dict[str, Any]] = []
    best_val_loss = float("inf")
    best_state: Dict[str, torch.Tensor] = {
        k: v.detach().clone() for k, v in model.state_dict().items()
    }
    no_improve = 0

    train_data = data.train
    rng = random.Random(seed)

    for epoch in range(1, epochs + 1):
        rng.shuffle(train_data)
        train_loss_sum = 0.0
        train_n = 0
        for start in range(0, len(train_data), batch_size):
            chunk = train_data[start : start + batch_size]
            evidences, labels = collate(chunk)
            labels = labels.to(device)
            optimizer.zero_grad()
            batch_loss = 0.0
            for i, ef in enumerate(evidences):
                pf = (
                    torch.tensor(
                        chunk[i].price_features.tolist(), dtype=torch.float32
                    )
                    if device == "cpu"
                    else chunk[i].price_features.to(device)
                )
                ef_t = ef.to(device)
                probs = model(ef_t, pf)
                batch_loss = batch_loss + loss_fn(probs.unsqueeze(0), labels[i].unsqueeze(0))
            batch_loss = batch_loss / len(chunk)
            batch_loss.backward()
            optimizer.step()
            train_loss_sum += float(batch_loss.item()) * len(chunk)
            train_n += len(chunk)
        train_loss = train_loss_sum / max(train_n, 1)

        val_loss = _evaluate_loss(model, data.val, loss_fn, device=device)
        history.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})
        print(
            f"[train] epoch={epoch}/{epochs} train_loss={train_loss:.4f} "
            f"val_loss={val_loss:.4f}"
        )
        if val_loss < best_val_loss - 1e-6:
            best_val_loss = val_loss
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            no_improve = 0
        else:
            no_improve += 1
            if no_improve >= patience:
                print(f"[train] early-stop at epoch={epoch} (patience={patience})")
                break

    model.load_state_dict(best_state)
    model.eval()
    return model, history


def _evaluate_loss(
    model: AttentionEvidenceAggregator,
    dataset: Sequence[Sample],
    loss_fn: nn.CrossEntropyLoss,
    *,
    device: str,
) -> float:
    model.eval()
    total = 0.0
    n = 0
    with torch.no_grad():
        for s in dataset:
            ef = s.evidence_features.to(device)
            pf = s.price_features.to(device)
            label = torch.tensor([s.label_index], dtype=torch.long, device=device)
            probs = model(ef, pf)
            total += float(loss_fn(probs.unsqueeze(0), label).item())
            n += 1
    model.train()
    return total / max(n, 1)


# ---------------------------------------------------------------------------
# Step 4: Evaluation (accuracy, macro-F1, confusion)
# ---------------------------------------------------------------------------


def evaluate_model(
    model: AttentionEvidenceAggregator,
    dataset: Sequence[Sample],
    *,
    device: str,
) -> Dict[str, Any]:
    model.eval()
    preds: List[int] = []
    actuals: List[int] = []
    with torch.no_grad():
        for s in dataset:
            ef = s.evidence_features.to(device)
            pf = s.price_features.to(device)
            probs = model(ef, pf)
            preds.append(int(probs.argmax(dim=-1).item()))
            actuals.append(s.label_index)
    n = len(preds)
    if n == 0:
        return {
            "accuracy": 0.0,
            "macro_f1": 0.0,
            "confusion": [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
            "n_samples": 0,
        }
    correct = sum(1 for p, a in zip(preds, actuals) if p == a)
    accuracy = correct / n
    confusion = [[0, 0, 0] for _ in range(3)]
    for p, a in zip(preds, actuals):
        confusion[p][a] += 1
    f1s = []
    for c in range(3):
        tp = confusion[c][c]
        fp = sum(confusion[c][j] for j in range(3) if j != c)
        fn = sum(confusion[i][c] for i in range(3) if i != c)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        f1s.append(f1)
    macro_f1 = sum(f1s) / 3.0
    return {
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "confusion": confusion,
        "n_samples": n,
    }


# ---------------------------------------------------------------------------
# Step 5: Benchmark eager vs torch.compile (CUDA only)
# ---------------------------------------------------------------------------


def benchmark_compile(
    model: AttentionEvidenceAggregator,
    dataset: Sequence[Sample],
    *,
    device: str,
    warm_up: int = 5,
    measure_passes: int = 50,
) -> Dict[str, Any]:
    if device != "cuda" or not torch.cuda.is_available():
        return {"eager_ms": None, "compiled_ms": None, "speedup": None, "skipped": True}
    model = model.to(device)
    model.eval()
    sample = dataset[0] if len(dataset) > 0 else None
    if sample is None:
        return {"eager_ms": None, "compiled_ms": None, "speedup": None, "skipped": True}
    ef = sample.evidence_features.to(device)
    pf = sample.price_features.to(device)

    def _time(fn) -> float:
        if device == "cuda":
            torch.cuda.synchronize()
        start = time.perf_counter()
        for _ in range(measure_passes):
            with torch.no_grad():
                fn()
        if device == "cuda":
            torch.cuda.synchronize()
        return (time.perf_counter() - start) * 1000.0 / measure_passes

    eager_fn = lambda: model(ef, pf)
    for _ in range(warm_up):
        with torch.no_grad():
            eager_fn()
    eager_ms = _time(eager_fn)

    compiled = torch.compile(model, backend="inductor")
    compiled_fn = lambda: compiled(ef, pf)
    for _ in range(warm_up):
        with torch.no_grad():
            compiled_fn()
    compiled_ms = _time(compiled_fn)

    return {
        "eager_ms": eager_ms,
        "compiled_ms": compiled_ms,
        "speedup": eager_ms / compiled_ms if compiled_ms > 0 else None,
        "skipped": False,
    }


# ---------------------------------------------------------------------------
# Step 6: Main
# ---------------------------------------------------------------------------


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scripts/train_evidence_aggregator.py",
        description="Train the Attention Evidence Aggregator (Forecast Model V3).",
    )
    parser.add_argument(
        "--csv",
        default=str(DEFAULT_CSV),
        help="Path to the input CSV (default: data/real_dataset.csv).",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        choices=("cpu", "cuda"),
        help="Torch device (default: cpu).",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=2,
        help="Number of training epochs (default: 2 — quick dry-run).",
    )
    parser.add_argument(
        "--lr",
        type=float,
        default=1e-3,
        help="Adam learning rate (default: 1e-3).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Training batch size (default: 8).",
    )
    parser.add_argument(
        "--patience",
        type=int,
        default=5,
        help="Early-stopping patience on val loss (default: 5).",
    )
    parser.add_argument(
        "--checkpoint-path",
        default=DEFAULT_CHECKPOINT_PATH,
        help="Where to write the best checkpoint.",
    )
    parser.add_argument(
        "--skip-benchmark",
        action="store_true",
        help="Skip the torch.compile / eager benchmark.",
    )
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] = ()) -> int:
    args = parse_args(argv)
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"input CSV not found: {csv_path}", file=sys.stderr)
        return 2

    print(f"[train] build_training_data({csv_path})")
    samples = build_training_data(csv_path)
    print(f"[train] total samples: {len(samples)}")
    if not samples:
        print("[train] no usable samples (all labels invalid). aborting.", file=sys.stderr)
        return 2
    data = split_samples(samples)
    print(
        f"[train] split: train={len(data.train)} val={len(data.val)} test={len(data.test)}"
    )

    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        print("[train] CUDA requested but not available; falling back to CPU.")
        device = "cpu"

    print(f"[train] device={device} epochs={args.epochs} lr={args.lr}")
    model, history = train_model(
        data,
        device=device,
        epochs=args.epochs,
        lr=args.lr,
        batch_size=args.batch_size,
        patience=args.patience,
    )

    metrics = evaluate_model(model, data.test, device=device)
    print(
        f"[train] test: accuracy={metrics['accuracy']:.4f} "
        f"macro_f1={metrics['macro_f1']:.4f} n={metrics['n_samples']}"
    )
    print(f"[train] confusion matrix (rows=pred, cols=actual): {metrics['confusion']}")

    bench = {"skipped": True}
    if not args.skip_benchmark and device == "cuda":
        bench = benchmark_compile(model, data.test, device=device)
        if not bench.get("skipped"):
            print(
                f"[bench] eager={bench['eager_ms']:.3f}ms "
                f"compiled={bench['compiled_ms']:.3f}ms "
                f"speedup={bench['speedup']:.2f}x"
            )

    checkpoint_path = Path(args.checkpoint_path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), checkpoint_path)
    print(f"[train] saved checkpoint: {checkpoint_path}")

    summary = {
        "epochs": len(history),
        "best_train_loss": min(h["train_loss"] for h in history),
        "best_val_loss": min(h["val_loss"] for h in history),
        "test_metrics": metrics,
        "benchmark": bench,
        "checkpoint_path": str(checkpoint_path),
    }
    print("[train] summary:")
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
