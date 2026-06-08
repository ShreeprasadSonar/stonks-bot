"""Fetch news headlines from Google News RSS (free, no key needed)."""
import re
import logging
import feedparser

logger = logging.getLogger(__name__)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def get_news(ticker: str, company_name: str = "", limit: int = 10) -> list:
    query     = company_name or ticker
    query_enc = query.replace(" ", "+")
    url       = f"https://news.google.com/rss/search?q={query_enc}+stock&hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(url)
        articles = []
        for entry in feed.entries[:limit]:
            # summary/description gives context beyond just the headline
            raw_summary = entry.get("summary", "") or entry.get("description", "")
            summary = _strip_html(raw_summary)[:400] if raw_summary else ""
            articles.append({
                "title":     entry.get("title", ""),
                "published": entry.get("published", ""),
                "link":      entry.get("link", ""),
                "source":    entry.get("source", {}).get("title", ""),
                "summary":   summary,
            })
        logger.debug(f"[{ticker}] Fetched {len(articles)} news articles")
        return articles
    except Exception as e:
        logger.error(f"[{ticker}] News fetch failed: {e}")
        return []


def check_political_mentions(ticker: str, company_name: str = "") -> list:
    """Scan news for political figure mentions alongside the stock."""
    political_keywords = [
        "trump", "biden", "harris", "president", "senator", "congress",
        "white house", "government", "federal", "pentagon", "sec",
        "regulation", "tariff", "subsidy", "contract", "executive order",
        "antitrust", "doj", "treasury", "musk", "powell"
    ]
    articles = get_news(ticker, company_name, limit=30)
    hits = []
    for a in articles:
        title_lower = a["title"].lower()
        matched = [kw for kw in political_keywords if kw in title_lower]
        if matched:
            hits.append({**a, "political_keywords": matched})
    logger.info(f"[{ticker}] Found {len(hits)} political mentions in {len(articles)} articles")
    return hits
