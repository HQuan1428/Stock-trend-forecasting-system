"""Evidence Selector.

The fourth stage in the faithful-evidence-forecasting pipeline. Given a
single forecast prediction (UP / DOWN / HOLD) and a list of evidence
candidates produced by the Evidence Extractor, it classifies each
candidate into one of three groups relative to the prediction:

- ``pro_evidence``       — evidence that supports the prediction
- ``counterevidence``    — evidence that conflicts with the prediction
- ``neutral_evidence``   — evidence that is neither clearly supportive
                           nor conflicting

Version 1 is a **deterministic, rule-based, side-effect-free** pure
function with no ML, LLM, FinBERT, transformer, network, or external
service dependencies. The classification is a fixed
``(prediction, expected_direction) → selector_label`` table; the
``reason`` string is emitted verbatim in the output for auditability.

Scope and contract:

- The selector consumes a per-prediction request and emits a
  structured per-prediction result object. It does NOT produce
  predictions (the Forecast Model owns that) and does NOT re-extract
  evidence from raw news text (the Evidence Extractor owns that).
- The selector does NOT re-implement temporal filtering. The Temporal
  Retriever owns temporal validity; the selector only flags (in
  ``invalid_future_evidence``) any candidate whose ``news_time >
  forecast_time`` as a defense-in-depth smoke alarm. Such items are
  never placed in any pro/counter/neutral group.
- The selector MUST NOT read a ground-truth label, an ``actual`` field,
  or any other field that would constitute label leakage. Extra fields
  on a candidate are passed through unchanged but ignored for
  classification.

See ``openspec/changes/evidence-selector/specs/evidence-selector/spec.md``
for the full normative specification.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.retriever import _normalize_to_utc, _parse_datetime


# ---------------------------------------------------------------------------
# Public exceptions
# ---------------------------------------------------------------------------


class EvidenceSelectorError(ValueError):
    """Raised for unrecoverable input problems (e.g., bad ``prediction``)."""


# ---------------------------------------------------------------------------
# Field constants (introspectable by tests and downstream code)
# ---------------------------------------------------------------------------


REQUIRED_INPUT_FIELDS = ("ticker", "forecast_time", "prediction", "confidence", "evidence_candidates")

OUTPUT_GROUPS = ("pro_evidence", "counterevidence", "neutral_evidence")

#: Output evidence-item fields preserved from the input candidate.
EVIDENCE_SELECTOR_FIELDS = (
    "news_id",
    "ticker",
    "news_time",
    "evidence_text",
    "polarity",
    "expected_direction",
    "extractor_score",
    "selector_label",
    "selector_score",
    "reason",
)

#: Per-group ``top_k`` defaults.
DEFAULT_TOP_K = {"pro_evidence": 3, "counterevidence": 3, "neutral_evidence": 3}

#: Literals allowed in ``prediction`` and ``expected_direction``.
VALID_PREDICTIONS = ("UP", "DOWN", "HOLD")
VALID_DIRECTIONS = ("UP", "DOWN", "HOLD")

#: Output literal for ``selection_method`` (kept stable for downstream parsing).
SELECTION_METHOD = "rule_based"


# ---------------------------------------------------------------------------
# Classification rules (single source of truth)
# ---------------------------------------------------------------------------
# Single source of truth for (prediction, expected_direction) classification.
# Downstream modules (Faithfulness Evaluator, Dashboard) MUST import
# ``CLASSIFICATION_TABLE`` and ``REASON_TABLE`` from this module rather than
# redefining the rules. The constants are also re-exported from
# ``src/__init__.py`` for ergonomic access.


CLASSIFICATION_TABLE: Dict[Tuple[str, str], str] = {
    # prediction=UP
    ("UP", "UP"): "pro",
    ("UP", "DOWN"): "counter",
    ("UP", "HOLD"): "neutral",
    # prediction=DOWN
    ("DOWN", "DOWN"): "pro",
    ("DOWN", "UP"): "counter",
    ("DOWN", "HOLD"): "neutral",
    # prediction=HOLD
    ("HOLD", "HOLD"): "pro",
    ("HOLD", "UP"): "counter",
    ("HOLD", "DOWN"): "counter",
}

REASON_TABLE: Dict[Tuple[str, str], str] = {
    ("UP", "UP"): "Evidence expected direction UP matches prediction UP",
    ("UP", "DOWN"): "Evidence expected direction DOWN conflicts with prediction UP",
    ("UP", "HOLD"): "Evidence expected direction HOLD is not directional for prediction UP",
    ("DOWN", "DOWN"): "Evidence expected direction DOWN matches prediction DOWN",
    ("DOWN", "UP"): "Evidence expected direction UP conflicts with prediction DOWN",
    ("DOWN", "HOLD"): "Evidence expected direction HOLD is not directional for prediction DOWN",
    ("HOLD", "HOLD"): "Evidence expected direction HOLD matches prediction HOLD",
    ("HOLD", "UP"): "Evidence expected direction UP conflicts with prediction HOLD",
    ("HOLD", "DOWN"): "Evidence expected direction DOWN conflicts with prediction HOLD",
}


def _classify(prediction: str, expected_direction: str) -> Tuple[str, str]:
    """Return ``(selector_label, reason)`` for a single cell of the table.

    Raises ``EvidenceSelectorError`` for an unknown ``prediction`` or an
    unknown ``expected_direction``. This helper is for well-formed
    pairs only; callers should pre-validate the input shape.
    """
    if prediction not in VALID_PREDICTIONS:
        raise EvidenceSelectorError(
            f"prediction must be one of {VALID_PREDICTIONS}, got {prediction!r}"
        )
    if expected_direction not in VALID_DIRECTIONS:
        raise EvidenceSelectorError(
            f"expected_direction must be one of {VALID_DIRECTIONS}, "
            f"got {expected_direction!r}"
        )
    label = CLASSIFICATION_TABLE[(prediction, expected_direction)]
    reason = REASON_TABLE[(prediction, expected_direction)]
    return label, reason


# ---------------------------------------------------------------------------
# Future-evidence helpers
# ---------------------------------------------------------------------------


def _parse_news_time(value: Any) -> Any:
    """Parse ``news_time`` defensively. Returns ``None`` for missing or
    unparseable values (so the candidate is treated as not-future).
    """
    if value is None or not isinstance(value, str) or not value.strip():
        return None
    try:
        return _normalize_to_utc(_parse_datetime(value))
    except ValueError:
        return None


def _parse_forecast_time(value: Any) -> Any:
    """Parse ``forecast_time``. Raises ``EvidenceSelectorError`` on a bad
    value because ``forecast_time`` is a top-level required field whose
    failure should not be silently masked.
    """
    if value is None or not isinstance(value, str) or not value.strip():
        raise EvidenceSelectorError(
            f"forecast_time must be a non-empty string, got {value!r}"
        )
    try:
        return _normalize_to_utc(_parse_datetime(value))
    except ValueError as exc:
        raise EvidenceSelectorError(
            f"forecast_time is not a parseable timestamp: {value!r}"
        ) from exc


def _is_future(news_time_dt: Any, forecast_time_dt: Any) -> bool:
    """Return True iff ``news_time_dt`` is strictly after ``forecast_time_dt``.

    A naive-or-aware mix is handled by ``_normalize_to_utc`` upstream.
    """
    if news_time_dt is None or forecast_time_dt is None:
        return False
    return news_time_dt > forecast_time_dt


# ---------------------------------------------------------------------------
# Ranking and top_k helpers
# ---------------------------------------------------------------------------


def _sort_by_score_desc(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Stable sort by ``selector_score`` descending.

    Python's sort is stable, so ties preserve input order.
    """
    return sorted(items, key=lambda x: -float(x.get("selector_score", 0.0)))


