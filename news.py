"""Fetch news headlines from Google News RSS (free, no key needed)."""
import feedparser


def get_news(ticker: str, company_name: str = "", limit: int = 10) -> list:
    query     = company_name or ticker
    query_enc = query.replace(" ", "+")
    url       = f"https://news.google.com/rss/search?q={query_enc}+stock&hl=en-US&gl=US&ceid=US:en"
    feed      = feedparser.parse(url)
    articles  = []
    for entry in feed.entries[:limit]:
        articles.append({
            "title":     entry.get("title", ""),
            "published": entry.get("published", ""),
            "link":      entry.get("link", ""),
            "source":    entry.get("source", {}).get("title", ""),
        })
    return articles


def check_political_mentions(ticker: str, company_name: str = "") -> list:
    """Scan news for political figure mentions alongside the stock."""
    political_keywords = [
        "president", "senator", "congress", "white house", "biden", "trump",
        "government", "federal", "pentagon", "sec", "regulation", "tariff",
        "subsidy", "contract", "executive order"
    ]
    articles = get_news(ticker, company_name, limit=30)
    hits = []
    for a in articles:
        title_lower = a["title"].lower()
        matched = [kw for kw in political_keywords if kw in title_lower]
        if matched:
            hits.append({**a, "political_keywords": matched})
    return hits
