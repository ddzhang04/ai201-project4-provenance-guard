"""
Entropy / repetition signal for AI detection (stretch: 3rd ensemble signal).

AI-generated text tends to have:
- Lower bigram entropy (more predictable word pairs)
- Higher trigram repetition rates
- More uniform n-gram distributions

Returns a probability [0.0, 1.0] that the text is AI-generated.
"""

import math
import re
from collections import Counter


def _tokens(text: str) -> list[str]:
    return re.findall(r"\b[a-zA-Z']+\b", text.lower())


def _bigram_entropy(tokens: list[str]) -> float:
    """Shannon entropy of bigrams. Lower entropy → more predictable → likely AI."""
    if len(tokens) < 4:
        return 0.5
    bigrams = [(tokens[i], tokens[i + 1]) for i in range(len(tokens) - 1)]
    counts = Counter(bigrams)
    total = sum(counts.values())
    entropy = -sum((c / total) * math.log2(c / total) for c in counts.values())
    # Typical range: 5-12 bits. Normalize: low entropy → AI
    # AI tends toward 5-8 bits, human 8-12 bits
    normalized = max(0.0, min(1.0, (9.0 - entropy) / 5.0))
    return normalized


def _trigram_repetition(tokens: list[str]) -> float:
    """Ratio of repeated trigrams. Higher repetition → AI."""
    if len(tokens) < 6:
        return 0.5
    trigrams = [(tokens[i], tokens[i+1], tokens[i+2]) for i in range(len(tokens) - 2)]
    if not trigrams:
        return 0.5
    counts = Counter(trigrams)
    repeated = sum(1 for c in counts.values() if c > 1)
    ratio = repeated / len(counts)
    # Scale: 0 repetition = 0.3 AI prob; high repetition = 0.9
    return max(0.0, min(1.0, 0.3 + ratio * 1.5))


def _lexical_predictability(tokens: list[str]) -> float:
    """Unigram dominance: top-10 words covering high fraction suggests AI formulaicity."""
    if len(tokens) < 20:
        return 0.5
    counts = Counter(tokens)
    total = len(tokens)
    top10 = sum(c for _, c in counts.most_common(10))
    coverage = top10 / total
    # High coverage → AI. Typical human: 0.3-0.5; AI: 0.45-0.65
    return max(0.0, min(1.0, (coverage - 0.35) / 0.25 + 0.4))


def analyze(text: str) -> dict:
    """
    Run entropy/repetition heuristics and return a combined signal.

    Returns:
        {
            "signal_name": "entropy",
            "ai_probability": float,
            "sub_scores": {...},
            "confidence": float,
        }
    """
    tokens = _tokens(text)

    bigram_ent = _bigram_entropy(tokens)
    trigram_rep = _trigram_repetition(tokens)
    predictability = _lexical_predictability(tokens)

    weights = {"bigram_entropy": 0.45, "trigram_repetition": 0.30, "predictability": 0.25}
    combined = (
        bigram_ent * weights["bigram_entropy"]
        + trigram_rep * weights["trigram_repetition"]
        + predictability * weights["predictability"]
    )

    word_count = len(tokens)
    confidence = min(1.0, word_count / 200) * 0.75 + 0.10

    return {
        "signal_name": "entropy",
        "ai_probability": round(combined, 4),
        "sub_scores": {
            "bigram_entropy": round(bigram_ent, 4),
            "trigram_repetition": round(trigram_rep, 4),
            "lexical_predictability": round(predictability, 4),
        },
        "confidence": round(confidence, 4),
    }
