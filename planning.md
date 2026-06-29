# Provenance Guard — Planning

## Architecture

```
                        ┌─────────────────────────────────────┐
                        │           Flask Application          │
                        │                                      │
         POST /submit   │  ┌──────────┐   ┌─────────────────┐ │
         ──────────────►│  │ Rate     │──►│  Submit Route   │ │
                        │  │ Limiter  │   │  (routes/       │ │
         POST /appeal   │  │(Flask-   │   │   submit.py)    │ │
         ──────────────►│  │Limiter)  │   └────────┬────────┘ │
                        │  └──────────┘            │          │
         GET  /log      │                           ▼          │
         ──────────────►│  ┌──────────────────────────────┐   │
                        │  │   Detection Pipeline         │   │
                        │  │   (detection/pipeline.py)    │   │
                        │  │                              │   │
                        │  │  ┌──────────┐ ┌──────────┐  │   │
                        │  │  │  Groq    │ │Stylometic│  │   │
                        │  │  │  LLM     │ │Heuristics│  │   │
                        │  │  │ (0.50w)  │ │  (0.30w) │  │   │
                        │  │  └──────────┘ └──────────┘  │   │
                        │  │       ┌──────────────┐       │   │
                        │  │       │   Entropy /  │       │   │
                        │  │       │   N-gram     │       │   │
                        │  │       │   (0.20w)    │       │   │
                        │  │       └──────────────┘       │   │
                        │  │                              │   │
                        │  │  Confidence-weighted avg     │   │
                        │  │  + Asymmetric FP penalty     │   │
                        │  └──────────────┬───────────────┘   │
                        │                 │                    │
                        │                 ▼                    │
                        │  ┌──────────────────────────────┐   │
                        │  │   Audit DB (SQLite)          │   │
                        │  │   - submissions table        │   │
                        │  │   - appeals table            │   │
                        │  │   - certificates table       │   │
                        │  └──────────────────────────────┘   │
                        └─────────────────────────────────────┘
```

## Signals

### Signal 1: Groq LLM (`detection/groq_signal.py`)
- **What it captures:** Semantic and structural patterns that are hard to fake — reasoning style, factual hedging, characteristic AI discourse ("delve", "it's worth noting", averaged tone)
- **Why chosen:** The LLM has seen millions of AI-generated samples during training and can identify global coherence patterns that surface heuristics miss
- **Weight:** 0.50 (highest — most reliable, captures what humans actually notice)
- **Confidence:** Scales with how extreme the score is (confident when score is far from 0.5)

### Signal 2: Stylometric Heuristics (`detection/stylometric.py`)
- **What it captures:** Surface-level writing statistics — sentence length burstiness, type-token ratio, AI marker phrases ("furthermore", "underscore", "tapestry"), punctuation patterns
- **Why chosen:** Purely local, no API cost, captures measurable differences in writing mechanics. Human writing has higher variance; AI writing is more "averaged"
- **Weight:** 0.30
- **Sub-scores:** burstiness (0.35), markers (0.30), type-token ratio (0.20), punctuation (0.15)
- **Confidence:** Scales with word count (more reliable on longer texts)

### Signal 3: Entropy / N-gram (`detection/entropy_signal.py`) — Ensemble stretch
- **What it captures:** Predictability of word sequences — Shannon entropy of bigrams, trigram repetition rate, lexical dominance of top-N words
- **Why chosen:** Orthogonal to stylometric (which is about surface form) — this captures distributional properties of the vocabulary. AI text tends toward lower bigram entropy
- **Weight:** 0.20
- **Confidence:** Scales with word count, lower ceiling (0.85 max) due to noisier signal

## Confidence Scoring Design

The confidence score is **not** just the raw ensemble probability. It has two components:

1. **Score extremity:** `|score - 0.5| × 2` — how far from uncertain is the prediction?
2. **Signal agreement:** `1 - variance(ai_probs) × 4` — do all three signals agree?

`confidence = 0.6 × extremity + 0.4 × agreement`

This means a 0.95 AI probability produces a very different confidence than 0.55, even if both would naively label as "AI" without uncertainty awareness.

### Asymmetric False-Positive Penalty

Calling a human's work AI-generated is worse than a false negative (missing AI content). To reflect this:

- When the raw ensemble score is in the uncertain zone (0.35–0.85), we apply a dampening factor: `corrected = 0.5 + (raw - 0.5) × 0.88`
- This means a raw score of 0.85 becomes ~0.83, making it harder to reach the AI_THRESHOLD of 0.80

### Thresholds
| Score | Label |
|-------|-------|
| ≥ 0.80 | high-confidence AI |
| ≤ 0.20 | high-confidence human |
| 0.21–0.79 | uncertain |

## Rate Limiting

| Endpoint | Limit | Reasoning |
|----------|-------|-----------|
| POST /submit | 10/min, 100/day | Each request calls Groq API (cost + abuse vector). A creator realistically submits 1-3 pieces per session. 10/min covers batch testing; adversary flooding would need thousands of requests to gain anything. |
| POST /appeal | 5/min, 50/day | Appeals are manual actions. 5/min prevents scripted bulk filing. |
| All others | 50/hr, 200/day | Read-only endpoints; generous limits for dashboard/monitoring use. |

