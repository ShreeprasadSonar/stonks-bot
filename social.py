"""
Social signal aggregator — four free sources, no API keys required.

Sources:
  1. Reddit RSS       — r/wallstreetbets, r/stocks, r/investing
  2. Google Trends    — search interest spikes via pytrends
  3. Congress Trades  — housestockwatcher.com + senatestockwatcher.com
  4. Finviz           — analyst upgrades/downgrades, insider transactions
"""
import logging
import re
import time
import feedparser
import requests

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# ─────────────────────────────────────────────────────────────────────────────
# 1. REDDIT RSS
# ─────────────────────────────────────────────────────────────────────────────

SUBREDDITS = ["wallstreetbets", "stocks", "investing", "StockMarket"]

BULLISH_WORDS = ["buy", "bull", "calls", "long", "breakout", "moon", "squeeze",
                 "upgrade", "beat", "surge", "rally", "undervalued"]
BEARISH_WORDS = ["sell", "bear", "puts", "short", "crash", "overvalued",
                 "miss", "downgrade", "dump", "warn", "drop", "decline"]


def get_reddit_mentions(ticker: str) -> dict:
    """
    Scan r/wallstreetbets, r/stocks, r/investing RSS for ticker mentions.
    No API key — uses public .json and RSS endpoints.
    Returns mention count, sentiment, and top post titles.
    """
    ticker_up   = ticker.upper()
    mention_cnt = 0
    bull_score  = 0
    bear_score  = 0
    top_posts   = []

    # Pattern: standalone ticker (e.g. $NVDA or NVDA not inside a word)
    pattern = re.compile(r'(?<![A-Z$])(\$?' + re.escape(ticker_up) + r')(?![A-Z])')

    for sub in SUBREDDITS:
        try:
            url  = f"https://www.reddit.com/r/{sub}/hot.json?limit=25"
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code != 200:
                # fall back to RSS
                feed = feedparser.parse(f"https://www.reddit.com/r/{sub}/hot.rss")
                posts = [{"title": e.title, "url": e.link} for e in feed.entries[:25]]
            else:
                data  = resp.json()
                posts = [
                    {"title": p["data"]["title"], "url": "https://reddit.com" + p["data"]["permalink"]}
                    for p in data["data"]["children"]
                ]
        except Exception as e:
            logger.debug(f"Reddit RSS {sub} failed: {e}")
            continue

        for post in posts:
            title = post["title"].upper()
            if pattern.search(title):
                mention_cnt += 1
                title_lower  = post["title"].lower()
                bull_score  += sum(1 for w in BULLISH_WORDS if w in title_lower)
                bear_score  += sum(1 for w in BEARISH_WORDS if w in title_lower)
                if len(top_posts) < 3:
                    top_posts.append({"title": post["title"][:100], "url": post["url"], "sub": sub})

        time.sleep(0.2)  # be polite

    if bull_score > bear_score * 1.3:
        sentiment = "🟢 Bullish"
    elif bear_score > bull_score * 1.3:
        sentiment = "🔴 Bearish"
    else:
        sentiment = "🟡 Mixed"

    hype = "🚀 High buzz" if mention_cnt >= 5 else ("🔥 Active" if mention_cnt >= 2 else "🔇 Quiet")

    logger.info(f"[{ticker}] Reddit mentions={mention_cnt}, bull={bull_score}, bear={bear_score}")
    return {
        "mentions":   mention_cnt,
        "sentiment":  sentiment,
        "hype":       hype,
        "top_posts":  top_posts,
        "bull":       bull_score,
        "bear":       bear_score,
    }


