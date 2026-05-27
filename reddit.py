"""
Social sentiment via Yahoo Finance Trending — no API key, no credentials.
Replaces StockTwits (403) and Reddit (requires credentials).

Yahoo Finance Trending shows what tickers retail investors are actively
searching and watching right now — a reliable free proxy for social sentiment.
"""
import logging
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

YAHOO_TRENDING_URL = "https://query1.finance.yahoo.com/v1/finance/trending/US"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def get_trending_tickers(limit: int = 20) -> list:
    """
    Fetch Yahoo Finance trending tickers for the US market.
    Free, no API key, refreshes during market hours.
    """
    try:
        resp = requests.get(YAHOO_TRENDING_URL, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"Yahoo Trending returned HTTP {resp.status_code}")
            return []
        data   = resp.json()
        quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
        tickers = [q["symbol"] for q in quotes[:limit] if q.get("symbol")]
        logger.info(f"Yahoo Trending: {len(tickers)} tickers — {tickers[:8]}")
        return tickers
    except Exception as e:
        logger.error(f"Yahoo Trending fetch failed: {e}")
        return []


def get_reddit_sentiment(ticker: str, limit: int = 30) -> dict:
    """
    Public sentiment proxy using Yahoo Finance Trending + volume + news.
    Same return dict shape as old Reddit/StockTwits — all callers unchanged.

    Scoring:
    - Yahoo Trending rank:  rank 1-5=40pts, 6-15=25pts, 16-50=15pts, not=0
    - Volume ratio:         >3x=30pts, >2x=20pts, >1.5x=10pts, else=0
    - News sentiment:       positive=20pts, neutral=10pts, negative=0pts
    """
    try:
        trending    = get_trending_tickers(50)
        in_trending = ticker.upper() in [t.upper() for t in trending]
        trend_rank  = None
        if in_trending:
            for i, t in enumerate(trending):
                if t.upper() == ticker.upper():
                    trend_rank = i + 1
                    break

        try:
            hist = yf.download(ticker, period="5d", auto_adjust=True,
                               progress=False, timeout=10)
            if not hist.empty:
                if hasattr(hist.columns, "levels"):
                    hist.columns = hist.columns.get_level_values(0)
                avg_vol   = float(hist["Volume"].iloc[:-1].mean())
                today_vol = float(hist["Volume"].iloc[-1])
                vol_ratio = round(today_vol / avg_vol, 2) if avg_vol > 0 else 1.0
            else:
                vol_ratio = 1.0
        except Exception:
            vol_ratio = 1.0

        try:
            from news import get_news
            from sentiment import score_news
            articles   = get_news(ticker, limit=10)
            news_sent  = score_news(articles)
            news_score = news_sent["score"]
            news_label = news_sent["label"]
            top_news   = news_sent.get("scored", [])[:3]
        except Exception:
            news_score = 0
            news_label = "Neutral"
            top_news   = []

        trend_pts = 0
        if trend_rank:
            if trend_rank <= 5:    trend_pts = 40
            elif trend_rank <= 15: trend_pts = 25
            else:                  trend_pts = 15

        vol_pts    = 30 if vol_ratio >= 3 else (20 if vol_ratio >= 2 else (10 if vol_ratio >= 1.5 else 0))
        news_pts   = int((news_score + 1) / 2 * 20)
        hype_score = min(100, trend_pts + vol_pts + news_pts)

        if hype_score >= 65:
            hype_label = "Trending — High Retail Activity"
        elif hype_score >= 40:
            hype_label = "Elevated Interest"
        elif hype_score >= 20:
            hype_label = "Moderate Activity"
        else:
            hype_label = "Low Retail Activity"

        if news_score > 0.15:
            sentiment = "Bullish — " + news_label
        elif news_score < -0.15:
            sentiment = "Bearish — " + news_label
        else:
            sentiment = "Neutral — " + news_label

        top_posts = [
            {
                "title": n.get("title", "")[:100],
                "score": 0,
                "sub":   n.get("source", "News"),
                "url":   n.get("link", ""),
            }
            for n in top_news
        ]

        trend_note = (
            f"#{trend_rank} on Yahoo Finance Trending right now"
            if in_trending and trend_rank
            else "Not currently on Yahoo Finance Trending list"
        )

        logger.info(
            f"[{ticker}] Yahoo social: trending={in_trending} rank={trend_rank}, "
            f"vol_ratio={vol_ratio}, hype={hype_score}"
        )

        return {
            "ticker":        ticker,
            "mentions":      trend_rank or 0,
            "upvotes":       len(trending),
            "hype_score":    hype_score,
            "hype_label":    hype_label,
            "sentiment":     sentiment,
            "top_posts":     top_posts,
            "available":     True,
            "note":          trend_note,
            "source":        "Yahoo Finance",
            "in_trending":   in_trending,
            "trend_rank":    trend_rank,
            "vol_ratio":     vol_ratio,
            "trending_list": trending[:10],
        }

    except Exception as e:
        logger.error(f"[{ticker}] Yahoo sentiment fetch error: {e}")
        return _no_data(ticker, str(e))


