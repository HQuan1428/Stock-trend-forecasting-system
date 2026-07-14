"""FinBERT sentiment scorer.

Originally added for the Phase C2 bonus (``phase-c2-finbert-model``) as an
isolated, opt-in dependency. Since ``finbert-native-pipeline``, this
module is a core dependency: ``src/evidence_extractor.py`` (reachable from
``src/pipeline.py``) imports it directly, so ``torch``/``transformers``
are now required to run the main pipeline — see ``requirements.txt``. The
historical, now-archived group-level comparison model
(``experiments/finbert_lr_v2_baseline/src/finbert_forecast_model.py``)
also depends on this module.

This module has exactly one job: text -> sentiment probabilities. It does
NOT know about evidence IDs, pro/counter classification, or predictions —
those remain the responsibility of ``src/evidence_extractor.py`` and
``src/evidence_selector.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

MODEL_NAME = "ProsusAI/finbert"

REPO_ROOT = Path(__file__).resolve().parent.parent


class FinbertLoadError(RuntimeError):
    """Raised when the FinBERT tokenizer/model cannot be loaded.

    Wraps the underlying ``transformers``/``huggingface_hub`` exception
    (e.g. no network on first run, no local Hugging Face cache yet) with
    an actionable message instead of letting a raw library traceback
    surface from inside a pipeline run.
    """


class FinbertSentimentScorer:
    """Lazy-loaded, singleton-per-instance wrapper around ProsusAI/finbert.

    The model (~400MB) and tokenizer are only loaded on first ``score()``
    call, not at import time or construction time, so importing this module
    is cheap even when the model is never used.
    """

    def __init__(self, model_name: str = MODEL_NAME):
        self._model_name = model_name
        self._tokenizer = None
        self._model = None
        self._id2label: Optional[Dict[int, str]] = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        # Imported lazily so merely constructing (or importing this module)
        # never requires torch/transformers to be installed.
        from dotenv import load_dotenv
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        # Optional HF_TOKEN from .env raises the anonymous Hugging Face Hub
        # rate limit on first download; never overrides a real `export`.
        load_dotenv(REPO_ROOT / ".env")

        try:
            self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)
            self._model = AutoModelForSequenceClassification.from_pretrained(self._model_name)
        except Exception as exc:
            self._tokenizer = None
            self._model = None
            raise FinbertLoadError(
                f"Could not load FinBERT model {self._model_name!r}. This "
                "usually means there is no network access and no local "
                "Hugging Face cache yet (~/.cache/huggingface) — the "
                "weights (~400MB) must be downloaded once with network "
                f"access before the pipeline can run offline. Original error: {exc}"
            ) from exc
        self._model.eval()
        # Read the label mapping from the checkpoint itself rather than
        # hard-coding {0: positive, 1: negative, 2: neutral} — if a future
        # checkpoint swap changes the ordering, this stays correct.
        self._id2label = {int(k): v for k, v in self._model.config.id2label.items()}

    def score(self, texts: List[str]) -> List[Dict[str, float]]:
        """Return one ``{"positive": p, "negative": p, "neutral": p}`` dict
        per input text, in input order. Batched for speed.
        """
        if not texts:
            return []
        self._ensure_loaded()
        import torch

        with torch.no_grad():
            inputs = self._tokenizer(
                texts, return_tensors="pt", padding=True, truncation=True, max_length=64
            )
            logits = self._model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)

        results = []
        for row in probs:
            labeled = {self._id2label[i]: float(row[i]) for i in range(len(row))}
            results.append(
                {
                    "positive": labeled.get("positive", 0.0),
                    "negative": labeled.get("negative", 0.0),
                    "neutral": labeled.get("neutral", 0.0),
                }
            )
        return results

    def score_one(self, text: str) -> Dict[str, float]:
        return self.score([text])[0]


__all__ = ["FinbertSentimentScorer", "FinbertLoadError", "MODEL_NAME"]
