"""
Stylometric heuristics signal for AI vs human detection.

Captures surface-level writing statistics that differ between AI and human text:
- Sentence length burstiness: humans vary length more; AI is more uniform
- Type-token ratio: vocabulary richness (AI slightly lower on long texts)
- Function word density: AI uses connectives like "furthermore", "notably" more
- Punctuation density: exclamation marks rarer in AI; em-dashes rarer in AI

Returns a probability [0.0, 1.0] that the text is AI-generated.
"""

import re
import math


AI_MARKER_PHRASES = [
    "furthermore", "notably", "in conclusion", "it is worth noting",
    "it's worth noting", "it is important to", "it's important to",
    "in summary", "to summarize", "as an ai", "as a language model",
    "delve", "tapestry", "nuanced", "multifaceted", "underscore",
    "leverage", "paradigm", "in the realm of", "it is crucial",
]

HUMAN_MARKER_PHRASES = [
    "honestly", "look,", "i mean,", "you know", "kind of", "sort of",
    "tbh", "lol", "honestly though", "like,",
]


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


def _words(text: str) -> list[str]:
    return re.findall(r"\b[a-zA-Z']+\b", text.lower())


def _sentence_burstiness(sentences: list[str]) -> float:
    """Low burstiness (uniform lengths) → AI. Returns 0-1 AI probability."""
    if len(sentences) < 3:
        return 0.5
    lengths = [len(_words(s)) for s in sentences]
    mean = sum(lengths) / len(lengths)
    if mean == 0:
        return 0.5
    variance = sum((l - mean) ** 2 for l in lengths) / len(lengths)
    std = math.sqrt(variance)
    cv = std / mean  # coefficient of variation
    # High CV → human (varied). Low CV → AI (uniform).
    # Typical human CV: 0.4-0.9; AI CV: 0.2-0.5
    ai_prob = max(0.0, min(1.0, 1.0 - (cv / 0.6)))
    return ai_prob


def _type_token_ratio(words: list[str]) -> float:
    """Lower TTR on long texts can indicate AI. Returns 0-1 AI probability."""
    if len(words) < 10:
        return 0.5
    unique = len(set(words))
    ttr = unique / len(words)
    # Normalize: TTR < 0.5 hints AI, > 0.75 hints human
    ai_prob = max(0.0, min(1.0, (0.65 - ttr) / 0.3 + 0.5))
    return max(0.0, min(1.0, ai_prob))


def _marker_score(text: str) -> float:
    """AI marker phrases push score up; human markers push down."""
    lower = text.lower()
    ai_hits = sum(1 for phrase in AI_MARKER_PHRASES if phrase in lower)
    human_hits = sum(1 for phrase in HUMAN_MARKER_PHRASES if phrase in lower)
    words = _words(text)
    word_count = max(len(words), 1)
    ai_density = ai_hits / (word_count / 100)
    human_density = human_hits / (word_count / 100)
    raw = 0.5 + (ai_density * 0.15) - (human_density * 0.15)
    return max(0.0, min(1.0, raw))


def _punctuation_signal(text: str) -> float:
    """Exclamation marks and em-dashes are rarer in AI; returns 0-1 AI prob."""
    word_count = max(len(_words(text)), 1)
    exclamations = text.count("!")
    em_dashes = text.count("—") + text.count("--")
    human_indicators = (exclamations + em_dashes) / (word_count / 100)
    # More human indicators → lower AI prob
    ai_prob = max(0.0, min(1.0, 0.6 - (human_indicators * 0.08)))
    return ai_prob


def analyze(text: str) -> dict:
    """
    Run all stylometric heuristics and return a combined signal.

    Returns:
        {
            "signal_name": "stylometric",
            "ai_probability": float,  # 0.0 = human, 1.0 = AI
            "sub_scores": {...},
            "confidence": float,      # how much to trust this signal
        }
    """
    sentences = _sentences(text)
    words = _words(text)

    burstiness = _sentence_burstiness(sentences)
    ttr = _type_token_ratio(words)
    markers = _marker_score(text)
    punctuation = _punctuation_signal(text)

    # Weighted combination of sub-scores
    weights = {"burstiness": 0.35, "ttr": 0.20, "markers": 0.30, "punctuation": 0.15}
    combined = (
        burstiness * weights["burstiness"]
        + ttr * weights["ttr"]
        + markers * weights["markers"]
        + punctuation * weights["punctuation"]
    )

    # Signal confidence is lower for very short texts
    word_count = len(words)
    confidence = min(1.0, word_count / 150) * 0.85 + 0.15

    return {
        "signal_name": "stylometric",
        "ai_probability": round(combined, 4),
        "sub_scores": {
            "burstiness": round(burstiness, 4),
            "type_token_ratio": round(ttr, 4),
            "marker_phrases": round(markers, 4),
            "punctuation": round(punctuation, 4),
        },
        "confidence": round(confidence, 4),
    }
