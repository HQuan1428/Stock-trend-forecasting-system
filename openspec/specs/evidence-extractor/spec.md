# Evidence Extractor — Main Spec (Version 3)

This is the **main spec** for the `evidence-extractor` capability, consolidated from Version 1, Version 2, and Version 3 of the keyword dictionary. The dictionary is a **strict superset** at every step (V1 ⊂ V2 ⊂ V3).

## Purpose

The Evidence Extractor receives a single news item (a dict with `news_id`, `ticker`, `forecast_time`, `news_time`, `news_text`) and returns a structured list of evidence phrases extracted from `news_text`. The extractor is **deterministic, rule-based, and audit-friendly**: it uses a fixed keyword dictionary, case-insensitive substring matching with a token-gap fallback, longest-match-wins overlap resolution, and a neutral fallback when no keyword matches. It does not use any LLM, FinBERT, transformer, or external NLP model.

---

## Input Schema

Each input news item MUST be a JSON object (or equivalent dict) with the following fields:

| Field           | Type   | Required | Description |
|-----------------|--------|----------|-------------|
| `news_id`       | string | yes      | Stable identifier for the news item. Used to namespace evidence IDs. |
| `ticker`        | string | yes      | Stock ticker the news item is about. Preserved verbatim in the output. |
| `forecast_time` | string | yes      | Datetime string at which the forecast is made. Preserved verbatim in the output. |
| `news_time`     | string | yes      | Datetime string at which the news item was published. Preserved verbatim in the output. |
| `news_text`     | string | yes      | Raw text of the news item. Searched case-insensitively. |

The extractor MUST treat `forecast_time` and `news_time` as opaque strings and MUST NOT compare, parse, or filter on them. Temporal validity is the responsibility of the Temporal Retriever.

---

## Output Schema

For each input news item, the extractor MUST return a single result object with the following fields:

| Field                | Type    | Description |
|----------------------|---------|-------------|
| `news_id`            | string  | Same as input. |
| `ticker`             | string  | Same as input. |
| `forecast_time`      | string  | Same as input. |
| `news_time`          | string  | Same as input. |
| `evidence`           | list    | List of evidence objects (see below). Never empty. |
| `summary`            | object  | Counts and mixed-evidence flag (see below). |
| `extraction_method`  | string  | MUST be the literal `"rule_based_keyword"`. |
| `primary_evidence_id`| string  | ID of the chosen primary evidence. See *Primary Evidence Rule*. |

### Evidence Object

| Field               | Type    | Description |
|---------------------|---------|-------------|
| `evidence_id`       | string  | Deterministic ID in the form `<news_id>_E<index>` where `<index>` is the 1-based position of the evidence in the final text-ordered list, zero-padded to 3 digits (e.g. `E001`, `E002`, …, `E042`). The padding width is fixed for V1. |
| `news_id`           | string  | Same as input. |
| `evidence_text`     | string  | The matched phrase (lower-cased) or a short surrounding phrase if the implementation chooses to expand the slice. |
| `polarity`          | string  | One of `"positive"`, `"negative"`, `"neutral"`. |
| `expected_direction`| string  | One of `"UP"`, `"DOWN"`, `"HOLD"`. |
| `matched_keyword`   | string \| null | The dictionary keyword that produced this evidence, or `null` for the neutral fallback. |
| `start_char`        | integer | Inclusive 0-based start offset into the original `news_text`. |
| `end_char`          | integer | Exclusive 0-based end offset into the original `news_text`. |
| `support_score`     | number  | `1.0` for keyword matches, `0.5` for the neutral fallback. |

`start_char` and `end_char` MUST be valid offsets into the **original** `news_text` (not a lowercased copy) such that `news_text[start_char:end_char].lower() == evidence_text`.

### Summary Object

| Field                  | Type    | Description |
|------------------------|---------|-------------|
| `positive_count`       | integer | Count of evidence items with `polarity = "positive"`. |
| `negative_count`       | integer | Count of evidence items with `polarity = "negative"`. |
| `neutral_count`        | integer | Count of evidence items with `polarity = "neutral"`. |
| `total_evidence_count` | integer | Sum of the three counts above. |
| `has_mixed_evidence`   | boolean | `true` if both `positive_count >= 1` and `negative_count >= 1`; otherwise `false`. |

---

## Keyword Dictionary (Version 3)

The Version 3 keyword set is a strict superset of Version 2, which is a strict superset of Version 1. The dictionary is fixed and auditable as a module-level constant.

