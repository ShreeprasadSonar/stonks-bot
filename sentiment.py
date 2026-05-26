"""
Simple rule-based sentiment scoring on headlines.
Phase 3 will replace this with FinBERT for accuracy.
"""

BULLISH_WORDS = [
    "surge", "soar", "rally", "gain", "beat", "record", "high", "profit",
    "growth", "upgrade", "buy", "strong", "bullish", "jump", "rise",
    "breakthrough", "contract", "win", "partnership", "revenue"
]
BEARISH_WORDS = [
    "fall", "drop", "crash", "miss", "loss", "down", "weak", "sell",
    "bearish", "decline", "cut", "layoff", "lawsuit", "fine", "recall",
    "warning", "risk", "debt", "concern", "investigation"
]


def score_headline(title: str) -> dict:
    title_lower = title.lower()
    bull = sum(1 for w in BULLISH_WORDS if w in title_lower)
    bear = sum(1 for w in BEARISH_WORDS if w in title_lower)
    if bull > bear:
        return {"label": "Bullish 🟢", "score": min(1.0, bull * 0.2)}
    if bear > bull:
        return {"label": "Bearish 🔴", "score": -min(1.0, bear * 0.2)}
    return {"label": "Neutral 🟡", "score": 0.0}


def score_news(articles: list) -> dict:
    """Score a list of articles and return aggregate sentiment."""
    if not articles:
        return {"label": "No news", "score": 0, "scored": []}

    scored = []
    total  = 0
    for a in articles:
        s = score_headline(a["title"])
        scored.append({**a, **s})
        total += s["score"]

    avg   = total / len(articles)
    label = "Bullish 🟢" if avg > 0.1 else ("Bearish 🔴" if avg < -0.1 else "Neutral 🟡")
    return {"label": label, "score": round(avg, 3), "scored": scored}
