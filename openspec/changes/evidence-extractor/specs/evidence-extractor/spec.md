# Evidence Extractor — Spec (Version 1)

This spec defines the behavior of the **Evidence Extractor** module in the Faithful Evidence-Centric Financial News Forecasting pipeline. The Evidence Extractor receives validated news items from the Temporal Retriever and produces a structured list of evidence phrases per news item, preserving all matched positive and negative evidence and falling back to a single neutral evidence when no keyword matches.

Version 1 is **rule-based, deterministic, and testable**. It does not use any LLM, FinBERT, transformer, or external NLP model.

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
| `primary_evidence_id`| string  | ID of the chosen primary evidence. See *Primary Evidence Rule*. The field is present whenever the result is produced; implementations MAY omit it as a whole (treating it as optional at the schema level) but the Version 1 implementation always emits it. |

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

`start_char` and `end_char` MUST be valid offsets into the **original** `news_text` (not a lowercased copy) such that `news_text[start_char:end_char].lower() == evidence_text`. The offsets are computed against the original text but are equal to offsets into a same-length lowercased copy; the spec is written against the original to keep audit traces stable.

### Summary Object

| Field                  | Type    | Description |
|------------------------|---------|-------------|
| `positive_count`       | integer | Count of evidence items with `polarity = "positive"`. |
| `negative_count`       | integer | Count of evidence items with `polarity = "negative"`. |
| `neutral_count`        | integer | Count of evidence items with `polarity = "neutral"`. |
| `total_evidence_count` | integer | Sum of the three counts above. |
| `has_mixed_evidence`   | boolean | `true` if both `positive_count >= 1` and `negative_count >= 1`; otherwise `false`. |

---

## Keyword Dictionary (Version 1)

The Version 1 keyword set is fixed and auditable.

**Positive keywords (polarity = `positive`, expected direction = `UP`):**

- `beats expectations`
- `record profit`
- `strong sales`
- `raises guidance`
- `launches new product`

**Negative keywords (polarity = `negative`, expected direction = `DOWN`):**

- `misses expectations`
- `weak sales`
- `recall`
- `lawsuit`
- `cuts guidance`
- `decline`

**Neutral fallback:**

- When no positive or negative keyword matches, the extractor MUST emit exactly one evidence object with `polarity = "neutral"`, `expected_direction = "HOLD"`, `support_score = 0.5`, and `matched_keyword = null`.

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

## ADDED Requirements

### Requirement: Case-insensitive keyword matching

The system SHALL search `news_text` case-insensitively for every Version 1 keyword.

#### Scenario: All-uppercase input
- **GIVEN** an input news item with `news_text = "Microsoft MISSES EXPECTATIONS in cloud revenue"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains an evidence object with `matched_keyword = "misses expectations"`, `polarity = "negative"`, and `expected_direction = "DOWN"`

#### Scenario: Mixed case input
- **GIVEN** an input news item with `news_text = "Amazon BEATS Expectations After Strong Sales"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains positive evidence objects for `beats expectations` and `strong sales` with `polarity = "positive"` and `expected_direction = "UP"`

---

### Requirement: All positive and negative matches are preserved

The system SHALL return every non-overlapping positive and negative keyword occurrence in `news_text`. The system MUST NOT drop a positive match because a negative match exists, and MUST NOT drop a negative match because a positive match exists.

#### Scenario: Mixed positive and negative
- **GIVEN** an input news item with `news_text = "Google raises guidance despite lawsuit risk"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result's `evidence` list contains at least one positive evidence for `"raises guidance"` AND at least one negative evidence for `"lawsuit"`
- **AND** `summary.has_mixed_evidence` is `true`
- **AND** `summary.positive_count >= 1` and `summary.negative_count >= 1`

#### Scenario: Multiple distinct positive matches
- **GIVEN** an input news item with `news_text = "Amazon beats expectations after strong sales in cloud services"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains exactly two positive evidence items, one with `matched_keyword = "beats expectations"` and one with `matched_keyword = "strong sales"`
- **AND** `summary.positive_count = 2`
- **AND** the two evidence objects appear in `evidence` in ascending `start_char` order

---

### Requirement: Text order and overlap handling

The system SHALL return evidence in ascending `start_char` order. When the same keyword appears multiple times at non-overlapping positions, the system SHALL return each occurrence. When matches overlap, the system SHALL keep the longest match and break ties by earliest start.

#### Scenario: Non-overlapping duplicate keyword
- **GIVEN** an input news item with `news_text = "A lawsuit was filed. The lawsuit claims..."`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains two negative evidence objects, both with `matched_keyword = "lawsuit"`, ordered by `start_char` ascending

#### Scenario: Overlapping matches are resolved to the longest
- **GIVEN** an input news item with `news_text` that produces overlapping candidate matches
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains only the longest match for that region
- **AND** no shorter overlapping match is included

---

### Requirement: Neutral fallback when no keyword matches

The system SHALL return exactly one neutral evidence object when no positive or negative keyword matches.

