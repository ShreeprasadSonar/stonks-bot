"""
Social sentiment via StockTwits — no API key or credentials required.
Replaces the previous Reddit/PRAW implementation.
StockTwits is finance-focused social media: every post is about stocks.
"""
import logging
import requests

logger = logging.getLogger(__name__)

BULLISH_WORDS = [
    "buy", "buying", "bull", "bullish", "moon", "calls", "long",
    "breakout", "undervalued", "upside", "squeeze", "strong", "upgrade",
    "accumulate", "hold", "rocket", "run", "bounce", "bottom",
]
BEARISH_WORDS = [
    "sell", "selling", "bear", "bearish", "puts", "short", "crash", "dump",
    "overvalued", "avoid", "warning", "downgrade", "weak", "drop",
    "bubble", "falling", "loss", "top", "resist",
]


def get_reddit_sentiment(ticker: str, limit: int = 30) -> dict:
    """
    Fetch StockTwits stream for ticker.
    Returns same dict shape as the old Reddit version so all callers work unchanged.
    No API key needed — free public endpoint.
    """
    try:
        url  = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "StockBot/1.0"})

        if resp.status_code == 404:
            return _no_data(ticker, "Ticker not found on StockTwits")
        if resp.status_code == 429:
            return _no_data(ticker, "StockTwits rate limit — try again in a minute")
        if resp.status_code != 200:
            return _no_data(ticker, f"StockTwits returned HTTP {resp.status_code}")

        data      = resp.json()
        messages  = data.get("messages", [])
        symbol    = data.get("symbol", {})

        if not messages:
            return {
                "ticker":     ticker,
                "mentions":   0,
                "upvotes":    0,
                "hype_score": 0,
                "hype_label": "🔇 No StockTwits Activity",
                "sentiment":  "🟡 No signal",
                "top_posts":  [],
                "available":  True,
                "note":       "No recent messages on StockTwits",
                "source":     "StockTwits",
            }

        bull_count = 0
        bear_count = 0
        bull_word  = 0
        bear_word  = 0
        top_posts  = []

        for msg in messages[:limit]:
            body   = (msg.get("body") or "").lower()
            # StockTwits has explicit sentiment labels on some posts
            entities  = msg.get("entities", {})
            st_sent   = msg.get("entities", {}).get("sentiment", {})
            if isinstance(st_sent, dict):
                basic = st_sent.get("basic", "")
                if basic == "Bullish":
                    bull_count += 1
                elif basic == "Bearish":
                    bear_count += 1

            bull_word += sum(1 for w in BULLISH_WORDS if w in body)
            bear_word += sum(1 for w in BEARISH_WORDS if w in body)

            if len(top_posts) < 3:
                likes = msg.get("likes", {}).get("total", 0)
                top_posts.append({
                    "title": msg.get("body", "")[:100],
                    "score": likes,
                    "sub":   "StockTwits",
                    "url":   f"https://stocktwits.com/symbol/{ticker}",
                })

        total_messages = len(messages)
        total_bull     = bull_count + bull_word
        total_bear     = bear_count + bear_word

        # Hype score: message volume (0-100)
        hype_score = min(100, total_messages * 2)

        if hype_score >= 70:
            hype_label = "🚀 Extreme Hype"
        elif hype_score >= 40:
            hype_label = "🔥 High Buzz"
        elif hype_score >= 15:
            hype_label = "💬 Moderate Activity"
        else:
            hype_label = "🔇 Low Activity"

        if total_bull > total_bear * 1.4:
            sentiment = "🟢 Mostly Bullish"
        elif total_bear > total_bull * 1.4:
            sentiment = "🔴 Mostly Bearish"
        else:
            sentiment = "🟡 Mixed Sentiment"

        # StockTwits explicit labels are more reliable — override if available
        if bull_count + bear_count >= 3:
            bull_pct = bull_count / (bull_count + bear_count)
            if bull_pct >= 0.65:
                sentiment = f"🟢 Bullish ({bull_count}👍 vs {bear_count}👎 tagged)"
            elif bull_pct <= 0.35:
                sentiment = f"🔴 Bearish ({bear_count}👎 vs {bull_count}👍 tagged)"

        # Also pull StockTwits watchlist count if available
        watchers = symbol.get("watchlist_count", 0)

        logger.info(
            f"[{ticker}] StockTwits: {total_messages} msgs, "
            f"bull={total_bull}, bear={total_bear}, watchers={watchers:,}"
        )

        return {
            "ticker":     ticker,
            "mentions":   total_messages,
            "upvotes":    watchers,        # repurposed field: watchlist count
            "hype_score": hype_score,
            "hype_label": hype_label,
            "sentiment":  sentiment,
            "top_posts":  top_posts,
            "available":  True,
            "note":       f"{watchers:,} users watch {ticker} on StockTwits",
            "source":     "StockTwits",
            "watchers":   watchers,
        }

    except Exception as e:
        logger.error(f"[{ticker}] StockTwits fetch error: {e}")
        return _no_data(ticker, str(e))


def format_reddit_report(ticker: str, data: dict) -> str:
    """Format StockTwits sentiment into a readable Telegram message."""
    if not data.get("available"):
        return (
            f"📱 *STOCKTWITS SOCIAL SENTIMENT — {ticker}*\n"
            f"   ⚠️ {data.get('note', 'Unavailable')}\n"
        )

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📱 *STOCKTWITS BUZZ — {ticker}*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"   Activity: *{data['hype_label']}*",
        f"   Mood: {data['sentiment']}",
        f"   Recent messages: *{data['mentions']}*",
    ]

    watchers = data.get("watchers", 0)
    if watchers:
        lines.append(f"   👀 Watchlist: *{watchers:,}* traders following this stock")

    lines += [
        "",
        "🧠 *What this means:*",
        "   _StockTwits is finance-only social media — pure trader sentiment._",
        "   _Bullish/Bearish labels are self-reported by traders posting._",
        "   _High activity + Bullish mood = strong retail conviction._",
        "   _Always combine with RSI + news before deciding._",
    ]

    if data.get("top_posts"):
        lines += ["", "💬 *Recent Posts:*"]
        for p in data["top_posts"]:
            likes_str = f" ({p['score']} ❤️)" if p["score"] else ""
            lines.append(f"   • {p['title'][:80]}…{likes_str}")

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
        "source":     "StockTwits",
    }