## Transparency Labels

### High-Confidence AI (score ≥ 0.80)
> "AI-Generated Content — Our system found strong indicators that this content was generated by an AI writing tool (N% AI probability, N% system confidence). Multiple independent signals — including writing structure, vocabulary patterns, and semantic style — all pointed in the same direction. If you believe this is incorrect, the creator can submit an appeal."

### High-Confidence Human (score ≤ 0.20)
> "Human-Written Content — Our analysis found strong indicators of original human authorship (N% human probability, N% system confidence). The writing shows the kind of natural variation, personal voice, and idiosyncratic style that distinguishes human work."

### Uncertain (0.21–0.79)
> "Authorship Uncertain — Our system is uncertain about the origin of this content (AI probability: N%, system confidence: N%). The writing shows a mix of patterns that our analysis cannot reliably attribute to either AI or human authorship alone. This is not a verdict — it reflects the limits of automated detection. Creators can provide additional context through our appeals process."

## Appeal Handling

Appeals are captured but not automatically re-classified. This is by design — AI detection is an unsolved problem, and automated re-classification would just run the same imperfect pipeline again. The workflow:

1. Creator POSTs to `/appeal` with `submission_id` and `creator_reasoning`
2. System logs the appeal with timestamp alongside the original decision
3. Submission status updates to `"under_review"`
4. A human reviewer examines the content and reasoning (out of scope for this system)

## Anticipated Edge Cases

### 1. Poetry with repetition and simple vocabulary
A haiku or minimalist poem ("Rain falls. / I wait. / Nothing.") will have very low type-token ratio and high sentence-length uniformity — the same features that indicate AI. Stylometric and entropy signals will score it as AI-generated even though the terseness is a deliberate human aesthetic choice. The Groq LLM signal is more likely to recognize the genre, but may still be uncertain. **Mitigation:** the uncertain zone (0.21–0.79) is wide; such content should land there rather than getting an AI label. If it doesn't, the creator has a clear appeal path.

### 2. Human-edited AI drafts
A writer who uses AI for a first draft and then substantially rewrites it produces text that mixes AI structure (formulaic paragraph openings) with human touches (personal anecdotes, irregular punctuation). Both the LLM signal and heuristics will disagree, producing high signal variance and low confidence. The system will correctly label this "uncertain" — but neither label (AI nor human) is fully accurate, and there is no clean answer.

### 3. Non-native English speakers
Writers whose native language is not English often use more formal connectives ("Furthermore", "In addition") and more uniform sentence lengths — the exact patterns our heuristics flag as AI. A non-native speaker writing earnestly will be unfairly pushed toward the AI side of the score. **Mitigation:** asymmetric false-positive penalty + wide uncertain zone + appeals workflow.

### 4. Very short content (< 100 words)
Most statistical signals become unreliable with fewer than 100 words. A short tweet-length post gives the stylometric and entropy signals almost no data to work with. Both return low confidence, so the ensemble automatically downgrades toward uncertain. Short content almost never receives a high-confidence label.

## AI Tool Plan

### M3 — Submission endpoint + first signal
- **Spec sections provided:** Detection signals section + Architecture diagram
- **Requested output:** Flask app skeleton with `POST /submit` route stub + Groq LLM signal function (`groq_signal.py`)
- **Verification:** Call `groq_signal.analyze()` directly on 3 test inputs (clearly AI text, clearly human text, ambiguous text). Confirm the returned `ai_probability` values are directionally correct before wiring into the endpoint.

### M4 — Second signal + confidence scoring
- **Spec sections provided:** Detection signals section + Uncertainty representation section + diagram
- **Requested output:** Stylometric heuristics signal (`stylometric.py`) + confidence-weighted ensemble in `pipeline.py`
- **Verification:** Check that `ai_probability` varies meaningfully between clearly AI text (>0.7 expected) and personal journal-style text (<0.35 expected). Confirm that a 0.51 score and a 0.91 score produce different `confidence_score` values and different label variants.

### M5 — Production layer
- **Spec sections provided:** Transparency label design section + Appeals workflow section + diagram
- **Requested output:** Label generation logic (embedded in `pipeline.py`) + `POST /appeal` endpoint + `GET /log` endpoint
- **Verification:** Test all three label variants are reachable by submitting text that produces each attribution. Confirm that `POST /appeal` updates `appeal_status` to `"under_review"` and that the appeal appears in `GET /log` output alongside the original decision.

## Stretch Features

- **Ensemble detection (3 signals):** Implemented — see Signal 3 above
- **Provenance certificate:** POST `/certificate` issues a `verification_token` for creators who attest human authorship. Token is stored in DB; can be displayed alongside content
- **Analytics dashboard:** GET `/analytics` returns attribution breakdown, appeal rate, average confidence, and recent submission trend