**Positive keywords (polarity = `positive`, expected direction = `UP`)** — V1 entries are listed first, V2 additions follow, V3 additions are appended last:

- V1 (retained): `beats expectations`, `record profit`, `strong sales`, `raises guidance`, `launches new product`
- V2 (retained): `stronger than expected`, `faster growth`, `positive analyst`, `wins a`, `signs a`, `accelerate`, `record level`, `raises shipment outlook`
- V3 additions: `launches`, `expands`, `improvement`, `stronger`, `secures`, `receives`, `praise`, `preorders`, `cost efficient`, `backlog expands`, `advertiser retention`, `adoption`, `introduces`, `accelerated`, `better conversion`, `carrier partnership`, `upgrade`, `automation`, `advertising marketplace`, `supply agreement`, `demand from`

**Negative keywords (polarity = `negative`, expected direction = `DOWN`)** — V1 entries are listed first, V2 additions follow, V3 additions are appended last:

- V1 (retained): `misses expectations`, `weak sales`, `recall`, `lawsuit`, `cuts guidance`, `decline`
- V2 (retained): `antitrust complaint`, `softer orders`, `slower growth`, `warns of`, `warns that`, `faces a`, `is fined`, `fined for`, `delays production`, `lowers outlook`, `outage`, `probe into`, `regulatory costs`, `downgraded`, `vote to authorize a strike`, `complaint`, `delays`, `cuts the price`, `budget cuts`, `complain about`, `losses widen`, `loses an appeal`, `overheating`, `lowers revenue guidance`
- V3 additions: `warns`, `slower`, `softer`, `weaker`, `lower`, `reduced`, `reduces`, `class action`, `criticism`, `pauses`, `delivery delays`, `fresh lawsuit`, `outage in`, `permitting`, `delays a planned`, `downgrade`

**Neutral fallback** — unchanged: when no positive or negative keyword matches, the extractor MUST emit exactly one evidence object with `polarity = "neutral"`, `expected_direction = "HOLD"`, `support_score = 0.5`, `matched_keyword = null`.

---

## Polarity-to-Direction Mapping

| Polarity     | `expected_direction` |
|--------------|----------------------|
| `positive`   | `UP`                 |
| `negative`   | `DOWN`               |
| `neutral`    | `HOLD`               |

---

## Primary Evidence Rule

If `primary_evidence_id` is emitted, the extractor MUST apply the following deterministic rule:

1. Prefer evidence with `polarity = "negative"`.
2. If none, prefer `polarity = "positive"`.
3. If still tied, prefer `polarity = "neutral"`.
4. If multiple evidence items share the chosen polarity, choose the one with the smallest `start_char` (earliest in the text).

This rule selects a single reference only. It MUST NOT alter the full `evidence` list.

---

## Requirements

### Requirement: Case-insensitive keyword matching
The system SHALL search `news_text` case-insensitively for every Version 3 keyword.

#### Scenario: All-uppercase input
- **GIVEN** an input news item with `news_text = "Microsoft MISSES EXPECTATIONS in cloud revenue"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains an evidence object with `matched_keyword = "misses expectations"`, `polarity = "negative"`, and `expected_direction = "DOWN"`

### Requirement: All positive and negative matches are preserved
The system SHALL return every non-overlapping positive and negative keyword occurrence in `news_text`. The system MUST NOT drop a positive match because a negative match exists, and MUST NOT drop a negative match because a positive match exists.

#### Scenario: Mixed positive and negative
- **GIVEN** an input news item with `news_text = "Google raises guidance despite lawsuit risk"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result's `evidence` list contains at least one positive evidence for `"raises guidance"` AND at least one negative evidence for `"lawsuit"`
- **AND** `summary.has_mixed_evidence` is `true`

### Requirement: Text order and overlap handling
The system SHALL return evidence in ascending `start_char` order. When the same keyword appears multiple times at non-overlapping positions, the system SHALL return each occurrence. When matches overlap, the system SHALL keep the longest match and break ties by earliest start.

### Requirement: Neutral fallback when no keyword matches
The system SHALL return exactly one neutral evidence object when no positive or negative keyword matches.

