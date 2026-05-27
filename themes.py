"""
Investment Theme Tracker — detects narrative shifts in the market.

Scans Google News headlines + Reddit RSS + Google Trends to measure
how much buzz each macro investment theme is generating RIGHT NOW.

Example: when "AI power demand" starts appearing constantly in headlines
while "AI chips" cools off, this module surfaces that shift before
the stock prices fully move.

All free — no API keys.
"""
import logging
import re
import feedparser
import requests

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# ─────────────────────────────────────────────────────────────────────────────
# THEME DEFINITIONS
# Each theme has:
#   keywords   — words to scan for in headlines (ANY match counts)
#   tickers    — stocks that directly benefit from this theme
#   description — plain English explanation for beginners
# ─────────────────────────────────────────────────────────────────────────────
THEMES = {
    "AI Power & Energy": {
        "keywords": [
            "data center power", "power demand", "electricity grid", "nuclear power",
            "energy consumption", "power plant", "grid capacity", "hyperscaler",
            "data center energy", "power infrastructure", "gigawatt", "megawatt",
        ],
        "tickers": ["VST", "CEG", "ETN", "NRG", "AES", "GEV", "PWR", "EMR"],
        "description": (
            "AI data centers use enormous amounts of electricity. "
            "Companies that build power infrastructure, nuclear plants, "
            "and electrical equipment are the picks-and-shovels play for the AI era."
        ),
        "trend_query": "data center power demand",
    },
    "AI Chips & Semiconductors": {
        "keywords": [
            "gpu", "chip", "semiconductor", "nvdia", "amd chip", "inference",
            "training chip", "ai accelerator", "hbm memory", "chip shortage",
            "foundry", "wafer", "tsmc", "advanced packaging",
        ],
        "tickers": ["NVDA", "AMD", "TSM", "ASML", "AMAT", "LRCX", "SMCI", "MU"],
        "description": (
            "The core AI hardware theme — GPUs, memory chips, and chipmaking equipment. "
            "This was the dominant theme in 2023–2024. "
            "Watch for shifts if AI inference moves to custom silicon."
        ),
        "trend_query": "AI semiconductor chips",
    },
    "AI Software & Applications": {
        "keywords": [
            "ai agent", "copilot", "llm", "large language model", "openai",
            "anthropic", "gemini", "agentic", "ai application", "ai platform",
            "ai workflow", "enterprise ai", "ai software",
        ],
        "tickers": ["MSFT", "GOOGL", "META", "CRM", "NOW", "ADBE", "ORCL", "PLTR"],
        "description": (
            "Software companies embedding AI into products — "
            "Microsoft Copilot, Salesforce Einstein, ServiceNow, etc. "
            "This theme picks up when hardware investment matures and apps layer on top."
        ),
        "trend_query": "AI software enterprise",
    },
    "Cloud Infrastructure": {
        "keywords": [
            "cloud spending", "cloud growth", "aws", "azure", "google cloud",
            "cloud migration", "cloud revenue", "hyperscaler capex",
            "cloud infrastructure", "cloud contract",
        ],
        "tickers": ["AMZN", "MSFT", "GOOGL", "SNOW", "DDOG", "NET", "MDB"],
        "description": (
            "Cloud spending is the highway AI runs on. "
            "When hyperscalers (AWS, Azure, GCP) report strong capex guidance, "
            "the entire cloud ecosystem benefits."
        ),
        "trend_query": "cloud computing spending",
    },
    "Defense & National Security": {
        "keywords": [
            "defense contract", "military ai", "drone warfare", "pentagon budget",
            "national security", "defense spending", "weapons system",
            "autonomous weapon", "cyber warfare", "missile defense",
        ],
        "tickers": ["PLTR", "RTX", "LMT", "NOC", "ANSS", "BWXT", "KTOS"],
        "description": (
            "Geopolitical tensions drive defense budgets higher. "
            "AI + defense convergence is a growing theme — drones, autonomous systems, "
            "and intelligence software are all benefiting."
        ),
        "trend_query": "AI defense military spending",
    },
    "Cybersecurity": {
        "keywords": [
            "cyberattack", "ransomware", "data breach", "hack", "zero-day",
            "cybersecurity spending", "identity threat", "soc", "endpoint security",
            "cloud security", "network security",
        ],
        "tickers": ["CRWD", "PANW", "ZS", "FTNT", "S", "OKTA"],
        "description": (
            "Every AI expansion creates new attack surfaces. "
            "Cybersecurity spending grows every time a major breach hits the news. "
            "Watch for headline attacks — they spike CRWD, PANW, ZS."
        ),
        "trend_query": "cybersecurity breach attack",
    },
    "Robotics & Automation": {
        "keywords": [
            "humanoid robot", "factory automation", "robot", "autonomous vehicle",
            "self-driving", "automation", "cobots", "industrial ai",
            "manufacturing ai", "robotaxi",
        ],
        "tickers": ["TSLA", "ABB", "HON", "ROK", "ISRG", "URI"],
        "description": (
            "Physical AI — robots, automation, and autonomous systems. "
            "Tesla Optimus, humanoid robots, and factory automation are growing narratives "
            "as labor costs rise and AI capabilities mature."
        ),
        "trend_query": "humanoid robot automation",
    },
    "Biotech & Healthcare AI": {
        "keywords": [
            "drug discovery", "ai drug", "biotech", "fda approval", "clinical trial",
            "genomics", "precision medicine", "weight loss drug", "glp-1",
            "cancer treatment", "mRNA",
        ],
        "tickers": ["LLY", "NVO", "MRNA", "GILD", "AMGN", "VRTX", "RXRX"],
        "description": (
            "AI accelerating drug discovery + weight loss drugs (GLP-1) dominating headlines. "
            "Eli Lilly and Novo Nordisk have become trillion-dollar companies on this theme."
        ),
        "trend_query": "AI drug discovery biotech",
    },
    "Tariffs & Trade War": {
        "keywords": [
            "tariff", "trade war", "import duty", "export ban", "china supply chain",
            "reshoring", "supply chain", "trade policy", "sanctions",
            "decoupling", "friend-shoring",
        ],
        "tickers": ["AAPL", "TSM", "INTC", "MU", "QCOM", "AMAT"],
        "description": (
            "Trade tensions between US and China directly impact tech supply chains. "
            "Chip export bans, tariffs on electronics, and reshoring mandates "
            "create winners and losers fast."
        ),
        "trend_query": "tariffs trade war technology",
    },
}