def get_reddit_hot_tickers(limit: int = 10) -> list[dict]:
    """
    Return list of tickers most-mentioned in r/wallstreetbets hot posts right now.
    Used for morning brief "what WSB is watching today".
    """
    from collections import Counter
    ticker_pat = re.compile(r'\$([A-Z]{1,5})\b')
    counts     = Counter()
    posts_map  = {}

    for sub in ["wallstreetbets", "stocks"]:
        try:
            url  = f"https://www.reddit.com/r/{sub}/hot.json?limit=50"
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code != 200:
                continue
            for post in resp.json()["data"]["children"]:
                title = post["data"]["title"]
                for m in ticker_pat.findall(title.upper()):
                    # Skip common false positives
                    if m in {"A", "I", "IT", "BE", "OR", "AT", "IS", "SO", "ON", "IF", "DO"}:
                        continue
                    counts[m] += 1
                    if m not in posts_map:
                        posts_map[m] = title[:80]
            time.sleep(0.3)
        except Exception as e:
            logger.debug(f"Hot tickers from {sub}: {e}")

    return [
        {"ticker": t, "mentions": c, "sample_post": posts_map.get(t, "")}
        for t, c in counts.most_common(limit)
        if c >= 2
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 2. GOOGLE TRENDS
# ─────────────────────────────────────────────────────────────────────────────

def get_google_trends(ticker: str) -> dict:
    """
    Returns Google Trends search interest for ticker over last 7 days.
    A spike (>150% of baseline) is a strong retail attention signal.
    Requires: pip install pytrends
    """
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=360, timeout=(5, 15))
        pt.build_payload([ticker], timeframe="now 7-d", geo="US")
        df = pt.interest_over_time()

        if df is None or df.empty or ticker not in df.columns:
            return {"available": False, "note": "No Trends data"}

        values  = df[ticker].tolist()
        current = values[-1] if values else 0
        avg     = sum(values) / len(values) if values else 1
        peak    = max(values) if values else 0
        ratio   = current / avg if avg > 0 else 1

        if ratio >= 2.0:
            signal = "🚀 Search spike — 2x+ normal"
        elif ratio >= 1.4:
            signal = "🔥 Rising searches"
        elif ratio <= 0.5:
            signal = "🔇 Below average interest"
        else:
            signal = "🟡 Normal search volume"

        logger.info(f"[{ticker}] Google Trends current={current}, avg={avg:.1f}, ratio={ratio:.2f}")
        return {
            "available": True,
            "current":   current,
            "avg_7d":    round(avg, 1),
            "peak_7d":   peak,
            "ratio":     round(ratio, 2),
            "signal":    signal,
        }

    except Exception as e:
        logger.warning(f"[{ticker}] Google Trends error: {e}")
        return {"available": False, "note": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# 3. CONGRESSIONAL STOCK TRADES
# ─────────────────────────────────────────────────────────────────────────────

HOUSE_URL  = "https://house-stock-watcher-data.s3-us-gov-west-1.amazonaws.com/data/all_transactions.json"
SENATE_URL = "https://efts.sec.gov/LATEST/search-index?q=%22congress%22&dateRange=custom&startdt=2024-01-01&enddt=2099-01-01&forms=4"

# Simple direct endpoint from senatestockwatcher.com
SENATE_TRADES_URL = "https://senate-stock-watcher-data.s3-us-gov-west-1.amazonaws.com/aggregate/all_transactions.json"


def get_congress_trades(ticker: str, recent_days: int = 90) -> list[dict]:
    """
    Fetch recent House + Senate stock trades for a ticker.
    Data from housestockwatcher.com and senatestockwatcher.com — both free, no auth.
    Returns list of {name, chamber, trade_type, amount, date, party}.
    """
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=recent_days)
    trades = []

    # House trades
    try:
        resp = requests.get(HOUSE_URL, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            for t in resp.json():
                sym = (t.get("ticker") or "").strip().upper().lstrip("$")
                if sym != ticker.upper():
                    continue
                try:
                    trade_date = datetime.strptime(t["transaction_date"], "%Y-%m-%d")
                except Exception:
                    continue
                if trade_date < cutoff:
                    continue
                trades.append({
                    "name":    t.get("representative", "Unknown"),
                    "chamber": "House",
                    "type":    t.get("type", "?").capitalize(),
                    "amount":  t.get("amount", "?"),
                    "date":    t["transaction_date"],
                    "party":   t.get("party", "?"),
                })
    except Exception as e:
        logger.debug(f"House trades error: {e}")

    # Senate trades
    try:
        resp = requests.get(SENATE_TRADES_URL, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            for t in resp.json():
                sym = (t.get("ticker") or "").strip().upper().lstrip("$")
                if sym != ticker.upper():
                    continue
                try:
                    trade_date = datetime.strptime(t["transaction_date"], "%Y-%m-%d")
                except Exception:
                    continue
                if trade_date < cutoff:
                    continue
                trades.append({
                    "name":    t.get("senator", "Unknown"),
                    "chamber": "Senate",
                    "type":    t.get("type", "?").capitalize(),
                    "amount":  t.get("amount", "?"),
                    "date":    t["transaction_date"],
                    "party":   t.get("party", "?"),
                })
    except Exception as e:
        logger.debug(f"Senate trades error: {e}")

    trades.sort(key=lambda x: x["date"], reverse=True)
    logger.info(f"[{ticker}] Congress trades found: {len(trades)}")
    return trades[:10]


def format_congress_trades(ticker: str, trades: list[dict]) -> str:
    """Format congress trades as clean HTML."""
    import html as _h
    if not trades:
        return f"<b>Congress Trades — {_h.escape(ticker)}</b>\n\nNo recent trades in the last 90 days."

    lines = [
        f"<b>Congress Trades — {_h.escape(ticker)}</b>",
        "<i>Last 90 days  ·  House + Senate</i>",
        "─────────────────────",
        "",
    ]
    for t in trades:
        trade_emoji = "🟢" if "purchase" in t["type"].lower() or "buy" in t["type"].lower() else "🔴"
        lines.append(
            f"{trade_emoji} <b>{_h.escape(t['name'])}</b>  ({_h.escape(t['chamber'])})\n"
            f"   {_h.escape(t['type'])}  ·  {_h.escape(t['amount'])}  ·  {t['date']}"
        )

    buy_count  = sum(1 for t in trades if "purchase" in t["type"].lower() or "buy" in t["type"].lower())
    sell_count = len(trades) - buy_count

    lines += [
        "",
        "─────────────────────",
        f"  🟢 Buys: <b>{buy_count}</b>  ·  🔴 Sells: <b>{sell_count}</b>",
    ]
    if buy_count > sell_count * 2:
        lines.append("  <b>Congress is net-buying</b> — historically bullish signal")
    elif sell_count > buy_count * 2:
        lines.append("  <b>Congress is net-selling</b> — watch closely")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 4. FINVIZ — Analyst upgrades/downgrades + insider transactions
# ─────────────────────────────────────────────────────────────────────────────

def get_finviz_signals(ticker: str) -> dict:
    """
    Scrape Finviz for analyst ratings and insider transaction data.
    Free, no API key. Returns ratings, price target, and insider activity.
    """
    from bs4 import BeautifulSoup

    url = f"https://finviz.com/quote.ashx?t={ticker.upper()}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return {"available": False}

        soup = BeautifulSoup(resp.text, "html.parser")

        # Analyst ratings table
        ratings = []
        for row in soup.select("table.fullview-ratings-outer tr"):
            cols = [c.get_text(strip=True) for c in row.select("td")]
            if len(cols) >= 4:
                ratings.append({
                    "date":   cols[0],
                    "action": cols[1],
                    "firm":   cols[2],
                    "from":   cols[3],
                    "to":     cols[4] if len(cols) > 4 else "",
                })

        # Price target and recommendation from snapshot table
        target = ""
        recom  = ""
        for row in soup.select("table.snapshot-table2 tr"):
            for i, cell in enumerate(row.select("td")):
                text = cell.get_text(strip=True)
                if text == "Target Price":
                    sibling = row.select("td")[i + 1]
                    target  = sibling.get_text(strip=True)
                if text == "Recom":
                    sibling = row.select("td")[i + 1]
                    recom   = sibling.get_text(strip=True)

        # Insider transactions
        insiders = []
        for row in soup.select("table.body-table tr")[1:6]:
            cols = [c.get_text(strip=True) for c in row.select("td")]
            if len(cols) >= 6:
                insiders.append({
                    "name":   cols[0],
                    "rel":    cols[1],
                    "date":   cols[2],
                    "action": cols[3],
                    "shares": cols[4],
                    "value":  cols[5],
                })

        logger.info(f"[{ticker}] Finviz: {len(ratings)} ratings, target={target}, {len(insiders)} insider txns")
        return {
            "available": True,
            "ratings":   ratings[:5],
            "target":    target,
            "recom":     recom,
            "insiders":  insiders,
        }

    except Exception as e:
        logger.warning(f"[{ticker}] Finviz scrape error: {e}")
        return {"available": False, "note": str(e)}


def format_finviz_signals(ticker: str, data: dict) -> str:
    """Format Finviz analyst + insider data as HTML."""
    import html as _h
    t = _h.escape(ticker)

    if not data.get("available"):
        return f"<b>Analyst Signals — {t}</b>\n\nData unavailable."

    lines = [
        f"<b>Analyst Signals — {t}</b>",
        "─────────────────────",
        "",
    ]

    if data.get("target") or data.get("recom"):
        lines.append("<b>Consensus</b>")
        if data.get("recom"):
            lines.append(f"  Rating:  <b>{_h.escape(data['recom'])}</b>")
        if data.get("target"):
            lines.append(f"  Target:  <b>${_h.escape(data['target'])}</b>")
        lines.append("")

    if data.get("ratings"):
        lines.append("<b>Recent Analyst Actions</b>")
        for r in data["ratings"]:
            action = _h.escape(r["action"])
            firm   = _h.escape(r["firm"])
            to_    = _h.escape(r["to"]) if r["to"] else ""
            arrow  = f" → {to_}" if to_ else ""
            lines.append(f"  {r['date']}  <b>{firm}</b>  {action}{arrow}")
        lines.append("")

    if data.get("insiders"):
        lines.append("<b>Insider Transactions</b>")
        for ins in data["insiders"]:
            action = ins["action"].lower()
            emoji  = "🟢" if "buy" in action or "purch" in action else "🔴"
            lines.append(
                f"  {emoji} <b>{_h.escape(ins['name'])}</b>  ({_h.escape(ins['rel'])})\n"
                f"     {_h.escape(ins['action'])}  ·  {_h.escape(ins['shares'])} shares  ·  ${_h.escape(ins['value'])}"
            )

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Combined: full social intelligence report for /social command
# ─────────────────────────────────────────────────────────────────────────────

def get_full_social_report(ticker: str) -> str:
    """
    Build the complete social intelligence report for a ticker.
    Combines Reddit, Google Trends, Congress trades, and Finviz.
    """
    import html as _h
    t = _h.escape(ticker.upper())

    lines = [
        f"<b>📡 {t} — Social Intelligence</b>",
        "─────────────────────",
        "",
    ]

    # ── Reddit Activity ───────────────────────────────────────
    reddit = get_reddit_mentions(ticker)
    sentiment_emoji = "🟢" if "bullish" in reddit["sentiment"].lower() else ("🔴" if "bearish" in reddit["sentiment"].lower() else "🟡")
    lines += [
        f"💬 <b>Reddit</b>  ·  {reddit['mentions']} mentions  ·  {sentiment_emoji} {reddit['sentiment']}",
    ]
    if reddit["top_posts"]:
        for p in reddit["top_posts"][:2]:
            title = _h.escape(p["title"][:80])
            url   = p.get("url", "")
            sub   = _h.escape(p.get("sub", ""))
            if url:
                lines.append(f'  • <a href="{url}">{title}</a>  <i>r/{sub}</i>')
            else:
                lines.append(f"  • {title}  <i>r/{sub}</i>")
    lines.append("")

    # ── Google Trends ─────────────────────────────────────────
    trends = get_google_trends(ticker)
    if trends.get("available"):
        lines += [
            f"📈 <b>Google Trends</b>  ·  {trends['signal']}",
            f"  Interest: <b>{trends['current']}</b> vs {trends['avg_7d']} avg  ·  {trends['ratio']}x baseline",
            "",
        ]
    else:
        lines += [f"📈 <b>Google Trends</b>  ·  <i>unavailable</i>", ""]

    # ── Congressional Trades ──────────────────────────────────
    trades = get_congress_trades(ticker)
    if trades:
        buy_cnt  = sum(1 for tr in trades if "purch" in tr["type"].lower() or "buy" in tr["type"].lower())
        sell_cnt = len(trades) - buy_cnt
        net_label = "Net buying 🟢" if buy_cnt > sell_cnt else ("Net selling 🔴" if sell_cnt > buy_cnt else "Balanced 🟡")
        lines += [
            f"🏛️ <b>Congress Trades</b>  ·  {net_label}  ·  {len(trades)} total",
            f"  🟢 {buy_cnt} buys  ·  🔴 {sell_cnt} sells  (last 90 days)",
        ]
        for tr in trades[:3]:
            emoji = "🟢" if "purch" in tr["type"].lower() or "buy" in tr["type"].lower() else "🔴"
            lines.append(f"  {emoji} <b>{_h.escape(tr['name'])}</b> ({tr['chamber']})  {_h.escape(tr['type'])}  ·  {tr['date']}")
        lines.append("")
    else:
        lines += [f"🏛️ <b>Congress Trades</b>  ·  <i>none in last 90 days</i>", ""]

    # ── Analyst Consensus ─────────────────────────────────────
    fv = get_finviz_signals(ticker)
    if fv.get("available"):
        recom  = _h.escape(fv.get("recom", ""))
        target = fv.get("target", "")
        header_parts = []
        if recom:  header_parts.append(f"<b>{recom}</b>")
        if target: header_parts.append(f"target ${_h.escape(target)}")
        lines.append(f"🔬 <b>Analysts</b>  ·  {' · '.join(header_parts)}")
        for r in fv["ratings"][:3]:
            action = _h.escape(r.get("action", ""))
            firm   = _h.escape(r.get("firm", ""))
            pt     = r.get("price_target", "")
            pt_str = f" → ${_h.escape(str(pt))}" if pt and pt != "0" else ""
            lines.append(f"  {r['date']}  <b>{firm}</b>  {action}{pt_str}")
        lines.append("")
    else:
        lines += [f"🔬 <b>Analysts</b>  ·  <i>data unavailable</i>", ""]

    lines += [
        "─────────────────────",
        f"/analyze {ticker}  ·  /political {ticker}",
    ]

    return "\n".join(lines)
