# Provenance Guard

A backend system for creative sharing platforms to classify submitted content, score confidence in that classification, surface transparency labels to users, and handle appeals from creators who believe they've been misclassified.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your GROQ_API_KEY

python app.py
```

The API runs at `http://localhost:5000`.

---

## Endpoints

### `POST /submit`
Submit content for attribution analysis.

**Request:**
```json
{ "content": "Your poem, story excerpt, or blog post here..." }
```

**Response:**
```json
{
  "submission_id": "a1b2c3d4e5f6a1b2",
  "attribution": "uncertain",
  "ai_probability": 0.54,
  "confidence_score": 0.31,
  "transparency_label": {
    "variant": "uncertain",
    "headline": "Authorship Uncertain",
    "body": "Our system is uncertain about the origin of this content...",
    "action": "Creators can provide additional context through our appeals process."
  },
  "signals_used": ["groq_llm", "stylometric", "entropy"]
}
```

### `POST /appeal`
Contest a classification. Status updates to `"under_review"`.

```json
{
  "submission_id": "a1b2c3d4e5f6a1b2",
  "creator_reasoning": "I wrote this myself over several weeks — it's based on personal experience that no AI would know about."
}
```

### `POST /certificate` *(stretch)*
Issue a provenance certificate for a submission.

```json
{
  "submission_id": "a1b2c3d4e5f6a1b2",
  "creator_statement": "I, the creator, attest that this content was written entirely by me."
}
```

Returns a `certificate_id` and `verification_token` that can be displayed alongside the content.

### `GET /log`
Audit log of all attribution decisions and appeals.

```
GET /log?limit=10&offset=0
```

Sample output (3 entries):
```json
{
  "entries": [
    {
      "id": "abc123",
      "created_at": "2026-06-28T14:23:11+00:00",
      "content_preview": "Furthermore, it is important to note that the tapestry of human...",
      "attribution": "ai",
      "ai_probability": 0.87,
      "confidence_score": 0.79,
      "appeal_status": "none"
    },
    {
      "id": "def456",
      "created_at": "2026-06-28T14:20:05+00:00",
      "content_preview": "I honestly don't know how to start this. My dad died last spring...",
      "attribution": "human",
      "ai_probability": 0.11,
      "confidence_score": 0.72,
      "appeal_status": "none"
    },
    {
      "id": "ghi789",
      "created_at": "2026-06-28T14:18:44+00:00",
      "content_preview": "The light shifted in a way I can only describe as suspicious...",
      "attribution": "uncertain",
      "ai_probability": 0.51,
      "confidence_score": 0.22,
      "appeal_status": "under_review",
      "creator_reasoning": "This is a short poem I wrote in my notebook — the style is intentionally spare."
    }
  ]
}
```

### `GET /analytics` *(stretch)*
Detection patterns, appeal rates, and confidence stats.

### `GET /submission/<id>`
Look up a specific submission by ID.

---

## Detection Signals

The system uses **3 distinct signals** combined via confidence-weighted ensemble:

| Signal | Weight | What it captures |
|--------|--------|-----------------|
| **Groq LLM** (`llama-3.3-70b-versatile`) | 0.50 | Semantic patterns, reasoning structure, characteristic AI discourse ("delve", "tapestry", "it is worth noting") — things humans perceive but are hard to measure |
| **Stylometric heuristics** | 0.30 | Surface writing statistics: sentence length burstiness, type-token ratio, AI marker phrases, punctuation patterns. Human writing has higher variance; AI is more "averaged" |
| **Entropy / N-gram analysis** | 0.20 | Distributional properties: Shannon entropy of bigrams, trigram repetition rate, lexical dominance. AI text tends toward lower entropy and more predictable sequences |

Each signal returns both an `ai_probability` and a `confidence` value. The pipeline computes a confidence-weighted average so that an uncertain Groq result contributes less than a high-confidence one.

---

## Confidence Scoring

The `confidence_score` reflects **how much to trust the attribution**, not just the attribution itself.

