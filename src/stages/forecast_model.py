"""Forecast Model.

The fourth stage in the faithful-evidence-forecasting pipeline. Given a
single forecast request (one per ``sample_id``) and a list of **selected,
valid** evidence items already filtered by the Temporal Retriever and
extracted by the FinBERT-based Evidence Extractor, it emits a deterministic
stock-movement prediction (``UP`` / ``DOWN`` / ``HOLD``) with a softmax
confidence, evidence counts, pro and counter evidence lists, an
attention-derived rationale, and a structured warnings list.

Version 3 is a **trainable PyTorch** module: the
:class:`AttentionEvidenceAggregator` nn.Module (frozen at inference) is
loaded from the checked-in checkpoint ``models/evidence_aggregator_v1.pt``.
The class is loaded once per ``ForecastModel`` instance and reused across
``predict()`` calls.

Architecture (see ``openspec/changes/forecast-model-attention/design.md``
D1 for the full diagram):

- Per-evidence feature vector (7-dim):
  ``[pos_prob, neg_prob, neutral_prob, support_score,
     dir_up, dir_down, dir_hold]`` — sourced from the FinBERT output of
  the Evidence Extractor.
- ``proj = nn.Linear(7, 32)`` project each evidence into a hidden vector.
- ``attn = nn.Linear(32, 1)`` compute attention score per evidence;
  ``softmax`` over the evidence axis → weighted average pooling → a
  single ``(32,)`` group vector. Empty group → zero vector.
- Concat with two price features
  ``[price_5d_return, volume_change]`` (defaulting to 0.0) →
  ``head = Linear(34, 16) → ReLU → Dropout(0.3) → Linear(16, 3)``.
- ``softmax`` over the 3 logits → ``class_confidences``.
- ``prediction = argmax(class_confidences)`` (deterministic tie-break
  order ``UP > DOWN > HOLD``).

Determinism: every ``_predict_core`` sets
``torch.manual_seed(SEED=42)``, ``model.eval()``, and wraps the forward
pass in ``torch.no_grad()``. Two ``predict()`` calls with identical input
on the same machine + same checkpoint SHALL produce results whose scalar
fields agree within float tolerance ``1e-6``.

The rule-based vote of V1 (``_vote``, ``_compute_confidence``,
``_compute_evidence_strength``, ``_compute_conflict_ratio``,
``_compute_class_confidences``) and the V2 frozen logreg have been
removed entirely — kept only in git history. The check in this file is
the single source of truth for the V3 algorithm.

Scope and contract:

- The model consumes a per-sample request (sample_id / ticker /
  forecast_time / evidence) and emits a structured ``ForecastResult``
  dict. It does NOT re-extract evidence (the Evidence Extractor owns
  that) and does NOT classify evidence into pro / counter / neutral
  groups (the Evidence Selector owns that).
- The model defensively validates evidence timestamps (Temporal
  Retriever normally prevents future-news leakage; this is defense in
  depth).
- The model exposes ``predict_without_evidence`` so the Faithfulness
  Evaluator can compute ``confidence_drop`` after removing one or more
  cited evidence IDs.

See ``openspec/changes/forecast-model-attention/specs/forecasting/spec.md``
for the normative specification.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

from src.stages.retriever import TimeUtils

# torch is imported lazily so a missing checkpoint / torch environment
# surfaces a typed error instead of breaking every ``import`` chain.


SEED: int = 42

DEFAULT_CHECKPOINT_PATH = "models/evidence_aggregator_v1.pt"


class ForecastModelError(ValueError):
    """Raised for unrecoverable input problems (e.g. missing forecast_time,
    missing checkpoint, missing torch)."""


class _AttentionAggregatorBase:
    """Internal base to defer ``torch`` import until instantiation.

    The real subclass is ``AttentionEvidenceAggregator`` which is
    dynamically created via ``_make_attention_class()`` after
    ``import torch.nn as nn`` has run. Keeping the body elsewhere avoids
    importing torch at module-load time (so just ``import``-ing this
    module is cheap).
    """


def _make_attention_class():
    import torch.nn as nn

    class AttentionEvidenceAggregator(nn.Module):
        """``nn.Module`` group-level forecast head.

        See module docstring for the layer-by-layer walk-through.
        """

        EVIDENCE_FEATURE_DIM: int = 7
        PRICE_FEATURE_DIM: int = 2
        HIDDEN_DIM: int = 32

        def __init__(self) -> None:
            super().__init__()
            self.proj = nn.Linear(self.EVIDENCE_FEATURE_DIM, self.HIDDEN_DIM)
            self.attn = nn.Linear(self.HIDDEN_DIM, 1)
            self.head = nn.Sequential(
                nn.Linear(self.HIDDEN_DIM + self.PRICE_FEATURE_DIM, 16),
                nn.ReLU(),
                nn.Dropout(0.3),
                nn.Linear(16, 3),
            )

        def forward(self, evidence_features, price_features):
            import torch
            import torch.nn.functional as F

            if evidence_features.shape[0] == 0:
                group = torch.zeros(self.HIDDEN_DIM, dtype=evidence_features.dtype)
            else:
                h = self.proj(evidence_features)
                scores = self.attn(h)
                weights = torch.softmax(scores, dim=0)
                group = (weights * h).sum(dim=0)
            combined = torch.cat([group, price_features])
            logits = self.head(combined)
            return F.softmax(logits, dim=-1)

    return AttentionEvidenceAggregator


# Build the class lazily on first import so that ``import torch.nn as
# nn`` only runs once.
import torch as _torch  # noqa: E402  (intentional late import)

AttentionEvidenceAggregator = _make_attention_class()
del _make_attention_class


class ForecastModel:
    """Attention-based UP/DOWN/HOLD forecast over selected evidence.

    Loads ``AttentionEvidenceAggregator`` weights from
    ``DEFAULT_CHECKPOINT_PATH`` at construction time. Set the environment
    variable ``FORECAST_CHECKPOINT`` to override the path (used by tests).
    """

    #: Required top-level input fields for a forecast request.
    REQUIRED_INPUT_FIELDS: Tuple[str, ...] = ("sample_id", "ticker", "forecast_time", "evidence")

    #: Valid prediction labels.
    VALID_PREDICTIONS: Tuple[str, ...] = ("UP", "DOWN", "HOLD")

    #: Valid evidence ``expected_direction`` values.
    VALID_DIRECTIONS: Tuple[str, ...] = ("UP", "DOWN", "HOLD")

    #: This class's model version.
    MODEL_VERSION: str = "attention_evidence_v1"

    #: Output evidence-list field names (always present, never ``null``).
    OUTPUT_EVIDENCE_LISTS: Tuple[str, ...] = (
        "pro_evidence",
        "counter_evidence",
        "up_evidence",
        "down_evidence",
        "neutral_evidence",
    )

    #: Warning codes the model can emit.
    WARNING_CODES: Tuple[str, ...] = (
        "TEMPORAL_LEAKAGE_BLOCKED",
        "INVALID_EVIDENCE",
        "DUPLICATE_EVIDENCE_ID",
        "MALFORMED_NEWS_TIME",
        "INPUT_ERROR",
        "MISSING_SENTIMENT_PROBS",
    )

    #: Per-row scalar columns for the CSV emitted by ``predict_batch``.
    CSV_COLUMNS: Tuple[str, ...] = (
        "sample_id",
        "ticker",
        "forecast_time",
        "prediction",
        "confidence",
        "score",
        "positive_count",
        "negative_count",
        "neutral_count",
        "total_evidence",
        "directional_evidence_count",
        "label",
        "model_version",
    )

    #: Default CSV output path.
    CSV_DEFAULT_PATH: str = "outputs/prediction_results.csv"

    #: Default JSON output path (sibling of the CSV).
    JSON_DEFAULT_PATH: str = "outputs/prediction_results.json"

    # -----------------------------------------------------------------
    # Construction / checkpoint loading
    # -----------------------------------------------------------------

    def __init__(self, checkpoint_path: Optional[str] = None) -> None:
        import os
        import torch

        self.checkpoint_path = (
            checkpoint_path
            or os.environ.get("FORECAST_CHECKPOINT")
            or DEFAULT_CHECKPOINT_PATH
        )
        if not Path(self.checkpoint_path).exists():
            raise ForecastModelError(
                f"Attention checkpoint not found at {self.checkpoint_path!r}. "
                "Train one via scripts/train_evidence_aggregator.py or set "
                "FORECAST_CHECKPOINT to an existing path."
            )
        self.model = AttentionEvidenceAggregator()
        state = torch.load(self.checkpoint_path, map_location="cpu")
        self.model.load_state_dict(state)
        self.model.eval()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def predict(self, input_data: Dict[str, Any], *, strict: bool = False) -> Dict[str, Any]:
        return self._predict_core(input_data, exclude_ids=frozenset(), strict=strict)

    def predict_without_evidence(
        self,
        input_data: Dict[str, Any],
        removed_evidence_ids: Optional[Iterable[str]],
        *,
        strict: bool = False,
    ) -> Dict[str, Any]:
        ids: FrozenSet[str] = (
            frozenset() if removed_evidence_ids is None else frozenset(removed_evidence_ids)
        )
        return self._predict_core(input_data, exclude_ids=ids, strict=strict)

    def predict_batch(
        self,
        records: Sequence[Dict[str, Any]],
        *,
        output_csv_path: Optional[str] = CSV_DEFAULT_PATH,
        output_json_path: Optional[str] = JSON_DEFAULT_PATH,
        strict: bool = False,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for record in records:
            try:
                results.append(self.predict(record, strict=strict))
            except ForecastModelError as exc:
                results.append(self._default_error_result(record, str(exc)))
        if output_csv_path is not None:
            self._write_csv(results, Path(output_csv_path))
        if output_json_path is not None:
            self._write_json(results, Path(output_json_path))
        return results

    def compute_accuracy_and_confusion(
        self,
        results: Sequence[Any],
        *,
        label_key: str = "label",
    ) -> Dict[str, Any]:
        """Compute accuracy and a 3×3 confusion matrix.

        Identical contract to V1, kept stable for the dashboard and any
        downstream metric consumer.
        """
        del label_key
        records = self._normalize_records_for_eval(results)
        labels = list(self.VALID_PREDICTIONS)
        n = len(records)
        matrix: List[List[int]] = [[0, 0, 0] for _ in range(3)]
        label_to_idx = {l: i for i, l in enumerate(labels)}
        scored = 0
        correct = 0
        per_class_correct = {l: 0 for l in labels}
        per_class_pred = {l: 0 for l in labels}
        per_class_actual = {l: 0 for l in labels}
        for r in records:
            label = r.get("label")
            prediction = r.get("prediction")
            if label not in label_to_idx or prediction not in label_to_idx:
                continue
            scored += 1
            i_pred = label_to_idx[prediction]
            i_actual = label_to_idx[label]
            matrix[i_pred][i_actual] += 1
            per_class_pred[prediction] += 1
            per_class_actual[label] += 1
            if prediction == label:
                correct += 1
                per_class_correct[label] += 1
        if n > 0 and scored == 0:
            raise ValueError(
                "compute_accuracy_and_confusion: no record carries a usable label"
            )
        accuracy = (correct / scored) if scored > 0 else 0.0
        per_class: Dict[str, Dict[str, float]] = {}
        for l in labels:
            support = per_class_actual[l]
            pred_total = per_class_pred[l]
            precision = per_class_correct[l] / pred_total if pred_total > 0 else 0.0
            recall = per_class_correct[l] / support if support > 0 else 0.0
            f1 = (
                2 * precision * recall / (precision + recall)
                if (precision + recall) > 0
                else 0.0
            )
            per_class[l] = {
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "support": support,
            }
        return {
            "accuracy": accuracy,
            "confusion_matrix": {"labels": labels, "matrix": matrix},
            "per_class": per_class,
            "n_samples": scored,
        }

    # -----------------------------------------------------------------
    # Core prediction (single source of truth for the V3 algorithm)
    # -----------------------------------------------------------------

    def _predict_core(
        self,
        input_data: Dict[str, Any],
        *,
        exclude_ids: FrozenSet[str] = frozenset(),
        strict: bool = False,
    ) -> Dict[str, Any]:
        self._validate_request_envelope(input_data)

        sample_id = input_data["sample_id"]
        ticker = input_data["ticker"]
        forecast_time_str = input_data["forecast_time"]
        forecast_dt = self._parse_forecast_time(forecast_time_str)
        evidence = input_data["evidence"]
        label = input_data.get("label")

        warnings: List[Dict[str, Any]] = []

        if exclude_ids:
            evidence = [e for e in evidence if e.get("evidence_id", "") not in exclude_ids]

        evidence = self._deduplicate(evidence, warnings)
        evidence = self._filter_temporal(evidence, forecast_dt, warnings)

        if strict:
            for item in evidence:
                if item.get("expected_direction") not in self.VALID_DIRECTIONS:
                    raise ForecastModelError(
                        f"strict mode: expected_direction must be one of "
                        f"{self.VALID_DIRECTIONS}, got {item.get('expected_direction')!r}"
                    )

        valid_evidence = [e for e in evidence if e.get("expected_direction") in self.VALID_DIRECTIONS]
        positive_count = sum(1 for e in valid_evidence if e.get("expected_direction") == "UP")
        negative_count = sum(1 for e in valid_evidence if e.get("expected_direction") == "DOWN")
        neutral_count = sum(1 for e in valid_evidence if e.get("expected_direction") == "HOLD")
        directional_evidence_count = positive_count + negative_count
        total_evidence = len(evidence)

        # ---- Attention forward pass ---------------------------------
        import torch

        torch.manual_seed(SEED)
        with torch.no_grad():
            evidence_features = self._build_evidence_features(valid_evidence, warnings)
            price_features = self._build_price_features(input_data)
            class_probs_tensor = self.model(evidence_features, price_features)
        class_confidences: Dict[str, float] = {
            c: float(class_probs_tensor[i]) for i, c in enumerate(self.VALID_PREDICTIONS)
        }
        prediction, confidence = self._argmax_with_tiebreak(class_confidences)

        # ---- Evidence lists & rationale ----------------------------
        partitioned = self._partition_evidence(valid_evidence, warnings)
        up_evidence = partitioned["up_evidence"]
        down_evidence = partitioned["down_evidence"]
        neutral_evidence = partitioned["neutral_evidence"]
        pro_evidence, counter_evidence = self._build_pro_and_counter(
            prediction, up_evidence, down_evidence
        )
        rationale = self._build_rationale(valid_evidence, warnings)

        result: Dict[str, Any] = {
            "sample_id": sample_id,
            "ticker": ticker,
            "forecast_time": forecast_time_str,
            "prediction": prediction,
            "confidence": confidence,
            "class_confidences": class_confidences,
            "score": 0,
            "positive_count": positive_count,
            "negative_count": negative_count,
            "neutral_count": neutral_count,
            "total_evidence": total_evidence,
            "directional_evidence_count": directional_evidence_count,
            "pro_evidence": pro_evidence,
            "counter_evidence": counter_evidence,
            "up_evidence": up_evidence,
            "down_evidence": down_evidence,
            "neutral_evidence": neutral_evidence,
            "rationale": rationale,
            "warnings": warnings,
            "model_version": self.MODEL_VERSION,
        }
        if label is not None:
            result["label"] = label
        return result

    # -----------------------------------------------------------------
    # Feature builders (called inside ``no_grad``)
    # -----------------------------------------------------------------

    def _build_evidence_features(
        self,
        evidence_items: Sequence[Dict[str, Any]],
        warnings_out: List[Dict[str, Any]],
    ):
        """Return a ``torch.Tensor`` of shape ``(N, 7)`` per design D4.

        Items missing ``sentiment_probs`` are skipped with a
        ``MISSING_SENTIMENT_PROBS`` warning (defensive: a stale envelope
        from V1 shouldn't crash the pipeline).
        """
        import torch

        rows: List[List[float]] = []
        for item in evidence_items:
            sp = item.get("sentiment_probs")
            if not isinstance(sp, dict):
                warnings_out.append(
                    {
                        "code": "MISSING_SENTIMENT_PROBS",
                        "evidence_id": item.get("evidence_id", ""),
                        "message": (
                            "evidence item has no sentiment_probs; "
                            "skipped from feature vector"
                        ),
                    }
                )
                continue
            direction = item.get("expected_direction", "HOLD")
            rows.append(
                [
                    float(sp.get("positive", 0.0)),
                    float(sp.get("negative", 0.0)),
                    float(sp.get("neutral", 0.0)),
                    float(item.get("support_score", 0.0) or 0.0),
                    1.0 if direction == "UP" else 0.0,
                    1.0 if direction == "DOWN" else 0.0,
                    1.0 if direction == "HOLD" else 0.0,
                ]
            )
        if not rows:
            return torch.zeros((0, 7), dtype=torch.float32)
        return torch.tensor(rows, dtype=torch.float32)

    def _build_price_features(self, input_data: Dict[str, Any]):
        import torch

        return torch.tensor(
            [
                float(input_data.get("price_5d_return", 0.0) or 0.0),
                float(input_data.get("volume_change", 0.0) or 0.0),
            ],
            dtype=torch.float32,
        )

    @staticmethod
    def _argmax_with_tiebreak(probs: Dict[str, float]) -> Tuple[str, float]:
        order = ("UP", "DOWN", "HOLD")
        best_label = order[0]
        best_val = -1.0
        for label in order:
            v = float(probs.get(label, 0.0))
            if v > best_val:
                best_val = v
                best_label = label
        return best_label, best_val

    # -----------------------------------------------------------------
    # Datetime parsing helpers (reuse TimeUtils for UTC)
    # -----------------------------------------------------------------

    @staticmethod
    def _parse_news_time(value: Any) -> Optional[datetime]:
        if value is None or not isinstance(value, str) or not value.strip():
            return None
        try:
            return TimeUtils.parse_utc(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _is_future(news_dt: Optional[datetime], forecast_dt: datetime) -> bool:
        if news_dt is None:
            return False
        return news_dt > forecast_dt

    # -----------------------------------------------------------------
    # Pro / counter / raw evidence partition + rationale
    # -----------------------------------------------------------------

    @staticmethod
    def _copy_evidence(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "evidence_id": item.get("evidence_id", ""),
            "news_id": item.get("news_id", ""),
            "news_time": item.get("news_time", ""),
            "evidence_text": item.get("evidence_text", ""),
            "polarity": item.get("polarity", ""),
            "expected_direction": item.get("expected_direction", ""),
            "support_score": float(item.get("support_score", 0.0) or 0.0),
            "sentiment_probs": item.get("sentiment_probs", {}),
        }

    @staticmethod
    def _partition_evidence(
        evidence_items: Sequence[Dict[str, Any]],
        warnings_out: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        up: List[Dict[str, Any]] = []
        down: List[Dict[str, Any]] = []
        neutral: List[Dict[str, Any]] = []
        for item in evidence_items:
            direction = item.get("expected_direction")
            evidence_id = item.get("evidence_id", "")
            if direction == "UP":
                up.append(ForecastModel._copy_evidence(item))
            elif direction == "DOWN":
                down.append(ForecastModel._copy_evidence(item))
            elif direction == "HOLD":
                neutral.append(ForecastModel._copy_evidence(item))
            else:
                warnings_out.append(
                    {
                        "code": "INVALID_EVIDENCE",
                        "evidence_id": evidence_id,
                        "message": (
                            f"Evidence {evidence_id!r} has missing or invalid "
                            f"expected_direction={direction!r}; ignored."
                        ),
                    }
                )
        up.sort(key=lambda e: e["evidence_id"])
        down.sort(key=lambda e: e["evidence_id"])
        neutral.sort(key=lambda e: e["evidence_id"])
        return {"up_evidence": up, "down_evidence": down, "neutral_evidence": neutral}

    @staticmethod
    def _build_pro_and_counter(
        prediction: str,
        up_evidence: List[Dict[str, Any]],
        down_evidence: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        if prediction == "UP":
            return list(up_evidence), list(down_evidence)
        if prediction == "DOWN":
            return list(down_evidence), list(up_evidence)
        return [], []

    @staticmethod
    def _build_rationale(
        evidence_items: Sequence[Dict[str, Any]],
        warnings_out: List[Dict[str, Any]],
    ) -> str:
        if not evidence_items:
            return "Attention model: no evidence items"
        top = sorted(
            evidence_items,
            key=lambda e: (
                -float((e.get("sentiment_probs") or {}).get(
                    {"UP": "positive", "DOWN": "negative", "HOLD": "neutral"}.get(
                        e.get("expected_direction", "HOLD"), "neutral"
                    ),
                    0.0,
                )),
                e.get("evidence_id", ""),
            ),
        )[:3]
        if not top:
            return "Attention model: no usable evidence"
        eids = ", ".join(e.get("evidence_id", "") for e in top)
        head_sp = (top[0].get("sentiment_probs") or {})
        direction = top[0].get("expected_direction", "HOLD")
        head_score = float(
            head_sp.get(
                {"UP": "positive", "DOWN": "negative", "HOLD": "neutral"}.get(direction, "neutral"),
                0.0,
            )
        )
        return f"Attention model: top evidence {eids}, attention weight={head_score:.4f}"

    # -----------------------------------------------------------------
    # Defensive helpers (deduplication and temporal filtering)
    # -----------------------------------------------------------------

    @staticmethod
    def _deduplicate(
        evidence_items: Sequence[Dict[str, Any]],
        warnings_out: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        seen: Dict[str, Dict[str, Any]] = {}
        output: List[Dict[str, Any]] = []
        for item in evidence_items:
            evidence_id = item.get("evidence_id", "")
            if evidence_id in seen:
                warnings_out.append(
                    {
                        "code": "DUPLICATE_EVIDENCE_ID",
                        "evidence_id": evidence_id,
                        "message": (
                            f"Evidence {evidence_id!r} appeared more than once; "
                            "keeping the first occurrence."
                        ),
                    }
                )
                continue
            seen[evidence_id] = item
            output.append(item)
        return output

    def _filter_temporal(
        self,
        evidence_items: Sequence[Dict[str, Any]],
        forecast_dt: datetime,
        warnings_out: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        output: List[Dict[str, Any]] = []
        for item in evidence_items:
            evidence_id = item.get("evidence_id", "")
            raw_news_time = item.get("news_time")
            parsed = self._parse_news_time(raw_news_time)
            if parsed is None:
                warnings_out.append(
                    {
                        "code": "MALFORMED_NEWS_TIME",
                        "evidence_id": evidence_id,
                        "message": (
                            f"Evidence {evidence_id!r} has missing or unparseable "
                            f"news_time={raw_news_time!r}; treated as not-future."
                        ),
                    }
                )
                output.append(item)
                continue
            if self._is_future(parsed, forecast_dt):
                warnings_out.append(
                    {
                        "code": "TEMPORAL_LEAKAGE_BLOCKED",
                        "evidence_id": evidence_id,
                        "news_time": raw_news_time,
                        "forecast_time": forecast_dt.isoformat(),
                        "message": (
                            f"Evidence {evidence_id!r} has news_time strictly after "
                            "forecast_time; excluded from scoring."
                        ),
                    }
                )
                continue
            output.append(item)
        return output

    # -----------------------------------------------------------------
    # Validation helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _validate_request_envelope(input_data: Any) -> None:
        if not isinstance(input_data, dict):
            raise ForecastModelError(
                f"input must be a dict, got {type(input_data).__name__}"
            )
        for field_name in ("sample_id", "ticker", "forecast_time"):
            value = input_data.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise ForecastModelError(
                    f"required field {field_name!r} is missing or not a non-empty string"
                )
        evidence = input_data.get("evidence")
        if evidence is None:
            raise ForecastModelError("required field 'evidence' is missing")
        if not isinstance(evidence, list):
            raise ForecastModelError(
                f"'evidence' must be a list, got {type(evidence).__name__}"
            )

    @staticmethod
    def _parse_forecast_time(value: str) -> datetime:
        try:
            return TimeUtils.parse_utc(value)
        except (ValueError, TypeError) as exc:
            raise ForecastModelError(
                f"forecast_time is not a parseable timestamp: {value!r}"
            ) from exc

    # -----------------------------------------------------------------
    # Batch error default / IO helpers
    # -----------------------------------------------------------------

    def _default_error_result(self, record: Any, message: str) -> Dict[str, Any]:
        sample_id = ""
        ticker = ""
        forecast_time = ""
        label = None
        if isinstance(record, dict):
            sample_id = record.get("sample_id", "") if isinstance(record.get("sample_id"), str) else ""
            ticker = record.get("ticker", "") if isinstance(record.get("ticker"), str) else ""
            forecast_time = (
                record.get("forecast_time", "")
                if isinstance(record.get("forecast_time"), str)
                else ""
            )
            if "label" in record:
                label = record.get("label")
        result: Dict[str, Any] = {
            "sample_id": sample_id,
            "ticker": ticker,
            "forecast_time": forecast_time,
            "prediction": "HOLD",
            "confidence": 0.5,
            "class_confidences": {"UP": 0.25, "DOWN": 0.25, "HOLD": 0.5},
            "score": 0,
            "positive_count": 0,
            "negative_count": 0,
            "neutral_count": 0,
            "total_evidence": 0,
            "directional_evidence_count": 0,
            "pro_evidence": [],
            "counter_evidence": [],
            "up_evidence": [],
            "down_evidence": [],
            "neutral_evidence": [],
            "rationale": "Attention model: input error",
            "warnings": [
                {
                    "code": "INPUT_ERROR",
                    "evidence_id": "",
                    "message": message,
                }
            ],
            "model_version": self.MODEL_VERSION,
        }
        if label is not None:
            result["label"] = label
        return result

    def _write_csv(self, results: Sequence[Dict[str, Any]], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.CSV_COLUMNS))
            writer.writeheader()
            for r in results:
                writer.writerow({col: r.get(col, "") for col in self.CSV_COLUMNS})

    @staticmethod
    def _write_json(results: Sequence[Dict[str, Any]], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(list(results), handle, ensure_ascii=False, indent=2, sort_keys=False)

    @staticmethod
    def _normalize_records_for_eval(results: Sequence[Any]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for entry in results:
            if isinstance(entry, tuple) and len(entry) == 2:
                input_record, result = entry
                if isinstance(input_record, dict) and isinstance(result, dict):
                    if "label" in input_record and "label" not in result:
                        result = {**result, "label": input_record["label"]}
                    normalized.append(result)
                    continue
            if isinstance(entry, dict):
                normalized.append(entry)
        return normalized


# ---------------------------------------------------------------------------
# Envelope stage adapter (see openspec/changes/interactive-stage-cli)
# ---------------------------------------------------------------------------

STAGE_NAME = "forecast_model"


def build_forecast_request(sample: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sample_id": sample["sample_id"],
        "ticker": sample["ticker"],
        "forecast_time": sample["forecast_time"],
        "label": sample.get("label", ""),
        "price_5d_return": sample.get("price_5d_return", 0.0),
        "volume_change": sample.get("volume_change", 0.0),
        "evidence": sample["evidence"],
    }


def process(envelope: Dict[str, Any]) -> Dict[str, Any]:
    model = ForecastModel()
    for sample in envelope["samples"]:
        sample["forecast"] = model.predict(build_forecast_request(sample))
    envelope["stage"] = STAGE_NAME
    return envelope


def main(argv: Optional[List[str]] = None) -> int:
    from src.core.stage_io import run_stage_cli

    return run_stage_cli(
        STAGE_NAME,
        "Predict UP/DOWN/HOLD for each sample using the Attention aggregator.",
        process,
        argv,
    )


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main())


__all__ = [
    "AttentionEvidenceAggregator",
    "ForecastModel",
    "ForecastModelError",
    "STAGE_NAME",
    "build_forecast_request",
    "process",
    "main",
]
