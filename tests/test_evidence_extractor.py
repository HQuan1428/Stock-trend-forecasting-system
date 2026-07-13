"""Unit tests for the Evidence Extractor (Version 1)."""

from __future__ import annotations

import pytest

from src.stages.evidence_extractor import EvidenceExtractor

_extractor = EvidenceExtractor()
EXTRACTION_METHOD = EvidenceExtractor.EXTRACTION_METHOD
KEYWORDS = EvidenceExtractor.KEYWORDS
KEYWORD_TO_POLARITY = EvidenceExtractor.KEYWORD_TO_POLARITY
NEGATIVE_KEYWORDS = EvidenceExtractor.NEGATIVE_KEYWORDS
POLARITY_TO_DIRECTION = EvidenceExtractor.POLARITY_TO_DIRECTION
POSITIVE_KEYWORDS = EvidenceExtractor.POSITIVE_KEYWORDS
SUPPORT_SCORES = EvidenceExtractor.SUPPORT_SCORES
_find_keyword_occurrences = _extractor._find_keyword_occurrences
_resolve_overlaps = _extractor._resolve_overlaps
build_evidence_objects = _extractor.build_evidence_objects
build_summary = _extractor.build_summary
extract_evidence = _extractor.extract
extract_evidence_batch = _extractor.extract_batch
select_primary_evidence_id = _extractor.select_primary_evidence_id


# ---------------------------------------------------------------------------
# Module / dictionary constants
# ---------------------------------------------------------------------------