def get_market_trending_summary() -> str:
    """HTML-formatted trending list for morning brief."""
    import html as _h
    trending = get_trending_tickers(15)
    if not trending:
        return "   No trending data available"
    lines = [f"   {i}. <b>{_h.escape(t)}</b>" for i, t in enumerate(trending[:10], 1)]
    return "\n".join(lines)


def format_reddit_report(ticker: str, data: dict) -> str:
    """Format Yahoo Finance social sentiment into HTML for Telegram."""
    import html as _h
    t = _h.escape(ticker)

    if not data.get("available"):
        return (
            f"<b>SOCIAL SENTIMENT — {t}</b>\n"
            f"   {_h.escape(data.get('note', 'Unavailable'))}\n"
        )

    in_trending   = data.get("in_trending", False)
    trend_rank    = data.get("trend_rank")
    vol_ratio     = data.get("vol_ratio", 1.0)
    trending_list = data.get("trending_list", [])

    trend_str = (
        f"#​{trend_rank} on Yahoo Finance Trending"
        if in_trending and trend_rank
        else "Not on Yahoo Finance Trending today"
    )

    lines = [
        f"<b>RETAIL SENTIMENT — {t}</b>",
        f"<i>Yahoo Finance Trending + Volume + News</i>",
        "",
        f"   {trend_str}",
        f"   Activity: <b>{_h.escape(data['hype_label'])}</b>",
        f"   News Mood: {_h.escape(data['sentiment'])}",
        f"   Volume: <b>{vol_ratio}x</b> normal  <i>(high = people acting on it)</i>",
    ]

    if trending_list:
        lines += [
            "",
            "<b>Today's Top 10 Yahoo Trending:</b>",
            "   " + "  |  ".join(f"<b>{_h.escape(tk)}</b>" for tk in trending_list[:10]),
        ]

    if data.get("top_posts"):
        lines += ["", "<b>Related News:</b>"]
        for p in data["top_posts"]:
            title   = _h.escape(p["title"][:80])
            url     = p.get("url", "")
            src     = _h.escape(p.get("sub", ""))
            src_str = f"  <i>{src}</i>" if src else ""
            if url:
                lines.append(f'   • <a href="{url}">{title}</a>{src_str}')
            else:
                lines.append(f"   • {title}{src_str}")

    lines += [
        "",
        "<b>What this means:</b>",
        "   <i>Yahoo Trending = stocks retail investors are actively searching.</i>",
        "   <i>High volume ratio = people are acting, not just watching.</i>",
        "   <i>Always combine with RSI + technicals before investing.</i>",
    ]

    return "\n".join(lines)


def _no_data(ticker: str, reason: str) -> dict:
    return {
        "ticker":        ticker,
        "mentions":      0,
        "upvotes":       0,
        "hype_score":    0,
        "hype_label":    "N/A",
        "sentiment":     "N/A",
        "top_posts":     [],
        "available":     False,
        "note":          reason,
        "source":        "Yahoo Finance",
        "in_trending":   False,
        "trend_rank":    None,
        "vol_ratio":     1.0,
        "trending_list": [],
    }
