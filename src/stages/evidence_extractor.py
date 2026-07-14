"""Evidence Extractor.

The second stage in the faithful-evidence-forecasting pipeline. Given a
single news item, it extracts a list of evidence phrases from
``news_text`` using a deterministic, rule-based keyword dictionary.

Behavior (Version 1):

- Searches ``news_text`` case-insensitively for every Version 1 keyword.
- Returns every non-overlapping positive and negative keyword match.
- Returns exactly one neutral evidence object when no keyword matches.
- Preserves ``forecast_time`` and ``news_time`` unchanged in the output.
- Does NOT filter by time — the Temporal Retriever owns temporal validity.
- Does NOT produce predictions or trading advice.

See ``openspec/changes/evidence-extractor/specs/evidence-extractor/spec.md``
for the full normative specification.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class EvidenceExtractor:
    """Extracts keyword-matched evidence phrases from news text.

    ``POSITIVE_KEYWORDS`` / ``NEGATIVE_KEYWORDS`` are the single source
    of truth for polarity. Downstream classes (Evidence Selector,
    Counterevidence Coverage, Forecast Model) MUST read
    ``EvidenceExtractor.KEYWORD_TO_POLARITY`` / ``POLARITY_TO_DIRECTION``
    rather than redefining polarity rules.
    """

    # -----------------------------------------------------------------
    # Keyword dictionary (Version 3; V1 entries retained verbatim, V2/V3
    # appended). See openspec/changes/enrich-evidence-keywords-v2/ and
    # .../enrich-evidence-keywords-v3/ for the rationale behind each
    # addition and the false-positive checks run against the sample.
    # -----------------------------------------------------------------

    POSITIVE_KEYWORDS: List[str] = [
        # Version 1
        "beats expectations",
        "record profit",
        "strong sales",
        "raises guidance",
        "launches new product",
        # Version 2 additions
        "stronger than expected",
        "faster growth",
        "positive analyst",
        "wins a",
        "signs a",
        "accelerate",
        "record level",
        "raises shipment outlook",
        # Version 3 additions — shorter / softer UP signals
        "launches",
        "expands",
        "improvement",
        "stronger",
        "secures",
        "receives",
        "praise",
        "preorders",
        "cost efficient",
        "backlog expands",
        "advertiser retention",
        "adoption",
        "introduces",
        "accelerated",
        "better conversion",
        "carrier partnership",
        "upgrade",
        "automation",
        "advertising marketplace",
        "supply agreement",
        "demand from",
    ]

    NEGATIVE_KEYWORDS: List[str] = [
        # Version 1
        "misses expectations",
        "weak sales",
        "recall",
        "lawsuit",
        "cuts guidance",
        "decline",
        # Version 2 additions
        "antitrust complaint",
        "softer orders",
        "slower growth",
        "warns of",
        "warns that",
        "faces a",
        "is fined",
        "fined for",
        "delays production",
        "lowers outlook",
        "outage",
        "probe into",
        "regulatory costs",
        "downgraded",
        "vote to authorize a strike",
        "complaint",
        "delays",
        "cuts the price",
        "budget cuts",
        "complain about",
        "losses widen",
        "loses an appeal",
        "overheating",
        "lowers revenue guidance",
        # Version 3 additions — shorter / softer DOWN signals
        "warns",
        "slower",
        "softer",
        "weaker",
        "lower",
        "reduced",
        "reduces",
        "class action",
        "criticism",
        "pauses",
        "delivery delays",
        "fresh lawsuit",
        "outage in",
        "permitting",
        "delays a planned",
        "downgrade",
    ]

    # Flat dict mapping keyword -> "positive" or "negative". Built once at
    # class-definition time so a typo in either list is caught at import time.
    KEYWORD_TO_POLARITY: Dict[str, str] = {kw: "positive" for kw in POSITIVE_KEYWORDS}
    for _kw in NEGATIVE_KEYWORDS:
        if _kw in KEYWORD_TO_POLARITY:
            raise ValueError(
                f"keyword {_kw!r} appears in both POSITIVE and NEGATIVE lists"
            )
        KEYWORD_TO_POLARITY[_kw] = "negative"
    del _kw

    #: Combined list for downstream reuse (Evidence Selector,
    #: Counterevidence Coverage). Order: positive first, then negative.
    KEYWORDS: List[str] = POSITIVE_KEYWORDS + NEGATIVE_KEYWORDS

    POLARITY_TO_DIRECTION: Dict[str, str] = {
        "positive": "UP",
        "negative": "DOWN",
        "neutral": "HOLD",
    }

    SUPPORT_SCORES: Dict[str, float] = {
        "positive": 1.0,
        "negative": 1.0,
        "neutral": 0.5,
    }

    EXTRACTION_METHOD: str = "rule_based_keyword"

    # Maximum gap (in characters) between consecutive keyword words during
    # token-level matching. About 2-3 English words. Wide enough to absorb
    # a single noun modifier (e.g. "weak iPhone sales"), narrow enough to
    # avoid unrelated words bridging across sentences.
    _MAX_TOKEN_GAP: int = 15

    # Polarity priority for primary-evidence selection (negative > positive > neutral).
    _POLARITY_PRIORITY = {"negative": 0, "positive": 1, "neutral": 2}

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def extract(self, news_item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract evidence from a single news item.

        Args:
            news_item: Dict with required keys ``news_id``, ``ticker``,
                ``forecast_time``, ``news_time``, ``news_text``. Extra keys
                on the input are not propagated to the result — only the
                four metadata fields above are echoed back.

        Returns:
            A result dict matching the OpenSpec output schema:
            ``news_id``, ``ticker``, ``forecast_time``, ``news_time``,
            ``evidence`` (non-empty list), ``summary``,
            ``extraction_method`` (literal ``"rule_based_keyword"``), and
            ``primary_evidence_id``.
        """
        news_id: str = news_item["news_id"]
        ticker: str = news_item["ticker"]
        forecast_time: str = news_item["forecast_time"]
        news_time: str = news_item["news_time"]
        news_text: str = news_item["news_text"]

        occurrences = self._find_keyword_occurrences(news_text, self.KEYWORDS)
        matches = self._resolve_overlaps(occurrences)
        evidence = self.build_evidence_objects(news_id, news_text, matches)
        summary = self.build_summary(evidence)

        return {
            "news_id": news_id,
            "ticker": ticker,
            "forecast_time": forecast_time,
            "news_time": news_time,
            "evidence": evidence,
            "summary": summary,
            "extraction_method": self.EXTRACTION_METHOD,
            "primary_evidence_id": self.select_primary_evidence_id(evidence),
        }

    def extract_batch(self, news_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply :meth:`extract` to a list of news items.

        Returns one result per input, in the same order. Does NOT filter
        or reorder by time — temporal validity is owned by the Temporal
        Retriever.
        """
        return [self.extract(item) for item in news_items]

    def build_evidence_objects(
        self, news_id: str, news_text: str, matches: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert resolved keyword matches into evidence dicts.

        Assigns deterministic ``evidence_id`` in text order (1-based,
        zero-padded to 3 digits). The ``evidence_text`` is the lowercased
        slice of the matched range in ``news_text``.

        If ``matches`` is empty, returns exactly one neutral evidence object.
        """
        if not matches:
            return [
                {
                    "evidence_id": self._make_evidence_id(news_id, 1),
                    "news_id": news_id,
                    "evidence_text": "",
                    "polarity": "neutral",
                    "expected_direction": self.POLARITY_TO_DIRECTION["neutral"],
                    "matched_keyword": None,
                    "start_char": 0,
                    "end_char": 0,
                    "support_score": self.SUPPORT_SCORES["neutral"],
                }
            ]

        evidence: List[Dict[str, Any]] = []
        for idx, match in enumerate(matches, start=1):
            polarity = match["polarity"]
            evidence.append(
                {
                    "evidence_id": self._make_evidence_id(news_id, idx),
                    "news_id": news_id,
                    "evidence_text": news_text[
                        match["start_char"]: match["end_char"]
                    ].lower(),
                    "polarity": polarity,
                    "expected_direction": self.POLARITY_TO_DIRECTION[polarity],
                    "matched_keyword": match["keyword"],
                    "start_char": match["start_char"],
                    "end_char": match["end_char"],
                    "support_score": self.SUPPORT_SCORES[polarity],
                }
            )
        return evidence

    def build_summary(self, evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute summary counts and the mixed-evidence flag."""
        positive_count = sum(1 for e in evidence if e["polarity"] == "positive")
        negative_count = sum(1 for e in evidence if e["polarity"] == "negative")
        neutral_count = sum(1 for e in evidence if e["polarity"] == "neutral")
        total = len(evidence)
        return {
            "positive_count": positive_count,
            "negative_count": negative_count,
            "neutral_count": neutral_count,
            "total_evidence_count": total,
            "has_mixed_evidence": positive_count >= 1 and negative_count >= 1,
        }

    def select_primary_evidence_id(
        self, evidence: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Choose the primary evidence ID using the deterministic rule:

        1. Prefer evidence with ``polarity = "negative"`` (highest priority).
        2. Then ``polarity = "positive"``.
        3. Then ``polarity = "neutral"``.
        4. Tie-break by smallest ``start_char`` (earliest in text).

        Returns ``None`` only if the evidence list is empty (defensive;
        the spec forbids this in V1).
        """
        if not evidence:
            return None
        best = min(
            evidence,
            key=lambda e: (
                self._POLARITY_PRIORITY.get(e["polarity"], 99),
                e["start_char"],
            ),
        )
        return best["evidence_id"]

    def result_to_dict(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Return ``result`` as a plain dict.

        Today every result is already a plain dict, so this is an
        identity function. It exists so callers can normalize regardless
        of any future dataclass representation.
        """
        return dict(result)

    # -----------------------------------------------------------------
    # Private matching helpers
    # -----------------------------------------------------------------

    def _find_keyword_occurrences(
        self, news_text: str, keywords: List[str]
    ) -> List[Dict[str, Any]]:
        """Find every keyword occurrence in ``news_text`` (case-insensitive).

        Two matching modes, tried in order per keyword:

        1. **Exact substring match** — ``str.find`` left-to-right. All hits
           are recorded. Single-word keywords are matched this way
           exclusively.
        2. **Token-level match** — only for multi-word keywords with no
           exact hit. The keyword is split into words; each word is
           located in the lowercased text; we accept a window where the
           words appear in order and the gap between consecutive keyword
           words is at most ``_MAX_TOKEN_GAP`` characters. The match span
           runs from the first word's start to the last word's end. This
           lets ``"weak sales"`` match ``"weak iPhone sales"`` and
           produces ``evidence_text = "weak iPhone sales"`` — the spec's
           acceptance criterion 1.

        ``start_char`` / ``end_char`` are offsets into the ORIGINAL
        ``news_text`` (same-length lowercase preserves offsets).
        """
        lowered = news_text.lower()
        occurrences: List[Dict[str, Any]] = []

        for keyword in keywords:
            kw_lower = keyword.lower()
            kw_words = kw_lower.split()
            polarity = self.KEYWORD_TO_POLARITY[keyword]

            # --- 1. Exact substring match -----------------------------------
            start = 0
            found_exact = False
            while True:
                idx = lowered.find(kw_lower, start)
                if idx == -1:
                    break
                found_exact = True
                occurrences.append(
                    {
                        "start_char": idx,
                        "end_char": idx + len(kw_lower),
                        "keyword": keyword,
                        "polarity": polarity,
                    }
                )
                start = idx + 1

            if found_exact or len(kw_words) < 2:
                continue

            # --- 2. Token-level match (multi-word keywords only) -------------
            word_positions: List[List[int]] = []
            for word in kw_words:
                positions: List[int] = []
                scan = 0
                while True:
                    idx = lowered.find(word, scan)
                    if idx == -1:
                        break
                    positions.append(idx)
                    scan = idx + 1
                word_positions.append(positions)

            # Every keyword word must appear at least once.
            if any(not positions for positions in word_positions):
                continue

            # Enumerate windows: at each depth, pick one of the word's
            # positions, then recurse. Accept the window if positions are
            # in ascending order and gaps are within the cap.
            def _enumerate(idx: int, combo: List[int]) -> None:
                if idx == len(kw_words):
                    if combo == sorted(combo):
                        valid = True
                        for i in range(len(combo) - 1):
                            end_of_prev = combo[i] + len(kw_words[i])
                            gap = combo[i + 1] - end_of_prev
                            if gap < 0 or gap > self._MAX_TOKEN_GAP:
                                valid = False
                                break
                        if valid:
                            start_char = combo[0]
                            end_char = combo[-1] + len(kw_words[-1])
                            occurrences.append(
                                {
                                    "start_char": start_char,
                                    "end_char": end_char,
                                    "keyword": keyword,
                                    "polarity": polarity,
                                }
                            )
                    return
                for pos in word_positions[idx]:
                    _enumerate(idx + 1, combo + [pos])

            _enumerate(0, [])

        return occurrences

    def _resolve_overlaps(
        self, matches: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Resolve overlapping matches by keeping the longest (earliest on ties).

        Sorts by ``(length descending, start_char ascending)``, then walks
        the sorted list and drops any match that overlaps a previously
        kept match. The final list is re-sorted by ascending ``start_char``
        for a stable, text-ordered output.

        Two ranges overlap iff neither is strictly to the left of the other:
            overlap = NOT (a.end <= b.start OR a.start >= b.end)
        """
        if not matches:
            return []
        sorted_matches = sorted(
            matches,
            key=lambda m: (-(m["end_char"] - m["start_char"]), m["start_char"]),
        )
        kept: List[Dict[str, Any]] = []
        for match in sorted_matches:
            overlaps = False
            for k in kept:
                if not (
                    match["end_char"] <= k["start_char"]
                    or match["start_char"] >= k["end_char"]
                ):
                    overlaps = True
                    break
            if not overlaps:
                kept.append(match)
        # Two kept matches with the same start_char but different lengths
        # cannot both survive overlap resolution (the shorter is contained
        # in the longer), so sorting by start_char alone produces a
        # deterministic, text-ordered list.
        kept.sort(key=lambda m: m["start_char"])
        return kept

    def _make_evidence_id(self, news_id: str, index: int) -> str:
        """Format evidence_id as ``<news_id>_E<index>`` with index zero-padded
        to 3 digits per the spec (e.g. ``N001_E001``).
        """
        return f"{news_id}_E{index:03d}"


# ---------------------------------------------------------------------------
# Envelope stage adapter (see openspec/changes/interactive-stage-cli)
# ---------------------------------------------------------------------------

STAGE_NAME = "evidence_extractor"


def process(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Extract evidence from each sample's ``valid_news``.

    Builds the extractor input shape from the envelope (ported from the
    old ``PipelineRunner._build_extractor_input``), runs
    ``extract_batch``, and flattens the per-news evidence lists into one
    ``evidence`` list per sample, attaching ``news_time`` to every item.
    """
    extractor = EvidenceExtractor()
    for sample in envelope["samples"]:
        inputs = [
            {
                "news_id": str(n["news_id"]),
                "ticker": sample["ticker"],
                "forecast_time": sample["forecast_time"],
                "news_time": str(n["news_time"]),
                "news_text": str(n.get("news_text", n.get("text", ""))),
            }
            for n in sample["valid_news"]
        ]
        results = extractor.extract_batch(inputs)
        evidence: List[Dict[str, Any]] = []
        for news, result in zip(sample["valid_news"], results):
            for item in result["evidence"]:
                item["news_time"] = str(news["news_time"])
                evidence.append(item)
        sample["evidence"] = evidence
    envelope["stage"] = STAGE_NAME
    return envelope


def main(argv: Optional[List[str]] = None) -> int:
    from src.core.stage_io import run_stage_cli

    return run_stage_cli(
        STAGE_NAME,
        "Extract rule-based keyword evidence from each sample's valid news.",
        process,
        argv,
    )


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main())