#### Scenario: News with no sentiment keyword
- **GIVEN** an input news item with `news_text = "Meta holds annual developer conference"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result's `evidence` list contains exactly one object
- **AND** that object has `polarity = "neutral"`, `expected_direction = "HOLD"`, `support_score = 0.5`, and `matched_keyword = null`
- **AND** `summary.neutral_count = 1` and `summary.positive_count = 0` and `summary.negative_count = 0`

#### Scenario: Empty news_text
- **GIVEN** an input news item with `news_text = ""`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result's `evidence` list contains exactly one neutral evidence object

---

### Requirement: Polarity, direction, and support score mapping

The system SHALL map polarity to `expected_direction` according to the polarity-to-direction table and SHALL set `support_score` to `1.0` for keyword matches and `0.5` for the neutral fallback.

#### Scenario: Negative keyword support score
- **GIVEN** an evidence item is produced by a negative keyword match
- **WHEN** the result is read
- **THEN** its `support_score` is `1.0`

#### Scenario: Neutral support score
- **GIVEN** the only evidence is the neutral fallback
- **WHEN** the result is read
- **THEN** its `support_score` is `0.5`

#### Scenario: Direction mapping for positive keyword
- **GIVEN** an evidence item is produced by a positive keyword match
- **WHEN** the result is read
- **THEN** its `expected_direction` is `"UP"`

---

### Requirement: Preserve `forecast_time` and `news_time`

The system SHALL copy `forecast_time` and `news_time` from the input news item into the result object unchanged.

#### Scenario: Datetime fields preserved
- **GIVEN** an input with `forecast_time = "2025-03-12 09:00"` and `news_time = "2025-03-11 15:30"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result's `forecast_time` equals `"2025-03-12 09:00"` exactly
- **AND** the result's `news_time` equals `"2025-03-11 15:30"` exactly

---

### Requirement: Batch processing returns one result per input

The system SHALL provide `EvidenceExtractor.extract_batch(news_items)` that returns a list of result objects with the same length and order as the input list, one per input news item.

#### Scenario: Batch of three items
- **GIVEN** an input list of three news items
- **WHEN** `EvidenceExtractor.extract_batch` is called
- **THEN** the output is a list of three result objects in the same order as the input
- **AND** each result object has the same `news_id` as the corresponding input item

---

### Requirement: No temporal filtering, no prediction, no advice

The system SHALL NOT filter or classify news items based on time, SHALL NOT produce a final prediction, and SHALL NOT generate trading or buy/sell advice.

#### Scenario: Future news is preserved
- **GIVEN** an input news item with `news_time > forecast_time`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result is still produced (no exception, no rejection, no filter)
- **AND** both timestamps are preserved verbatim in the output

---

### Requirement: Deterministic evidence IDs and primary evidence

The system SHALL assign each evidence object a deterministic `evidence_id` of the form `<news_id>_E<index>` where `<index>` is the 1-based position in the final text-ordered list, zero-padded to 3 digits (e.g. `E001`, `E002`). The system SHALL set `primary_evidence_id` according to the Primary Evidence Rule, and the rule MUST NOT alter the full evidence list.

#### Scenario: Evidence IDs are zero-padded and in order
- **GIVEN** a news item with `news_id = "N042"` that produces two evidence objects in text order
- **WHEN** the result is read
- **THEN** the first evidence object has `evidence_id = "N042_E001"`
- **AND** the second evidence object has `evidence_id = "N042_E002"`

#### Scenario: Primary evidence prefers negative
- **GIVEN** a news item that produces at least one positive and one negative evidence object
- **WHEN** the result is read
- **THEN** `primary_evidence_id` points to a negative evidence object
- **AND** the full `evidence` list is unchanged (both positive and negative evidence remain)

#### Scenario: Primary evidence tie-break by earliest start
- **GIVEN** a news item that produces two negative evidence objects and no positive or neutral evidence
- **WHEN** the result is read
- **THEN** `primary_evidence_id` points to the negative evidence object with the smaller `start_char`

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

---

## Edge Cases

- **Empty `news_text`.** The extractor MUST return one neutral evidence object.
- **Whitespace-only `news_text`.** The extractor MUST return one neutral evidence object.
- **Unicode normalization.** The extractor SHALL treat `news_text` as a plain Python string; it does not perform Unicode normalization in V1.
- **Extremely long `news_text`.** The extractor SHALL still produce a result; it does not impose a length cap in V1.
- **Non-overlapping duplicate keyword** (e.g. `"A lawsuit was filed. The lawsuit claims..."`): each occurrence is matched separately and the two evidence objects appear in `start_char` order.
- **Keyword as a substring of a longer non-keyword phrase** (e.g. `"decline"` inside `"price decline continued"`): V1 returns the keyword match. Whole-word boundaries are out of scope for V1 and are a known limitation.

---

## Documented Examples

The following examples illustrate the expected behavior. They are normative for shape and field values, not for implementation language.