def _scan_google_news(query: str, limit: int = 20) -> list[str]:
    """Fetch Google News RSS headlines for a theme query."""
    try:
        q   = query.replace(" ", "+")
        url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url)
        return [e.get("title", "") for e in feed.entries[:limit]]
    except Exception:
        return []


def _scan_reddit_rss(limit: int = 50) -> list[str]:
    """Fetch hot post titles from r/investing and r/stocks."""
    titles = []
    for sub in ["investing", "stocks", "wallstreetbets"]:
        try:
            resp = requests.get(
                f"https://www.reddit.com/r/{sub}/hot.json?limit=25",
                headers=HEADERS, timeout=8,
            )
            if resp.status_code == 200:
                posts = resp.json()["data"]["children"]
                titles += [p["data"]["title"] for p in posts]
            else:
                feed = feedparser.parse(f"https://www.reddit.com/r/{sub}/hot.rss")
                titles += [e.title for e in feed.entries[:25]]
        except Exception:
            pass
    return titles[:limit]


def _count_keyword_hits(texts: list[str], keywords: list[str]) -> int:
    """Count how many texts contain at least one keyword."""
    hits = 0
    for text in texts:
        text_lower = text.lower()
        if any(kw.lower() in text_lower for kw in keywords):
            hits += 1
    return hits