#### Scenario: News with no sentiment keyword
- **GIVEN** an input news item with `news_text = "Meta holds annual developer conference"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result's `evidence` list contains exactly one object
- **AND** that object has `polarity = "neutral"`, `expected_direction = "HOLD"`, `support_score = 0.5`, and `matched_keyword = null`

### Requirement: Polarity, direction, and support score mapping
The system SHALL map polarity to `expected_direction` according to the polarity-to-direction table and SHALL set `support_score` to `1.0` for keyword matches and `0.5` for the neutral fallback.

### Requirement: Preserve `forecast_time` and `news_time`
The system SHALL copy `forecast_time` and `news_time` from the input news item into the result object unchanged.

### Requirement: Batch processing returns one result per input
The system SHALL provide `EvidenceExtractor.extract_batch(news_items)` that returns a list of result objects with the same length and order as the input list, one per input news item.

### Requirement: No temporal filtering, no prediction, no advice
The system SHALL NOT filter or classify news items based on time, SHALL NOT produce a final prediction, and SHALL NOT generate trading or buy/sell advice.

### Requirement: Deterministic evidence IDs and primary evidence
The system SHALL assign each evidence object a deterministic `evidence_id` of the form `<news_id>_E<index>` where `<index>` is the 1-based position in the final text-ordered list, zero-padded to 3 digits. The system SHALL set `primary_evidence_id` according to the Primary Evidence Rule.

### Requirement: V2 keyword coverage on the project sample
The system SHALL emit at least one positive/negative evidence object (i.e. NOT the neutral fallback) for any sample sentence that obviously conveys direction.

#### Scenario: UP sentence "stronger than expected"
- **GIVEN** an input news item with `news_text = "Apple reports stronger than expected iPhone demand in India"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains at least one positive evidence object with `expected_direction = "UP"`

#### Scenario: DOWN sentence "antitrust complaint"
- **GIVEN** an input news item with `news_text = "Google faces a new antitrust complaint over search distribution deals"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains at least one negative evidence object with `expected_direction = "DOWN"`

#### Scenario: DOWN sentence "warns of softer … orders"
- **GIVEN** an input news item with `news_text = "Apple supplier warns of softer iPhone component orders for next quarter"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains at least one negative evidence object (matched via either `warns of` or `softer orders`) with `expected_direction = "DOWN"`

### Requirement: V2 must NOT regress HOLD-style sentences
The system MUST continue to return the neutral fallback for genuinely directionless sentences. Adding V2 keywords SHALL NOT cause previously-neutral sentences to become falsely directional.

#### Scenario: HOLD sentence with "guidance" but no V1/V2 directional anchor
- **GIVEN** an input news item with `news_text = "Amazon keeps full year guidance unchanged after a mixed retail update"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains exactly one evidence object with `polarity = "neutral"`, `expected_direction = "HOLD"`, `support_score = 0.5`, and `matched_keyword = null`

### Requirement: V3 keyword coverage on the project sample
The system SHALL emit at least one positive/negative evidence object (i.e. NOT the neutral fallback) for the V3 sample sentences enumerated in the four normative scenarios below.

#### Scenario: UP sentence "expands … features"
- **GIVEN** an input news item with `news_text = "Google expands Gemini features for enterprise productivity customers"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains at least one positive evidence object with `expected_direction = "UP"`

#### Scenario: UP sentence "stronger advertiser retention"
- **GIVEN** an input news item with `news_text = "Meta reports stronger advertiser retention among small businesses"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains at least one positive evidence object via the V3 keyword `stronger` with `expected_direction = "UP"`

#### Scenario: DOWN sentence "weaker Mac shipments"
- **GIVEN** an input news item with `news_text = "Apple reports weaker Mac shipments in a supply chain channel check"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains at least one negative evidence object via the V3 keyword `weaker` with `expected_direction = "DOWN"`

#### Scenario: DOWN sentence "permitting issues"
- **GIVEN** an input news item with `news_text = "Google delays a planned cloud region because of permitting issues"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains at least one negative evidence object via the V3 keyword `permitting` with `expected_direction = "DOWN"`

### Requirement: V3 must NOT regress HOLD-style sentences
The system MUST continue to return the neutral fallback for genuinely directionless sentences that contain the substring of a V3 short keyword but where the surrounding context is neutral.

#### Scenario: HOLD sentence with "regular security patch" (no V3 match)
- **GIVEN** an input news item with `news_text = "Apple issues a regular security patch for iOS devices"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains exactly one evidence object with `polarity = "neutral"`, `expected_direction = "HOLD"`, `support_score = 0.5`, and `matched_keyword = null`

