"""
Phrase-level sentiment scoring with negation detection.
Much more accurate than simple word bags (handles 'not bullish', 'crash risk elevated', etc.)
"""

# Two-word phrase scores — more precise than single words
PHRASE_SCORES = {
    # Strong bullish phrases
    "beats estimates":   +0.8, "beat expectations":  +0.8, "record revenue":    +0.8,
    "raised guidance":   +0.7, "raises guidance":    +0.7, "strong earnings":   +0.7,
    "new contract":      +0.6, "strategic deal":     +0.6, "market share":      +0.4,
    "analyst upgrade":   +0.7, "price target raised": +0.6, "buy rating":        +0.6,
    "all-time high":     +0.5, "52-week high":        +0.5, "breakout":          +0.4,
    # Strong bearish phrases
    "misses estimates":  -0.8, "miss expectations":  -0.8, "revenue decline":   -0.7,
    "lowers guidance":   -0.7, "lowered guidance":   -0.7, "profit warning":    -0.8,
    "analyst downgrade": -0.7, "price target cut":   -0.6, "sell rating":       -0.6,
    "class action":      -0.8, "sec investigation":  -0.8, "regulatory fine":   -0.7,
    "data breach":       -0.7, "supply chain":       -0.3, "layoffs announced": -0.6,
    "misses revenue":    -0.7, "earnings miss":      -0.7, "beats revenue":     +0.7,
}

# Single-word fallback scores — only used when no phrase matches
WORD_SCORES = {
    "surge": +0.4, "soar": +0.4, "rally": +0.3, "gain": +0.2, "beat": +0.3,
    "record": +0.2, "profit": +0.2, "growth": +0.2, "upgrade": +0.4, "buy": +0.2,
    "strong": +0.2, "bullish": +0.4, "jump": +0.3, "rise": +0.2, "breakthrough": +0.4,
    "fall": -0.3, "drop": -0.3, "crash": -0.5, "miss": -0.3, "loss": -0.3,
    "weak": -0.2, "sell": -0.2, "bearish": -0.4, "decline": -0.3, "cut": -0.3,
    "layoff": -0.4, "lawsuit": -0.4, "fine": -0.3, "recall": -0.4, "warning": -0.3,
    "investigation": -0.4, "concern": -0.2, "debt": -0.2,
}

NEGATIONS = {"not", "no", "never", "without", "despite", "against", "fails", "unable"}


def score_headline(title: str) -> dict:
    title_lower = title.lower()
    score = 0.0
    matched_phrases = set()

    # Phase 1: phrase matching
    for phrase, val in PHRASE_SCORES.items():
        if phrase in title_lower:
            score += val
            matched_phrases.update(phrase.split())

    # Phase 2: word scoring for unmatched words, with negation window
    words = title_lower.split()
    for i, word in enumerate(words):
        if word in matched_phrases:
            continue
        if word in WORD_SCORES:
            # Check if a negation word appears within 3 words before
            window = words[max(0, i-3):i]
            multiplier = -1 if any(n in window for n in NEGATIONS) else 1
            score += WORD_SCORES[word] * multiplier

    score = max(-1.0, min(1.0, score))
    if score > 0.15:
        return {"label": "Bullish 🟢", "score": round(score, 3)}
    if score < -0.15:
        return {"label": "Bearish 🔴", "score": round(score, 3)}
    return {"label": "Neutral 🟡", "score": round(score, 3)}


def score_news(articles: list) -> dict:
    if not articles:
        return {"label": "No news", "score": 0, "scored": []}
    scored = []
    total  = 0.0
    for a in articles:
        s = score_headline(a["title"])
        scored.append({**a, **s})
        total += s["score"]
    avg   = total / len(articles)
    label = "Bullish 🟢" if avg > 0.1 else ("Bearish 🔴" if avg < -0.1 else "Neutral 🟡")
    return {"label": label, "score": round(avg, 3), "scored": scored}
