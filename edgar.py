"""SEC EDGAR free data — 8-K material event filings and Form 4 insider transactions."""
import logging, feedparser
logger = logging.getLogger(__name__)

def get_8k_filings(ticker: str, limit: int = 5) -> list:
    """8-K = material events companies must disclose same day (earnings, mergers, exec changes)."""
    url = (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&ticker={ticker}"
           f"&type=8-K&dateb=&owner=include&count={limit}&search_text=&output=atom")
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "StockBot research@stockbot.com"})
        import urllib.error
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read()
        feed = feedparser.parse(content)
        return [{"title": e.get("title",""), "date": e.get("updated","")[:10], "link": e.get("link","")} for e in feed.entries[:limit]]
    except Exception as ex:
        logger.warning(f"[{ticker}] EDGAR 8-K: {ex}"); return []

def get_insider_trades(ticker: str, limit: int = 8) -> list:
    """Form 4 = insider buy/sell within 2 business days of transaction."""
    url = (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&ticker={ticker}"
           f"&type=4&dateb=&owner=include&count={limit}&search_text=&output=atom")
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "StockBot research@stockbot.com"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read()
        feed = feedparser.parse(content)
        items = []
        for e in feed.entries[:limit]:
            title = e.get("title","")
            title_l = title.lower()
            direction = "buy" if any(w in title_l for w in ["purchase","acquired","exercised"]) else "sell"
            items.append({"title": title, "date": e.get("updated","")[:10], "link": e.get("link",""), "direction": direction})
        return items
    except Exception as ex:
        logger.warning(f"[{ticker}] EDGAR Form 4: {ex}"); return []

def format_edgar_report(ticker: str) -> str:
    import html as _h
    t = _h.escape(ticker)
    filings  = get_8k_filings(ticker)
    insiders = get_insider_trades(ticker)
    lines = [f"<b>📋 SEC FILINGS — {t}</b>",
             "<i>Official disclosures from SEC EDGAR — legally required, same-day</i>",
             "─────────────────────", ""]
    if filings:
        lines.append("<b>Recent 8-K Filings</b>  <i>(material events: earnings, mergers, exec changes)</i>")
        for f in filings[:4]:
            title = _h.escape(f["title"][:85])
            if f["link"]:
                lines.append(f'  • <a href="{_h.escape(f["link"])}">{title}</a>  <i>{f["date"]}</i>')
            else:
                lines.append(f"  • {title}  <i>{f['date']}</i>")
        lines.append("")
    if insiders:
        buys  = [i for i in insiders if i["direction"] == "buy"]
        sells = [i for i in insiders if i["direction"] == "sell"]
        lines.append(f"<b>Insider Transactions (Form 4)</b>  <i>🟢 {len(buys)} buys · 🔴 {len(sells)} sells</i>")
        for i in insiders[:5]:
            emoji = "🟢" if i["direction"] == "buy" else "🔴"
            title = _h.escape(i["title"][:80])
            if i["link"]:
                lines.append(f'  {emoji} <a href="{_h.escape(i["link"])}">{title}</a>  <i>{i["date"]}</i>')
            else:
                lines.append(f"  {emoji} {title}  <i>{i['date']}</i>")
        if len(buys) >= len(sells) * 2 and len(buys) >= 2:
            lines.append("  <i>🟢 Net insider buying — strong management confidence signal</i>")
        elif len(sells) >= len(buys) * 2 and len(sells) >= 2:
            lines.append("  <i>🔴 Net insider selling — monitor carefully</i>")
        lines.append("")
    if not filings and not insiders:
        lines.append("  No recent SEC filings found.")
    lines += ["", f"/analyze {ticker}  ·  /political {ticker}"]
    return "\n".join(lines)