**Formula:**
```
confidence = 0.6 × score_extremity + 0.4 × signal_agreement

where:
  score_extremity = |ai_probability - 0.5| × 2   (0 at 0.5, 1 at 0/1)
  signal_agreement = 1 - variance(all_signal_probs) × 4
```

**Why this matters:**
- A `confidence_score` of 0.95 means: the score is extreme AND all signals agree. High trust.
- A `confidence_score` of 0.15 means: the signals disagree or the score is near 0.5. Low trust — treat as uncertain regardless of the label.
- A 0.51 and a 0.95 `ai_probability` produce meaningfully different confidence scores and thus different transparency labels.

**Testing methodology:** We tested the scoring on:
1. Clearly AI-generated text (ChatGPT outputs) — should produce high `ai_probability` and high `confidence_score`
2. Raw personal writing (journal entries, stream-of-consciousness) — should produce low `ai_probability`
3. Edited/polished human writing — should produce moderate, uncertain scores, reflecting genuine ambiguity
4. Mixed content (human draft, AI-polished) — should land in uncertain zone with low confidence

---

## Transparency Labels

All three label variants are shown below exactly as they appear in API responses:

### High-Confidence AI (`ai_probability ≥ 0.80`)

> **AI-Generated Content**
>
> Our system found strong indicators that this content was generated by an AI writing tool (87% AI probability, 79% system confidence). Multiple independent signals — including writing structure, vocabulary patterns, and semantic style — all pointed in the same direction. If you believe this is incorrect, the creator can submit an appeal.

### High-Confidence Human (`ai_probability ≤ 0.20`)

> **Human-Written Content**
>
> Our analysis found strong indicators of original human authorship (89% human probability, 72% system confidence). The writing shows the kind of natural variation, personal voice, and idiosyncratic style that distinguishes human work.

### Uncertain (`ai_probability 0.21–0.79`)

> **Authorship Uncertain**
>
> Our system is uncertain about the origin of this content (AI probability: 54%, system confidence: 31%). The writing shows a mix of patterns that our analysis cannot reliably attribute to either AI or human authorship alone. This is not a verdict — it reflects the limits of automated detection. Creators can provide additional context through our appeals process.

---

## Appeals Workflow

Creators can contest a classification via `POST /appeal`. The workflow:

1. Creator provides `submission_id` and `creator_reasoning`
2. Appeal is logged alongside the original decision in the audit DB
3. Submission status updates to `"under_review"` — visible in `/log` and `/submission/<id>`
4. A human reviewer examines the content and reasoning

**Automated re-classification is intentionally not performed.** Running the same pipeline again would produce the same result. The appeal exists to give creators a path to human review and to ensure the system acknowledges uncertainty honestly.

---

## Rate Limiting

| Endpoint | Limit | Reasoning |
|----------|-------|-----------|
| `POST /submit` | 10/min, 100/day per IP | Each request calls the Groq API (cost and abuse vector). A creator realistically submits 1–3 pieces per session. 10/min covers edge cases like batch testing; an adversary flooding submissions would need thousands of requests to gain any advantage, and the daily cap prevents sustained abuse. |
| `POST /appeal` | 5/min, 50/day per IP | Appeals are manual creator actions. 5/min prevents scripted bulk filing while being generous enough for real use. |
| All other routes | 50/hr, 200/day per IP | Read-only endpoints — generous for dashboard or monitoring integrations. |

---

## Stack

| Component | Tool |
|-----------|------|
| API framework | Flask |
| LLM signal | Groq (`llama-3.3-70b-versatile`) |
| Heuristic signals | Pure Python (no external deps) |
| Rate limiting | Flask-Limiter |
| Audit log | SQLite (built-in) |
| Config | python-dotenv |

---

## Stretch Features Implemented

- **Ensemble detection (3 signals):** Three independent signals with documented weighting (Groq 50%, stylometric 30%, entropy 20%)
- **Provenance certificate:** `POST /certificate` issues a verified-human credential with a `verification_token` that creators can display alongside their content
- **Analytics dashboard:** `GET /analytics` shows attribution breakdown, appeal rate, average confidence, and recent submission trend
