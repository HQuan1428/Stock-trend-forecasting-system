"""Sufficiency + Counterfactual Perturbation Evaluator (B1).

Given the original forecast request and result, this class answers two
questions:

1. **Sufficiency**: If we run the forecast with *only* the cited evidence,
   does it still produce the same direction and confidence?
   ``sufficiency_score = min(suff_confidence / original_confidence, 1.0)``

2. **Counterfactual Perturbation**: If we replace each cited evidence item
   with a neutral placeholder (``expected_direction=HOLD``), how much does
   the confidence drop?
   ``counterfactual_delta = original_confidence - counterfactual_confidence``

Both use :class:`src.forecast_model.ForecastModel` — no ML, LLM, or
external API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

from src.forecast_model import ForecastModel


class SufficiencyEvaluator:
    """Compute sufficiency and counterfactual metrics for a single forecast."""

    def __init__(self) -> None:
        self._forecast_model = ForecastModel()

    def evaluate(
        self,
        original_input: Dict[str, Any],
        original_result: Dict[str, Any],
        cited_evidence_ids: Set[str],
    ) -> Dict[str, Any]:
        """Run sufficiency and counterfactual evaluation.

        Args:
            original_input: The forecast request dict (sample_id, ticker,
                forecast_time, evidence, ...) passed to the original
                ``predict()`` call.
            original_result: The ``ForecastResult`` dict returned by that
                ``predict()`` call.
            cited_evidence_ids: Set of ``news_id`` values that the Evidence
                Selector classified as cited (pro + counter).

        Returns:
            Dict with five fields:
            - ``sufficiency_confidence`` (float)
            - ``sufficiency_score`` (float, [0.0, 1.0])
            - ``prediction_on_only_cited`` (str: UP/DOWN/HOLD)
            - ``counterfactual_confidence`` (float)
            - ``counterfactual_delta`` (float, signed)
        """
        original_confidence = float(original_result.get("confidence", 0.5))
        evidence = list(original_input.get("evidence", []))

        # --- Sufficiency: run predict with only cited evidence ----------
        cited_only = self._only_cited_evidence(evidence, cited_evidence_ids)
        suff_input = {**original_input, "evidence": cited_only}
        suff_result = self._forecast_model.predict(suff_input)
        sufficiency_confidence = float(suff_result["confidence"])
        prediction_on_only_cited: str = str(suff_result["prediction"])
        # When no evidence is cited there is nothing to assess — score is 0.
        if not cited_evidence_ids:
            sufficiency_score = 0.0
        else:
            sufficiency_score = self._compute_sufficiency_score(
                sufficiency_confidence, original_confidence
            )

        # --- Counterfactual: replace cited evidence with neutral ---------
        perturbed = self._perturb_to_neutral(evidence, cited_evidence_ids)
        cf_input = {**original_input, "evidence": perturbed}
        cf_result = self._forecast_model.predict(cf_input)
        counterfactual_confidence = float(cf_result["confidence"])
        counterfactual_delta = original_confidence - counterfactual_confidence

        return {
            "sufficiency_confidence": sufficiency_confidence,
            "sufficiency_score": sufficiency_score,
            "prediction_on_only_cited": prediction_on_only_cited,
            "counterfactual_confidence": counterfactual_confidence,
            "counterfactual_delta": counterfactual_delta,
        }

    # -----------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _only_cited_evidence(
        evidence: List[Dict[str, Any]],
        cited_ids: Set[str],
    ) -> List[Dict[str, Any]]:
        """Return only the evidence items whose ``news_id`` is in ``cited_ids``."""
        return [ev for ev in evidence if ev.get("news_id") in cited_ids]

    @staticmethod
    def _perturb_to_neutral(
        evidence: List[Dict[str, Any]],
        cited_ids: Set[str],
    ) -> List[Dict[str, Any]]:
        """Return evidence with cited items replaced by neutral placeholders.

        Uncited items are kept as-is. Each cited item is replaced with a
        placeholder carrying ``expected_direction=HOLD`` and
        ``support_score=0.5`` so it contributes zero directional votes to
        the forecast.
        """
        result: List[Dict[str, Any]] = []
        for ev in evidence:
            news_id = ev.get("news_id", "")
            if news_id in cited_ids:
                result.append(
                    {
                        "evidence_id": f"{news_id}_NEUTRAL",
                        "news_id": news_id,
                        "news_time": ev.get("news_time", ""),
                        "evidence_text": "",
                        "polarity": "neutral",
                        "expected_direction": "HOLD",
                        "support_score": 0.5,
                    }
                )
            else:
                result.append(ev)
        return result

    @staticmethod
    def _compute_sufficiency_score(
        sufficiency_confidence: float,
        original_confidence: float,
    ) -> float:
        """Return ``min(sufficiency_confidence / original_confidence, 1.0)``.

        Returns ``0.0`` when ``original_confidence`` is zero or negative.
        """
        if original_confidence <= 0.0:
            return 0.0
        return min(sufficiency_confidence / original_confidence, 1.0)


# ---------------------------------------------------------------------------
# Envelope stage adapter (see openspec/changes/interactive-stage-cli)
# ---------------------------------------------------------------------------

STAGE_NAME = "sufficiency_evaluator"


def process(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Compute B1 sufficiency/counterfactual metrics for each sample.

    ``cited_evidence_ids`` are the news_ids of the selector's pro and
    counter groups (ported from the old ``PipelineRunner._run_group``).
    """
    from src.forecast_model import build_forecast_request

    evaluator = SufficiencyEvaluator()
    for sample in envelope["samples"]:
        selection = sample["selection"]
        cited_ids = {e["news_id"] for e in selection["pro_evidence"]} | {
            e["news_id"] for e in selection["counterevidence"]
        }
        request = build_forecast_request(sample)
        sample["sufficiency"] = evaluator.evaluate(
            request, sample["forecast"], cited_ids
        )
    envelope["stage"] = STAGE_NAME
    return envelope


def main(argv: Optional[List[str]] = None) -> int:
    from src.stage_io import run_stage_cli

    return run_stage_cli(
        STAGE_NAME,
        "Compute B1 sufficiency and counterfactual metrics per sample.",
        process,
        argv,
    )


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main())