#### Scenario: HOLD sentence with "in line with plan"
- **GIVEN** an input news item with `news_text = "Google says Android licensing revenue remains in line with plan"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains exactly one evidence object with `polarity = "neutral"`, `expected_direction = "HOLD"`, `support_score = 0.5`, and `matched_keyword = null`

---

## Acceptance Criteria

The following acceptance criteria are normative. Each criterion MUST be verified by a unit test in the implementation phase.

1. **Negative-only news.** Given `news_text = "Apple reports weak iPhone sales in China"`, the result contains at least one evidence item with `evidence_text` containing `"weak iPhone sales"` or `"weak sales"`, `polarity = "negative"`, and `expected_direction = "DOWN"`.
2. **Positive-only news.** Given `news_text = "Amazon beats expectations after strong sales in cloud services"`, the result contains positive evidence items with `polarity = "positive"`, `expected_direction = "UP"`, and `summary.positive_count >= 1`.
3. **Neutral news.** Given `news_text = "Meta holds annual developer conference"`, the result contains exactly one neutral evidence item with `polarity = "neutral"`, `expected_direction = "HOLD"`, `support_score = 0.5`, and `matched_keyword = null`.
4. **Mixed news.** Given `news_text = "Google raises guidance despite lawsuit risk"`, the result contains one positive evidence for `"raises guidance"` and one negative evidence for `"lawsuit"`, `summary.has_mixed_evidence = true`, and `primary_evidence_id` (if emitted) points to the negative evidence.
5. **Case-insensitive matching.** Given `news_text = "Microsoft MISSES EXPECTATIONS in cloud revenue"`, the result contains an evidence item with `matched_keyword = "misses expectations"`, `polarity = "negative"`, and `expected_direction = "DOWN"`.
6. **Batch processing.** Given a list of input news items, the extractor returns one result object per input news item, in the same order.
7. **Datetime preservation.** The result preserves `forecast_time` and `news_time` from input to output exactly.
8. **No temporal filtering.** The extractor does not remove or classify future news. Temporal validity is left to the Temporal Retriever.
9. **V2 coverage.** Given a sample sentence whose direction is unambiguous, the result MUST contain at least one positive or negative evidence object whose `expected_direction` matches the label direction.
10. **V3 coverage.** Given a V3 sample sentence whose direction is unambiguous (any of the V3 coverage scenarios), the result MUST contain at least one positive or negative evidence object whose `expected_direction` matches the label direction.
11. **V3 no-regression on HOLD.** Given a HOLD sample sentence that contains the substring of a V3 short keyword in a non-directional context, the result MUST remain a single neutral evidence object.

---

## Edge Cases

- **Empty `news_text`.** The extractor MUST return one neutral evidence object.
- **Whitespace-only `news_text`.** The extractor MUST return one neutral evidence object.
- **Unicode normalization.** The extractor SHALL treat `news_text` as a plain Python string; it does not perform Unicode normalization in V1.
- **Extremely long `news_text`.** The extractor SHALL still produce a result; it does not impose a length cap in V1.
- **Non-overlapping duplicate keyword** (e.g. `"A lawsuit was filed. The lawsuit claims..."`): each occurrence is matched separately and the two evidence objects appear in `start_char` order.
- **Keyword as a substring of a longer non-keyword phrase** (e.g. `"decline"` inside `"price decline continued"`): V1 returns the keyword match. Whole-word boundaries are out of scope and are a known limitation.

---

## Out of Scope

The following are explicitly **out of scope** and MUST NOT be implemented:

- LLM-based extraction (no prompt engineering, no generative models).
- FinBERT or any transformer-based sentiment model.
- Named entity recognition (NER), dependency parsing, part-of-speech tagging.
- Multi-sentence rationale generation or natural-language explanation.
- Final forecast prediction, price prediction, or movement direction.
- Temporal filtering or temporal validity checks (owned by the Temporal Retriever).
- Trading advice, buy/sell recommendations, or any portfolio action.
- Real stock buy/sell recommendation or any form of investment guidance.
- Learned scoring, calibrated confidence, or per-keyword weights beyond the binary `support_score`.
- Whole-word boundary enforcement, lemmatization, or stemming.
- Multi-language support.
- **Negation handling** (e.g. "did not raise guidance") — out of scope; whole-word boundaries are still out of scope.
- **Sentiment polarity inversion** for `not + positive` or `fails to + positive` — out of scope; the dictionary is a fixed polarity mapping only.