def test_positive_keywords_match_spec_vocabulary() -> None:
    # Version 3 — V1, V2, and V3 entries are all preserved. V1 leads, V2
    # additions follow, and V3 additions are appended last. See
    # openspec/changes/enrich-evidence-keywords-v2/ and
    # openspec/changes/enrich-evidence-keywords-v3/ for the rationale
    # behind each entry.
    assert POSITIVE_KEYWORDS == [
        # V1
        "beats expectations",
        "record profit",
        "strong sales",
        "raises guidance",
        "launches new product",
        # V2 additions
        "stronger than expected",
        "faster growth",
        "positive analyst",
        "wins a",
        "signs a",
        "accelerate",
        "record level",
        "raises shipment outlook",
        # V3 additions — shorter / softer UP signals
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


def test_negative_keywords_match_spec_vocabulary() -> None:
    # Version 3 — V1, V2, and V3 entries are all preserved. V1 leads, V2
    # additions follow, and V3 additions are appended last. See
    # openspec/changes/enrich-evidence-keywords-v2/ and
    # openspec/changes/enrich-evidence-keywords-v3/ for the rationale
    # behind each entry.
    assert NEGATIVE_KEYWORDS == [
        # V1
        "misses expectations",
        "weak sales",
        "recall",
        "lawsuit",
        "cuts guidance",
        "decline",
        # V2 additions
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
        # V3 additions — shorter / softer DOWN signals
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


def test_keyword_to_polarity_is_consistent_with_lists() -> None:
    for kw in POSITIVE_KEYWORDS:
        assert KEYWORD_TO_POLARITY[kw] == "positive"
    for kw in NEGATIVE_KEYWORDS:
        assert KEYWORD_TO_POLARITY[kw] == "negative"
    # The combined KEYWORDS list is positive-then-negative.
    assert KEYWORDS == POSITIVE_KEYWORDS + NEGATIVE_KEYWORDS


def test_polarity_to_direction_matches_spec_table() -> None:
    assert POLARITY_TO_DIRECTION == {
        "positive": "UP",
        "negative": "DOWN",
        "neutral": "HOLD",
    }


def test_support_scores_match_spec() -> None:
    assert SUPPORT_SCORES == {"positive": 1.0, "negative": 1.0, "neutral": 0.5}


def test_extraction_method_is_rule_based_keyword() -> None:
    assert EXTRACTION_METHOD == "rule_based_keyword"


# ---------------------------------------------------------------------------
# _find_keyword_occurrences + _resolve_overlaps helpers
# ---------------------------------------------------------------------------


def test_find_keyword_occurrences_is_case_insensitive() -> None:
    matches = _find_keyword_occurrences("MISSES EXPECTATIONS here", ["misses expectations"])
    assert len(matches) == 1
    assert matches[0]["start_char"] == 0
    # "misses expectations" is 19 characters: 6 + 1 + 12 = 19.
    assert matches[0]["end_char"] == 19
    assert matches[0]["polarity"] == "negative"


def test_find_keyword_occurrences_returns_all_non_overlapping_matches() -> None:
    matches = _find_keyword_occurrences(
        "lawsuit one, then lawsuit two", ["lawsuit"]
    )
    assert len(matches) == 2
    assert matches[0]["start_char"] < matches[1]["start_char"]


def test_resolve_overlaps_keeps_longest_on_overlap() -> None:
    # "strong sales" contains "sales" but "sales" is not a V1 keyword; build
    # a synthetic overlap with two keywords that share a range.
    matches = [
        {"start_char": 0, "end_char": 5, "keyword": "alpha", "polarity": "positive"},
        {"start_char": 2, "end_char": 10, "keyword": "alphabeta", "polarity": "positive"},
    ]
    resolved = _resolve_overlaps(matches)
    assert len(resolved) == 1
    assert resolved[0]["keyword"] == "alphabeta"


def test_resolve_overlaps_ties_break_by_earliest_start() -> None:
    matches = [
        {"start_char": 5, "end_char": 10, "keyword": "a", "polarity": "positive"},
        {"start_char": 5, "end_char": 10, "keyword": "b", "polarity": "positive"},
    ]
    resolved = _resolve_overlaps(matches)
    # Identical range -> first seen (in sorted order) wins; both have the
    # same length, so the one already first in the sorted input survives.
    assert len(resolved) == 1


def test_resolve_overlaps_keeps_non_overlapping_matches() -> None:
    matches = [
        {"start_char": 0, "end_char": 5, "keyword": "alpha", "polarity": "positive"},
        {"start_char": 10, "end_char": 15, "keyword": "beta", "polarity": "negative"},
    ]
    resolved = _resolve_overlaps(matches)
    assert len(resolved) == 2
    assert resolved[0]["start_char"] == 0
    assert resolved[1]["start_char"] == 10


def test_resolve_overlaps_sorts_final_list_by_start_char() -> None:
    # Even when input is in a weird order, the returned list is start-ordered.
    matches = [
        {"start_char": 30, "end_char": 35, "keyword": "later", "polarity": "negative"},
        {"start_char": 5, "end_char": 12, "keyword": "earlier", "polarity": "positive"},
    ]
    resolved = _resolve_overlaps(matches)
    assert [m["start_char"] for m in resolved] == [5, 30]


# ---------------------------------------------------------------------------
# Acceptance criteria 1-8 (spec.md)
# ---------------------------------------------------------------------------


def _make_item(news_text: str, news_id: str = "N001") -> dict:
    return {
        "news_id": news_id,
        "ticker": "X",
        "forecast_time": "2025-04-02 09:00",
        "news_time": "2025-04-01 16:00",
        "news_text": news_text,
    }


def test_acceptance_1_negative_only_news() -> None:
    """AC1: 'Apple reports weak iPhone sales in China' produces a negative
    evidence item whose evidence_text contains 'weak iPhone sales' or
    'weak sales'. evidence_text is lowercased per the spec, so we check
    for the lowercased variants."""
    result = extract_evidence(_make_item("Apple reports weak iPhone sales in China"))
    assert result["summary"]["negative_count"] >= 1
    matches = [e for e in result["evidence"] if e["polarity"] == "negative"]
    assert matches, "expected at least one negative evidence item"
    text = matches[0]["evidence_text"]
    assert "weak iphone sales" in text or "weak sales" in text
    assert matches[0]["expected_direction"] == "DOWN"


def test_acceptance_2_positive_only_news() -> None:
    """AC2: positive evidence items with positive polarity, UP direction."""
    result = extract_evidence(
        _make_item("Amazon beats expectations after strong sales in cloud services")
    )
    assert result["summary"]["positive_count"] >= 1
    for ev in result["evidence"]:
        assert ev["polarity"] == "positive"
        assert ev["expected_direction"] == "UP"


def test_acceptance_3_neutral_news_has_one_evidence_item() -> None:
    """AC3: 'Meta holds annual developer conference' returns one neutral item."""
    result = extract_evidence(_make_item("Meta holds annual developer conference"))
    assert len(result["evidence"]) == 1
    ev = result["evidence"][0]
    assert ev["polarity"] == "neutral"
    assert ev["expected_direction"] == "HOLD"
    assert ev["support_score"] == 0.5
    assert ev["matched_keyword"] is None
    assert result["summary"]["neutral_count"] == 1
    assert result["summary"]["positive_count"] == 0
    assert result["summary"]["negative_count"] == 0


def test_acceptance_4_mixed_news_has_mixed_evidence_and_correct_primary() -> None:
    """AC4: 'Google raises guidance despite lawsuit risk' returns positive +
    negative; has_mixed_evidence=true; primary points to negative."""
    result = extract_evidence(
        _make_item("Google raises guidance despite lawsuit risk")
    )
    matched_keywords = {e["matched_keyword"] for e in result["evidence"]}
    assert "raises guidance" in matched_keywords
    assert "lawsuit" in matched_keywords
    assert result["summary"]["has_mixed_evidence"] is True
    # Primary evidence is the negative "lawsuit".
    primary = next(e for e in result["evidence"] if e["evidence_id"] == result["primary_evidence_id"])
    assert primary["polarity"] == "negative"
    assert primary["matched_keyword"] == "lawsuit"


def test_acceptance_5_case_insensitive_matching() -> None:
    """AC5: 'Microsoft MISSES EXPECTATIONS in cloud revenue' matches lowercase
    'misses expectations' keyword."""
    result = extract_evidence(
        _make_item("Microsoft MISSES EXPECTATIONS in cloud revenue")
    )
    matched = [e for e in result["evidence"] if e["matched_keyword"] == "misses expectations"]
    assert len(matched) == 1
    assert matched[0]["polarity"] == "negative"
    assert matched[0]["expected_direction"] == "DOWN"


def test_acceptance_6_batch_returns_one_result_per_input_in_order() -> None:
    items = [
        _make_item("Apple reports weak iPhone sales in China", news_id="A"),
        _make_item("Meta holds annual developer conference", news_id="B"),
        _make_item("Google raises guidance despite lawsuit risk", news_id="C"),
    ]
    results = extract_evidence_batch(items)
    assert len(results) == 3
    assert [r["news_id"] for r in results] == ["A", "B", "C"]


def test_acceptance_7_datetime_fields_preserved_verbatim() -> None:
    item = _make_item("Any text here")
    item["forecast_time"] = "2025-03-12 09:00"
    item["news_time"] = "2025-03-11 15:30"
    result = extract_evidence(item)
    assert result["forecast_time"] == "2025-03-12 09:00"
    assert result["news_time"] == "2025-03-11 15:30"


def test_acceptance_8_future_news_is_not_filtered() -> None:
    """AC8: news_time > forecast_time still produces a result."""
    item = _make_item("Apple reports weak iPhone sales in China")
    item["news_time"] = "2099-01-01 00:00"  # far in the future
    item["forecast_time"] = "2025-04-02 09:00"
    result = extract_evidence(item)  # must not raise
    assert result["news_time"] == "2099-01-01 00:00"
    assert result["forecast_time"] == "2025-04-02 09:00"
    assert len(result["evidence"]) >= 1


# ---------------------------------------------------------------------------
# Edge cases (spec.md Edge Cases section)
# ---------------------------------------------------------------------------


def test_edge_empty_news_text_returns_one_neutral_evidence() -> None:
    result = extract_evidence(_make_item(""))
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["polarity"] == "neutral"
    assert result["evidence"][0]["support_score"] == 0.5
    assert result["evidence"][0]["matched_keyword"] is None


def test_edge_whitespace_only_news_text_returns_one_neutral_evidence() -> None:
    result = extract_evidence(_make_item("   \n\t  "))
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["polarity"] == "neutral"


def test_edge_non_overlapping_duplicate_keyword() -> None:
    text = "A lawsuit was filed. The lawsuit claims wrongdoing."
    result = extract_evidence(_make_item(text))
    lawsuit_items = [
        e for e in result["evidence"] if e["matched_keyword"] == "lawsuit"
    ]
    assert len(lawsuit_items) == 2
    assert lawsuit_items[0]["start_char"] < lawsuit_items[1]["start_char"]


def test_edge_overlapping_matches_resolve_to_longest() -> None:
    # Synthesize overlap via the helper directly (V1 keywords don't actually
    # overlap each other).
    matches = [
        {"start_char": 0, "end_char": 5, "keyword": "short", "polarity": "positive"},
        {"start_char": 2, "end_char": 12, "keyword": "longer_one", "polarity": "positive"},
    ]
    resolved = _resolve_overlaps(matches)
    assert len(resolved) == 1
    assert resolved[0]["keyword"] == "longer_one"


def test_edge_determinism_same_input_same_output() -> None:
    item = _make_item("Google raises guidance despite lawsuit risk")
    r1 = extract_evidence(item)
    r2 = extract_evidence(item)
    assert r1 == r2


def test_edge_each_evidence_has_all_required_fields() -> None:
    required = {
        "evidence_id",
        "news_id",
        "evidence_text",
        "polarity",
        "expected_direction",
        "matched_keyword",
        "start_char",
        "end_char",
        "support_score",
    }
    result = extract_evidence(
        _make_item("Apple reports weak iPhone sales in China, then a lawsuit")
    )
    for ev in result["evidence"]:
        assert required.issubset(ev.keys()), (
            f"missing fields in evidence: {required - ev.keys()}"
        )


def test_edge_result_has_extraction_method_and_summary_keys() -> None:
    result = extract_evidence(_make_item("Apple reports weak iPhone sales in China"))
    assert result["extraction_method"] == "rule_based_keyword"
    summary_keys = {
        "positive_count",
        "negative_count",
        "neutral_count",
        "total_evidence_count",
        "has_mixed_evidence",
    }
    assert summary_keys.issubset(result["summary"].keys())


# ---------------------------------------------------------------------------
# Spec scenarios (from spec.md Requirements section)
# ---------------------------------------------------------------------------


def test_scenario_multiple_distinct_positive_matches() -> None:
    """Spec: 'Amazon beats expectations after strong sales in cloud services'
    yields exactly two positive evidence items with the two keywords, in
    start_char order."""
    result = extract_evidence(
        _make_item("Amazon beats expectations after strong sales in cloud services")
    )
    assert result["summary"]["positive_count"] == 2
    matched = [e["matched_keyword"] for e in result["evidence"]]
    assert matched == ["beats expectations", "strong sales"]
    starts = [e["start_char"] for e in result["evidence"]]
    assert starts == sorted(starts)


def test_scenario_evidence_id_zero_padded_to_three_digits() -> None:
    result = extract_evidence(
        _make_item("Amazon beats expectations after strong sales in cloud services")
    )
    assert result["evidence"][0]["evidence_id"] == "N001_E001"
    assert result["evidence"][1]["evidence_id"] == "N001_E002"


def test_scenario_primary_evidence_tie_break_by_earliest_start() -> None:
    # Two negative evidence items, no positive. Primary must be the earliest.
    text = "A lawsuit was filed. Another lawsuit came later."
    result = extract_evidence(_make_item(text))
    negatives = [e for e in result["evidence"] if e["polarity"] == "negative"]
    assert len(negatives) >= 2
    primary = next(e for e in result["evidence"] if e["evidence_id"] == result["primary_evidence_id"])
    assert primary["polarity"] == "negative"
    # Tie-break: smallest start_char wins among negatives.
    earliest = min(negatives, key=lambda e: e["start_char"])
    assert primary["evidence_id"] == earliest["evidence_id"]


def test_scenario_news_id_propagated_to_evidence_objects() -> None:
    item = _make_item("Google raises guidance", news_id="N042")
    result = extract_evidence(item)
    assert result["news_id"] == "N042"
    for ev in result["evidence"]:
        assert ev["news_id"] == "N042"
        assert ev["evidence_id"].startswith("N042_E")


# ---------------------------------------------------------------------------
# Direction mapping per-polarity (sanity)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected_direction",
    [
        ("Apple beats expectations and reports record profit", "UP"),
        ("Microsoft misses expectations and faces a lawsuit", "DOWN"),
        ("Meta holds annual developer conference", "HOLD"),
    ],
)
def test_direction_mapping_per_polarity(text: str, expected_direction: str) -> None:
    result = extract_evidence(_make_item(text))
    # Every evidence item in this result has the same polarity (single-scenario).
    assert all(e["expected_direction"] == expected_direction for e in result["evidence"])
    assert result["evidence"][0]["expected_direction"] == expected_direction


# ---------------------------------------------------------------------------
# Batch and metadata propagation
# ---------------------------------------------------------------------------


def test_batch_preserves_ticker_and_datetimes_per_item() -> None:
    items = [
        {
            "news_id": "A",
            "ticker": "AAPL",
            "forecast_time": "2025-04-02 09:00",
            "news_time": "2025-04-01 16:00",
            "news_text": "Apple reports weak iPhone sales in China",
        },
        {
            "news_id": "B",
            "ticker": "META",
            "forecast_time": "2025-05-10 13:30",
            "news_time": "2025-05-10 13:00",
            "news_text": "Meta holds annual developer conference",
        },
    ]
    results = extract_evidence_batch(items)
    assert results[0]["ticker"] == "AAPL"
    assert results[1]["ticker"] == "META"
    assert results[0]["forecast_time"] == "2025-04-02 09:00"
    assert results[1]["news_time"] == "2025-05-10 13:00"


def test_select_primary_evidence_id_prefers_negative_then_positive_then_neutral() -> None:
    # Build a synthetic evidence list with mixed polarities and use the helper.
    evidence = [
        {"evidence_id": "X_E001", "polarity": "neutral", "start_char": 0},
        {"evidence_id": "X_E002", "polarity": "positive", "start_char": 5},
        {"evidence_id": "X_E003", "polarity": "negative", "start_char": 20},
        {"evidence_id": "X_E004", "polarity": "positive", "start_char": 50},
    ]
    assert select_primary_evidence_id(evidence) == "X_E003"


def test_select_primary_evidence_id_falls_back_to_neutral() -> None:
    evidence = [
        {"evidence_id": "X_E001", "polarity": "neutral", "start_char": 30},
        {"evidence_id": "X_E002", "polarity": "neutral", "start_char": 5},
    ]
    assert select_primary_evidence_id(evidence) == "X_E002"


def test_select_primary_evidence_id_empty_returns_none() -> None:
    assert select_primary_evidence_id([]) is None


def test_build_evidence_objects_returns_neutral_fallback_when_empty() -> None:
    ev = build_evidence_objects("N001", "", [])
    assert len(ev) == 1
    assert ev[0]["polarity"] == "neutral"
    assert ev[0]["matched_keyword"] is None
    assert ev[0]["evidence_id"] == "N001_E001"


def test_build_summary_counts_match_evidence_list() -> None:
    evidence = [
        {"polarity": "positive"},
        {"polarity": "positive"},
        {"polarity": "negative"},
        {"polarity": "neutral"},
    ]
    summary = build_summary(evidence)
    assert summary["positive_count"] == 2
    assert summary["negative_count"] == 1
    assert summary["neutral_count"] == 1
    assert summary["total_evidence_count"] == 4
    assert summary["has_mixed_evidence"] is True


def test_build_summary_no_mixed_when_only_one_polarity_present() -> None:
    evidence = [{"polarity": "positive"}, {"polarity": "positive"}]
    summary = build_summary(evidence)
    assert summary["has_mixed_evidence"] is False


# ---------------------------------------------------------------------------
# Version 2 keyword coverage tests (delta spec scenarios)
# ---------------------------------------------------------------------------
# These tests pin V2 behaviour on real sample sentences from
# data/sample_dataset.csv. They cover the "V2 keyword coverage on the
# project sample" and "V2 must NOT regress HOLD-style sentences"
# requirements in openspec/changes/enrich-evidence-keywords-v2/.


def test_v2_extracts_positive_from_sample_up_sentence() -> None:
    """V2 scenario: 'Apple reports stronger than expected iPhone demand in India' (UP)
    yields at least one positive evidence object via the V2 keyword
    'stronger than expected'."""
    result = extract_evidence(
        _make_item("Apple reports stronger than expected iPhone demand in India")
    )
    matched_keywords = {e["matched_keyword"] for e in result["evidence"]}
    assert "stronger than expected" in matched_keywords
    positives = [e for e in result["evidence"] if e["polarity"] == "positive"]
    assert positives, "expected at least one positive evidence item"
    assert result["summary"]["positive_count"] >= 1
    assert result["summary"]["negative_count"] == 0
    assert result["summary"]["has_mixed_evidence"] is False
    assert any(e["expected_direction"] == "UP" for e in result["evidence"])


def test_v2_extracts_negative_from_sample_down_sentence_antitrust() -> None:
    """V2 scenario: 'Google faces a new antitrust complaint over search distribution deals' (DOWN)
    yields at least one negative evidence object via the V2 keyword
    'antitrust complaint' (or 'faces a')."""
    result = extract_evidence(
        _make_item(
            "Google faces a new antitrust complaint over search distribution deals"
        )
    )
    matched_keywords = {e["matched_keyword"] for e in result["evidence"]}
    assert "antitrust complaint" in matched_keywords or "faces a" in matched_keywords
    negatives = [e for e in result["evidence"] if e["polarity"] == "negative"]
    assert negatives
    assert result["summary"]["negative_count"] >= 1
    assert result["summary"]["positive_count"] == 0
    assert any(e["expected_direction"] == "DOWN" for e in result["evidence"])


def test_v2_extracts_positive_faster_growth() -> None:
    """V2 scenario: 'Meta announces faster growth in Reels advertising engagement' (UP)
    yields a positive evidence object via the V2 keyword 'faster growth'."""
    result = extract_evidence(
        _make_item("Meta announces faster growth in Reels advertising engagement")
    )
    matched_keywords = {e["matched_keyword"] for e in result["evidence"]}
    assert "faster growth" in matched_keywords
    assert result["summary"]["positive_count"] >= 1
    assert any(e["expected_direction"] == "UP" for e in result["evidence"])


def test_v2_extracts_negative_multi_keyword_warns_of() -> None:
    """V2 scenario: 'Apple supplier warns of softer iPhone component orders for next quarter' (DOWN)
    yields at least one negative evidence object via either 'warns of' or
    'softer orders' (multi-keyword positive scenario for the DOWN class)."""
    result = extract_evidence(
        _make_item(
            "Apple supplier warns of softer iPhone component orders for next quarter"
        )
    )
    matched_keywords = {e["matched_keyword"] for e in result["evidence"]}
    assert "warns of" in matched_keywords or "softer orders" in matched_keywords
    negatives = [e for e in result["evidence"] if e["polarity"] == "negative"]
    assert len(negatives) >= 1
    assert any(e["expected_direction"] == "DOWN" for e in result["evidence"])


def test_v2_extracts_positive_signs_a_contract() -> None:
    """V2 scenario: 'Google Cloud signs a large AI infrastructure contract with a bank' (UP)
    yields a positive evidence object via the V2 keyword 'signs a'."""
    result = extract_evidence(
        _make_item(
            "Google Cloud signs a large AI infrastructure contract with a bank"
        )
    )
    matched_keywords = {e["matched_keyword"] for e in result["evidence"]}
    assert "signs a" in matched_keywords
    assert result["summary"]["positive_count"] >= 1
    assert any(e["expected_direction"] == "UP" for e in result["evidence"])


def test_v2_extracts_negative_is_fined() -> None:
    """V2 scenario: 'Google is fined by a regulator for data retention practices' (DOWN)
    yields a negative evidence object via the V2 keyword 'is fined'."""
    result = extract_evidence(
        _make_item("Google is fined by a regulator for data retention practices")
    )
    matched_keywords = {e["matched_keyword"] for e in result["evidence"]}
    assert "is fined" in matched_keywords
    assert result["summary"]["negative_count"] >= 1
    assert any(e["expected_direction"] == "DOWN" for e in result["evidence"])


def test_v2_hold_sentence_remains_neutral() -> None:
    """V2 must NOT regress: 'Amazon keeps full year guidance unchanged after a mixed retail update' (HOLD)
    remains a single neutral evidence object. No V2 keyword must match
    this sentence in a way that would flip it to UP/DOWN."""
    result = extract_evidence(
        _make_item(
            "Amazon keeps full year guidance unchanged after a mixed retail update"
        )
    )
    assert len(result["evidence"]) == 1
    ev = result["evidence"][0]
    assert ev["polarity"] == "neutral"
    assert ev["expected_direction"] == "HOLD"
    assert ev["support_score"] == 0.5
    assert ev["matched_keyword"] is None
    assert result["summary"]["neutral_count"] == 1
    assert result["summary"]["positive_count"] == 0
    assert result["summary"]["negative_count"] == 0


def test_v2_has_mixed_evidence_when_both_polarities_match() -> None:
    """V2 mixed flag: a synthetic sentence with both 'raises guidance' (V1 positive)
    and 'lawsuit' (V1 negative) yields summary.has_mixed_evidence = True.
    Pin the mixed-evidence contract under V2 — new keywords must not
    regress the mixed flag."""
    result = extract_evidence(
        _make_item("Google raises guidance despite lawsuit risk")
    )
    matched_keywords = {e["matched_keyword"] for e in result["evidence"]}
    assert "raises guidance" in matched_keywords
    assert "lawsuit" in matched_keywords
    assert result["summary"]["has_mixed_evidence"] is True
    assert result["summary"]["positive_count"] >= 1
    assert result["summary"]["negative_count"] >= 1
    # Primary evidence must still point to a negative item (V1 rule preserved).
    primary = next(
        e for e in result["evidence"] if e["evidence_id"] == result["primary_evidence_id"]
    )
    assert primary["polarity"] == "negative"
    assert primary["matched_keyword"] == "lawsuit"


# ---------------------------------------------------------------------------
# Version 3 keyword coverage tests (delta spec scenarios)
# ---------------------------------------------------------------------------
# V3 narrows the residual UP/DOWN sentences that V2 still classified as
# HOLD. The V3 keyword list was selected by inspecting the 27 UP-HOLD
# and 24 DOWN-HOLD sentences that V2 produced — see
# openspec/changes/enrich-evidence-keywords-v3/ for the full rationale
# and the false-positive audit table.


def test_v3_extracts_positive_from_softer_up_sentence_expands() -> None:
    """V3: 'Google expands Gemini features for enterprise productivity customers' (UP)
    yields a positive evidence object via the V3 keyword 'expands'."""
    result = extract_evidence(
        _make_item("Google expands Gemini features for enterprise productivity customers")
    )
    matched_keywords = {e["matched_keyword"] for e in result["evidence"]}
    assert "expands" in matched_keywords
    assert result["summary"]["positive_count"] >= 1
    assert any(e["expected_direction"] == "UP" for e in result["evidence"])


def test_v3_extracts_positive_from_softer_up_sentence_stronger() -> None:
    """V3: 'Meta reports stronger advertiser retention among small businesses' (UP)
    yields a positive evidence object via 'stronger' (which the V3
    extractor's token-gap also covers 'stronger advertiser retention')."""
    result = extract_evidence(
        _make_item("Meta reports stronger advertiser retention among small businesses")
    )
    matched_keywords = {e["matched_keyword"] for e in result["evidence"]}
    # V3 keyword 'stronger' matches as a single-word keyword.
    assert "stronger" in matched_keywords
    assert result["summary"]["positive_count"] >= 1
    assert any(e["expected_direction"] == "UP" for e in result["evidence"])


def test_v3_extracts_positive_improvement_program() -> None:
    """V3: 'Google announces a cloud margin improvement program' (UP)
    yields a positive evidence object via the V3 keyword 'improvement'."""
    result = extract_evidence(
        _make_item("Google announces a cloud margin improvement program")
    )
    matched_keywords = {e["matched_keyword"] for e in result["evidence"]}
    assert "improvement" in matched_keywords
    assert result["summary"]["positive_count"] >= 1


def test_v3_extracts_positive_cost_efficient() -> None:
    """V3: 'Amazon Web Services launches new cost efficient AI chips for customers' (UP)
    yields a positive evidence object via the V3 keyword 'cost efficient'."""
    result = extract_evidence(
        _make_item(
            "Amazon Web Services launches new cost efficient AI chips for customers"
        )
    )
    matched_keywords = {e["matched_keyword"] for e in result["evidence"]}
    assert "cost efficient" in matched_keywords
    assert result["summary"]["positive_count"] >= 1


def test_v3_extracts_negative_warns_short_form() -> None:
    """V3: 'Google warns that cloud capacity constraints may limit near term sales' (DOWN)
    yields a negative evidence object via the short V3 keyword 'warns'
    (V2 already has 'warns of' / 'warns that', but this sentence is also
    covered by the V3 short keyword as a defence-in-depth)."""
    result = extract_evidence(
        _make_item(
            "Google warns that cloud capacity constraints may limit near term sales"
        )
    )
    matched_keywords = {e["matched_keyword"] for e in result["evidence"]}
    # Either V2 ('warns that') or V3 ('warns') may match — the contract
    # is that the sentence is classified DOWN.
    assert matched_keywords & {"warns", "warns that"}
    assert result["summary"]["negative_count"] >= 1
    assert any(e["expected_direction"] == "DOWN" for e in result["evidence"])


def test_v3_extracts_negative_softer_shorter_form() -> None:
    """V3: 'Meta ad dashboard shows slower conversion rates for gaming advertisers' (DOWN)
    yields a negative evidence object via the short V3 keyword 'slower'."""
    result = extract_evidence(
        _make_item(
            "Meta ad dashboard shows slower conversion rates for gaming advertisers"
        )
    )
    matched_keywords = {e["matched_keyword"] for e in result["evidence"]}
    assert "slower" in matched_keywords
    assert result["summary"]["negative_count"] >= 1


def test_v3_extracts_negative_weaker_mac() -> None:
    """V3: 'Apple reports weaker Mac shipments in a supply chain channel check' (DOWN)
    yields a negative evidence object via the V3 keyword 'weaker'."""
    result = extract_evidence(
        _make_item("Apple reports weaker Mac shipments in a supply chain channel check")
    )
    matched_keywords = {e["matched_keyword"] for e in result["evidence"]}
    assert "weaker" in matched_keywords
    assert result["summary"]["negative_count"] >= 1


def test_v3_extracts_negative_permitting_issues() -> None:
    """V3: 'Google delays a planned cloud region because of permitting issues' (DOWN)
    yields a negative evidence object via the V3 keyword 'permitting'."""
    result = extract_evidence(
        _make_item(
            "Google delays a planned cloud region because of permitting issues"
        )
    )
    matched_keywords = {e["matched_keyword"] for e in result["evidence"]}
    assert "permitting" in matched_keywords
    assert result["summary"]["negative_count"] >= 1


def test_v3_extracts_negative_outage_in() -> None:
    """V3: 'Amazon reports a temporary outage in a major AWS region' (DOWN)
    yields a negative evidence object via the V3 keyword 'outage in'."""
    result = extract_evidence(
        _make_item("Amazon reports a temporary outage in a major AWS region")
    )
    matched_keywords = {e["matched_keyword"] for e in result["evidence"]}
    assert "outage in" in matched_keywords
    assert result["summary"]["negative_count"] >= 1


def test_v3_hold_sentence_still_remains_neutral() -> None:
    """V3 must NOT regress: 'Apple issues a regular security patch for iOS devices' (HOLD)
    remains a single neutral evidence object. None of the V3 short
    keywords (e.g. 'receives', 'improvement', 'launches', 'upgrade',
    'introduces', 'expands') must match a genuinely HOLD sentence."""
    result = extract_evidence(
        _make_item("Apple issues a regular security patch for iOS devices")
    )
    assert len(result["evidence"]) == 1
    ev = result["evidence"][0]
    assert ev["polarity"] == "neutral"
    assert ev["expected_direction"] == "HOLD"
    assert ev["support_score"] == 0.5
    assert ev["matched_keyword"] is None


def test_v3_hold_sentence_in_line_with_plan_still_neutral() -> None:
    """V3 must NOT regress: 'Google says Android licensing revenue remains in line with plan' (HOLD)
    must remain neutral. The V3 keyword 'receives' must NOT match this
    sentence in a way that flips it to UP."""
    result = extract_evidence(
        _make_item(
            "Google says Android licensing revenue remains in line with plan"
        )
    )
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["polarity"] == "neutral"
    assert result["summary"]["positive_count"] == 0
    assert result["summary"]["negative_count"] == 0