def _truncate(items: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    """Return the first ``top_k`` items (the input is already sorted)."""
    if top_k is None or top_k < 0:
        return items
    return items[:top_k]


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def _build_summary(
    pro_full: List[Dict[str, Any]],
    counter_full: List[Dict[str, Any]],
    neutral_full: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute summary counts and the ``counterevidence_ratio``.

    Counts use the pre-truncation lists so the dashboard can show
    "5 of 12 shown" affordances.
    """
    pro_count = len(pro_full)
    counter_count = len(counter_full)
    neutral_count = len(neutral_full)
    total = pro_count + counter_count
    ratio = (counter_count / total) if total > 0 else 0.0
    return {
        "pro_count": pro_count,
        "counter_count": counter_count,
        "neutral_count": neutral_count,
        "has_counterevidence": counter_count > 0,
        "counterevidence_ratio": ratio,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def select_evidence(
    request: Dict[str, Any],
    *,
    top_k_pro: int = 3,
    top_k_counter: int = 3,
    top_k_neutral: int = 3,
) -> Dict[str, Any]:
    """Classify evidence candidates relative to a forecast prediction.

    Args:
        request: Dict with required keys ``ticker``, ``forecast_time``,
            ``prediction``, ``confidence``, ``evidence_candidates``.
        top_k_pro: Cap on items in ``pro_evidence`` after sorting
            (default 3).
        top_k_counter: Cap on items in ``counterevidence`` (default 3).
        top_k_neutral: Cap on items in ``neutral_evidence`` (default 3).

    Returns:
        A result dict matching the spec: ``ticker``, ``forecast_time``,
        ``prediction``, ``confidence``, ``pro_evidence``,
        ``counterevidence``, ``neutral_evidence``,
        ``invalid_future_evidence``, ``summary``, and
        ``selection_method = "rule_based"``.

    Raises:
        EvidenceSelectorError: if ``prediction`` is missing/invalid or
            ``evidence_candidates`` is missing/not a list, or
            ``forecast_time`` is missing or unparseable.
    """
    # --- 1. Top-level validation (hard fail) ----------------------------
    if not isinstance(request, dict):
        raise EvidenceSelectorError(
            f"request must be a dict, got {type(request).__name__}"
        )
    prediction = request.get("prediction")
    if prediction not in VALID_PREDICTIONS:
        raise EvidenceSelectorError(
            f"prediction must be one of {VALID_PREDICTIONS}, got {prediction!r}"
        )
    candidates = request.get("evidence_candidates")
    if not isinstance(candidates, list):
        raise EvidenceSelectorError(
            f"evidence_candidates must be a list, got {type(candidates).__name__}"
        )

    ticker = request.get("ticker")
    forecast_time_raw = request.get("forecast_time")
    forecast_time_dt = _parse_forecast_time(forecast_time_raw)
    confidence = request.get("confidence")
    forecast_time_echo = forecast_time_raw  # echoed verbatim per spec

    # --- 2. Classify each candidate -------------------------------------
    pro_full: List[Dict[str, Any]] = []
    counter_full: List[Dict[str, Any]] = []
    neutral_full: List[Dict[str, Any]] = []
    invalid_future: List[Dict[str, Any]] = []
    invalid_candidates: List[Dict[str, Any]] = []

    for cand in candidates:
        if not isinstance(cand, dict):
            invalid_candidates.append(
                {"news_id": None, "reason": "candidate_not_a_dict"}
            )
            continue

        news_id = cand.get("news_id")
        news_time = cand.get("news_time")
        expected_direction = cand.get("expected_direction")
        extractor_score = cand.get("extractor_score", 0.0)

        # --- 2a. Malformed candidate -> invalid_candidates ---------------
        if expected_direction not in VALID_DIRECTIONS:
            invalid_candidates.append(
                {
                    "news_id": news_id,
                    "reason": "missing_or_unknown_expected_direction",
                }
            )
            continue

        # --- 2b. Future-evidence flagging -------------------------------
        news_time_dt = _parse_news_time(news_time)
        if _is_future(news_time_dt, forecast_time_dt):
            invalid_future.append(
                {
                    "news_id": news_id,
                    "news_time": news_time,
                    "reason": "future_evidence",
                }
            )
            continue

        # --- 2c. Classify ----------------------------------------------
        label, reason = _classify(prediction, expected_direction)

        out_item: Dict[str, Any] = {
            "news_id": news_id,
            "ticker": cand.get("ticker"),
            "news_time": news_time,
            "evidence_text": cand.get("evidence_text"),
            "polarity": cand.get("polarity"),
            "expected_direction": expected_direction,
            "extractor_score": extractor_score,
            "selector_label": label,
            "selector_score": float(extractor_score) if extractor_score is not None else 0.0,
            "reason": reason,
        }
        if label == "pro":
            pro_full.append(out_item)
        elif label == "counter":
            counter_full.append(out_item)
        else:
            neutral_full.append(out_item)

    # --- 3. Sort + top_k truncate ---------------------------------------
    pro_sorted = _sort_by_score_desc(pro_full)
    counter_sorted = _sort_by_score_desc(counter_full)
    neutral_sorted = _sort_by_score_desc(neutral_full)

    pro = _truncate(pro_sorted, top_k_pro)
    counter = _truncate(counter_sorted, top_k_counter)
    neutral = _truncate(neutral_sorted, top_k_neutral)

    # --- 4. Summary (uses pre-truncation counts) ------------------------
    summary = _build_summary(pro_full, counter_full, neutral_full)

    result: Dict[str, Any] = {
        "ticker": ticker,
        "forecast_time": forecast_time_echo,
        "prediction": prediction,
        "confidence": confidence,
        "pro_evidence": pro,
        "counterevidence": counter,
        "neutral_evidence": neutral,
        "invalid_future_evidence": invalid_future,
        "summary": summary,
        "selection_method": SELECTION_METHOD,
    }
    if invalid_candidates:
        result["invalid_candidates"] = invalid_candidates
    return result


def select_evidence_batch(
    requests: List[Dict[str, Any]],
    *,
    top_k_pro: int = 3,
    top_k_counter: int = 3,
    top_k_neutral: int = 3,
) -> List[Dict[str, Any]]:
    """Apply :func:`select_evidence` to a list of requests.

    Returns one result per input, in the same order. Does NOT filter
    or reorder by time — temporal validity is owned by the Temporal
    Retriever, and per-request time handling is done inside
    ``select_evidence``.
    """
    return [
        select_evidence(
            req,
            top_k_pro=top_k_pro,
            top_k_counter=top_k_counter,
            top_k_neutral=top_k_neutral,
        )
        for req in requests
    ]


def compute_coverage(
    result: Dict[str, Any],
    expected_labels: Dict[str, str],
) -> Dict[str, Any]:
    """Compute per-prediction Counterevidence Coverage from a selector result.

    Args:
        result: A result dict produced by :func:`select_evidence`.
        expected_labels: Mapping from ``news_id`` to the manually
            annotated expected ``selector_label`` (one of
            ``"pro"``, ``"counter"``, ``"neutral"``) for each
            evidence candidate considered for this prediction.

    Returns:
        A dict with:

        - ``available_counterevidence_count``: how many of the
          ``expected_labels`` values are ``"counter"``.
        - ``detected_counterevidence_count``: how many of those
          ``"counter"`` items are also in ``result["counterevidence"]``
          (matched by ``news_id``).
        - ``counterevidence_coverage``: ``detected / available`` when
          available > 0, else ``0.0``.
        - ``counterevidence_detected_rate``: ``1.0`` if
          ``detected > 0`` else ``0.0`` (per-prediction analogue of
          the dataset-level rate).

    This helper exists for the Faithfulness Evaluator to use. It
    NEVER reads a label from the input candidate list — only from the
    caller-supplied ``expected_labels`` argument.
    """
    available = sum(1 for v in expected_labels.values() if v == "counter")
    counter_ids = {
        e.get("news_id") for e in result.get("counterevidence", []) if e.get("news_id") is not None
    }
    detected = sum(
        1
        for news_id, label in expected_labels.items()
        if label == "counter" and news_id in counter_ids
    )
    coverage = (detected / available) if available > 0 else 0.0
    return {
        "available_counterevidence_count": available,
        "detected_counterevidence_count": detected,
        "counterevidence_coverage": coverage,
        "counterevidence_detected_rate": 1.0 if detected > 0 else 0.0,
    }