### Example 1 — Positive-only news

**Input:**
```json
{
  "news_id": "N010",
  "ticker": "AMZN",
  "forecast_time": "2025-04-02 09:00",
  "news_time":     "2025-04-01 16:00",
  "news_text": "Amazon beats expectations after strong sales in cloud services"
}
```

**Expected behavior:** Two positive evidence items (`beats expectations`, `strong sales`); `summary.positive_count = 2`, `summary.negative_count = 0`, `summary.has_mixed_evidence = false`; `extraction_method = "rule_based_keyword"`.

---

### Example 2 — Negative-only news

**Input:**
```json
{
  "news_id": "N011",
  "ticker": "AAPL",
  "forecast_time": "2025-04-02 09:00",
  "news_time":     "2025-04-01 16:00",
  "news_text": "Apple reports weak iPhone sales in China"
}
```

**Expected behavior:** At least one negative evidence item with `evidence_text` containing `"weak iPhone sales"` or `"weak sales"`; `polarity = "negative"`, `expected_direction = "DOWN"`, `support_score = 1.0`.

---

### Example 3 — Neutral news

**Input:**
```json
{
  "news_id": "N012",
  "ticker": "META",
  "forecast_time": "2025-04-02 09:00",
  "news_time":     "2025-04-01 16:00",
  "news_text": "Meta holds annual developer conference"
}
```

**Expected behavior:** Exactly one evidence object: `polarity = "neutral"`, `expected_direction = "HOLD"`, `support_score = 0.5`, `matched_keyword = null`; `summary.neutral_count = 1`.

---

### Example 4 — Mixed positive and negative news

**Input:**
```json
{
  "news_id": "N001",
  "ticker": "GOOGL",
  "forecast_time": "2025-03-12 09:00",
  "news_time":     "2025-03-11 15:30",
  "news_text": "Google raises guidance despite lawsuit risk"
}
```

**Expected output (shape):**
```json
{
  "news_id": "N001",
  "ticker": "GOOGL",
  "forecast_time": "2025-03-12 09:00",
  "news_time": "2025-03-11 15:30",
  "evidence": [
    {
      "evidence_id": "N001_E001",
      "news_id": "N001",
      "evidence_text": "raises guidance",
      "polarity": "positive",
      "expected_direction": "UP",
      "matched_keyword": "raises guidance",
      "start_char": 7,
      "end_char": 22,
      "support_score": 1.0
    },
    {
      "evidence_id": "N001_E002",
      "news_id": "N001",
      "evidence_text": "lawsuit",
      "polarity": "negative",
      "expected_direction": "DOWN",
      "matched_keyword": "lawsuit",
      "start_char": 31,
      "end_char": 38,
      "support_score": 1.0
    }
  ],
  "primary_evidence_id": "N001_E002",
  "summary": {
    "positive_count": 1,
    "negative_count": 1,
    "neutral_count": 0,
    "total_evidence_count": 2,
    "has_mixed_evidence": true
  },
  "extraction_method": "rule_based_keyword"
}
```

---

### Example 5 — Case-insensitive matching

**Input:**
```json
{
  "news_id": "N020",
  "ticker": "MSFT",
  "forecast_time": "2025-04-02 09:00",
  "news_time":     "2025-04-01 16:00",
  "news_text": "Microsoft MISSES EXPECTATIONS in cloud revenue"
}
```

**Expected behavior:** At least one evidence object with `matched_keyword = "misses expectations"`, `polarity = "negative"`, `expected_direction = "DOWN"`, `support_score = 1.0`. The original casing of `news_text` is preserved in the output, but the match is performed on a lowercased copy.

---

## Test Scenarios

The implementation MUST ship with unit tests covering at least the following:

1. Positive-only news (acceptance criterion 2).
2. Negative-only news (acceptance criterion 1).
3. Neutral news (acceptance criterion 3).
4. Mixed positive/negative news (acceptance criterion 4) — verify `has_mixed_evidence` and `primary_evidence_id`.
5. Case-insensitive matching (acceptance criterion 5).
6. Multiple occurrences of the same non-overlapping keyword — verify count and order.
7. Overlapping matches — verify longest-match-wins.
8. Empty `news_text` — verify neutral fallback.
9. Whitespace-only `news_text` — verify neutral fallback.
10. Batch input — verify one result per input, in order.
11. Datetime preservation — verify `forecast_time` and `news_time` are copied verbatim.
12. Future news (acceptance criterion 8) — verify the result is produced without error and timestamps are preserved.
13. Determinism — running the extractor twice on the same input produces identical output, including `evidence_id` and `primary_evidence_id`.
14. `evidence_id` format is `<news_id>_E<index>` zero-padded to 3 digits, and the indices are assigned in text order.
15. Primary-evidence tie-break — when multiple negative evidence items exist, `primary_evidence_id` points to the one with the smallest `start_char`.

---

## Out of Scope (Version 1)

The following are explicitly **out of scope** for Version 1 and MUST NOT be implemented:

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
