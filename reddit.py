"""
Reddit social sentiment — Phase 5.
Scans r/wallstreetbets and r/investing for ticker mentions.
Falls back gracefully if Reddit credentials are not set.
"""
import logging
import time
from config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT

logger = logging.getLogger(__name__)

# Subreddits to scan (in order of market impact)
SUBREDDITS = ["wallstreetbets", "investing", "stocks", "StockMarket"]

# Sentiment words tuned for Reddit / WSB slang
BULLISH_WORDS = [
    "buy", "buying", "bull", "bullish", "moon", "mooning", "calls", "long",
    "rocket", "🚀", "yolo", "squeeze", "breakout", "undervalued", "upside",
    "strong buy", "loading", "accumulate", "hold", "hodl", "upgrade",
]
BEARISH_WORDS = [
    "sell", "selling", "bear", "bearish", "puts", "short", "crash", "dump",
    "overvalued", "avoid", "warning", "down", "downgrade", "weak", "drop",
    "bubble", "falling", "red", "loss", "rekt", "bankrupt",
]


def _praw_client():
    """Return a read-only PRAW client, or None if credentials missing."""
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        return None
    try:
        import praw
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
        )
        reddit.read_only = True
        return reddit
    except Exception as e:
        logger.warning(f"Reddit client init failed: {e}")
        return None


def get_reddit_sentiment(ticker: str, limit: int = 50) -> dict:
    """
    Search recent Reddit posts for ticker mentions.
    Returns a dict with: mentions, upvotes, hype_score (0-100), hype_label, sentiment, top_posts.
    """
    reddit = _praw_client()
    if not reddit:
        return _no_data(ticker, "Reddit credentials not configured")

    mentions      = 0
    total_upvotes = 0
    bull_score    = 0
    bear_score    = 0
    top_posts     = []

    try:
        for sub_name in SUBREDDITS:
            sub = reddit.subreddit(sub_name)
            # Search last 24h
            for post in sub.search(ticker, sort="new", time_filter="day", limit=limit):
                text = (post.title + " " + (post.selftext or "")).lower()

                # Only count if ticker appears as a standalone word (avoid false matches)
                import re
                if not re.search(rf'\b{re.escape(ticker.lower())}\b', text):
                    continue

                mentions      += 1
                total_upvotes += max(0, post.score)
                bull_score    += sum(1 for w in BULLISH_WORDS if w in text)
                bear_score    += sum(1 for w in BEARISH_WORDS if w in text)

                if len(top_posts) < 3:
                    top_posts.append({
                        "title":   post.title[:100],
                        "score":   post.score,
                        "sub":     sub_name,
                        "url":     f"https://reddit.com{post.permalink}",
                    })

            time.sleep(0.5)  # polite rate limit between subreddits

    except Exception as e:
        logger.error(f"[{ticker}] Reddit fetch error: {e}")
        return _no_data(ticker, str(e))

    if mentions == 0:
        logger.info(f"[{ticker}] No Reddit mentions found in last 24h")
        return {
            "ticker":      ticker,
            "mentions":    0,
            "upvotes":     0,
            "hype_score":  0,
            "hype_label":  "🔇 No Reddit Buzz",
            "sentiment":   "🟡 No signal",
            "top_posts":   [],
            "available":   True,
            "note":        "No mentions found in last 24h",
        }

    # Hype score: combines mention count + upvotes (capped at 100)
    # 10 mentions = ~50 score, each 1k upvotes = +10 points
    hype_score = min(100, int(mentions * 4 + (total_upvotes / 500) * 10))

    if hype_score >= 70:
        hype_label = "🚀 Extreme Hype"
    elif hype_score >= 45:
        hype_label = "🔥 High Buzz"
    elif hype_score >= 20:
        hype_label = "💬 Moderate Mentions"
    else:
        hype_label = "🔇 Low Mentions"

    # Sentiment from bull/bear word ratio
    if bull_score > bear_score * 1.5:
        sentiment = "🟢 Mostly Bullish"
    elif bear_score > bull_score * 1.5:
        sentiment = "🔴 Mostly Bearish"
    else:
        sentiment = "🟡 Mixed Sentiment"

    logger.info(
        f"[{ticker}] Reddit: {mentions} mentions, {total_upvotes} upvotes, "
        f"hype={hype_score}, bull={bull_score}, bear={bear_score}"
    )

    return {
        "ticker":     ticker,
        "mentions":   mentions,
        "upvotes":    total_upvotes,
        "hype_score": hype_score,
        "hype_label": hype_label,
        "sentiment":  sentiment,
        "top_posts":  top_posts,
        "available":  True,
        "note":       "",
    }


def format_reddit_report(ticker: str, data: dict) -> str:
    """Format Reddit sentiment into a readable Telegram section."""
    if not data.get("available"):
        return (
            f"📱 *REDDIT SOCIAL SENTIMENT*\n"
            f"   ⚠️ {data.get('note', 'Unavailable')}\n"
            f"   _Add REDDIT_CLIENT_ID/SECRET as GitHub Secrets to enable_"
        )

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "📱 *REDDIT SOCIAL BUZZ*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"   Hype Level: *{data['hype_label']}*",
        f"   Mood: {data['sentiment']}",
        f"   Mentions (24h): *{data['mentions']}*  |  Upvotes: *{data['upvotes']:,}*",
        "",
        "🧠 *What this means:*",
        "   _High WSB hype = lots of retail trader interest._",
        "   _Extreme hype can cause short squeezes OR sharp reversals._",
        "   _Always combine with technical signals before deciding._",
    ]

    if data["top_posts"]:
        lines += ["", "💬 *Top Posts:*"]
        for p in data["top_posts"]:
            lines.append(f"   • r/{p['sub']} ({p['score']:,} ⬆️) — {p['title'][:70]}…")

    return "\n".join(lines)


def _no_data(ticker: str, reason: str) -> dict:
    return {
        "ticker":     ticker,
        "mentions":   0,
        "upvotes":    0,
        "hype_score": 0,
        "hype_label": "N/A",
        "sentiment":  "N/A",
        "top_posts":  [],
        "available":  False,
        "note":       reason,
    }