def _get_trend_score(query: str) -> int:
    """
    Google Trends score for the query over last 7 days.
    Returns 0-100 (relative interest). Returns 0 on failure.
    """
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=360, timeout=(5, 15))
        pt.build_payload([query[:100]], timeframe="now 7-d", geo="US")
        df = pt.interest_over_time()
        if df is None or df.empty:
            return 0
        col = [c for c in df.columns if c != "isPartial"]
        if not col:
            return 0
        return int(df[col[0]].mean())
    except Exception:
        return 0


def score_themes(use_trends: bool = True) -> list[dict]:
    """
    Score all themes by current news + Reddit + Google Trends activity.

    Returns list of theme dicts sorted by score descending:
    {
        name, score, momentum_label, headline_hits, reddit_hits,
        trend_score, tickers, description, top_headlines
    }
    """
    logger.info("Scoring investment themes…")
    reddit_titles = _scan_reddit_rss()
    results = []

    for name, theme in THEMES.items():
        keywords   = theme["keywords"]
        tickers    = theme["tickers"]

        # Headline hits from Google News
        news_titles    = _scan_google_news(theme["trend_query"], limit=20)
        news_hits      = _count_keyword_hits(news_titles, keywords)

        # Reddit hits
        reddit_hits    = _count_keyword_hits(reddit_titles, keywords)

        # Google Trends (optional — can be slow/rate-limited)
        trend_score    = _get_trend_score(theme["trend_query"]) if use_trends else 0

        # Composite score: news most important, then trends, then reddit
        composite = min(100, news_hits * 8 + reddit_hits * 5 + trend_score // 5)

        # Momentum label
        if composite >= 60:
            momentum = "🚀 Very Hot"
        elif composite >= 35:
            momentum = "🔥 Heating Up"
        elif composite >= 15:
            momentum = "💬 Active"
        else:
            momentum = "🔇 Quiet"

        # Top relevant headlines
        top_headlines = [
            t for t in (news_titles + reddit_titles)
            if any(kw.lower() in t.lower() for kw in keywords)
        ][:3]

        results.append({
            "name":          name,
            "score":         composite,
            "momentum":      momentum,
            "news_hits":     news_hits,
            "reddit_hits":   reddit_hits,
            "trend_score":   trend_score,
            "tickers":       tickers,
            "description":   theme["description"],
            "top_headlines": top_headlines,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    logger.info(f"Theme scores: { {r['name'][:20]: r['score'] for r in results[:4]} }")
    return results


def format_themes_report(results: list[dict], top_n: int = 5) -> str:
    """Format top N themes as an HTML Telegram message."""
    import html as _h
    lines = [
        "<b>📡 MARKET NARRATIVE TRACKER</b>",
        "<i>What institutional &amp; retail investors are focusing on right now</i>",
        "─────────────────────",
        "",
    ]

    for i, t in enumerate(results[:top_n], 1):
        tickers_str = "  ".join(f"<b>{_h.escape(tk)}</b>" for tk in t["tickers"][:5])
        lines += [
            f"<b>{i}. {_h.escape(t['name'])}</b>  {t['momentum']}",
            f"   {tickers_str}",
            f"   <i>{_h.escape(t['description'][:120])}…</i>",
        ]
        if t["top_headlines"]:
            lines.append(f"   📰 {_h.escape(t['top_headlines'][0][:90])}")
        lines.append("")

    lines += [
        "─────────────────────",
        "<i>Tap 📡 Narrative Tracker in /market for live updates</i>",
        "/analyze &lt;TICKER&gt; to deep-dive any stock above",
    ]
    return "\n".join(lines)


def get_top_theme_tickers(top_n_themes: int = 3) -> list[str]:
    """
    Return tickers from the top N hottest themes.
    Used by get_dynamic_tickers() to inject theme-relevant stocks into movers scan.
    Skips Google Trends (too slow for this use case).
    """
    try:
        results = score_themes(use_trends=False)
        tickers = []
        seen    = set()
        for theme in results[:top_n_themes]:
            for t in theme["tickers"]:
                if t not in seen:
                    seen.add(t)
                    tickers.append(t)
        return tickers
    except Exception as e:
        logger.warning(f"get_top_theme_tickers failed: {e}")
        return []
