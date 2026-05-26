"""
Market context module — free data sources only.
Provides: SPY/QQQ benchmarks, Fear & Greed Index, Sector ETF comparison, Macro calendar.
"""
import logging
import time
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

# Sector ETFs — compared against individual sector stocks
SECTOR_ETFS = {
    "AI":             "QQQ",   # Nasdaq — best proxy for AI/tech
    "Semiconductors": "SMH",   # VanEck Semiconductor ETF
    "Cloud":          "WCLD",  # WisdomTree Cloud Computing ETF
    "Software":       "IGV",   # iShares Expanded Tech-Software ETF
}

BENCHMARKS = ["SPY", "QQQ"]   # S&P 500 + Nasdaq 100


def get_market_benchmarks() -> dict:
    """
    Fetch SPY and QQQ — the two most important market benchmarks.
    If SPY is down 1.5%, most of your stocks will follow. Check this FIRST.
    """
    results = {}
    for ticker in BENCHMARKS:
        try:
            hist = yf.download(ticker, period="5d", auto_adjust=True,
                               progress=False, timeout=10)
            if hist.empty:
                continue
            if hasattr(hist.columns, "levels"):
                hist.columns = hist.columns.get_level_values(0)

            price      = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2])
            chg        = round((price - prev_close) / prev_close * 100, 2)

            # 5-day trend (is the market in a short-term up or down move?)
            price_5d = float(hist["Close"].iloc[0])
            trend_5d = round((price - price_5d) / price_5d * 100, 2)

            results[ticker] = {
                "price":    round(price, 2),
                "chg":      chg,
                "trend_5d": trend_5d,
            }
            logger.info(f"[{ticker}] ${price:.2f} ({chg:+.2f}%)")
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"[{ticker}] Benchmark fetch failed: {e}")

    return results


def get_sector_etf_performance() -> dict:
    """
    Fetch today's performance of sector ETFs.
    Compare individual stocks against these to see if they're leading or lagging their sector.
    """
    results = {}
    for sector, etf in SECTOR_ETFS.items():
        try:
            hist = yf.download(etf, period="5d", auto_adjust=True,
                               progress=False, timeout=10)
            if hist.empty:
                continue
            if hasattr(hist.columns, "levels"):
                hist.columns = hist.columns.get_level_values(0)

            price      = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2])
            chg        = round((price - prev_close) / prev_close * 100, 2)

            results[sector] = {"etf": etf, "chg": chg, "price": round(price, 2)}
            logger.info(f"[{etf}] Sector ETF for {sector}: {chg:+.2f}%")
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"[{etf}] Sector ETF fetch failed: {e}")

    return results


def get_fear_greed() -> dict:
    """
    Fetch CNN Fear & Greed Index (0-100).
    < 25 = Extreme Fear (historically good time to buy)
    > 75 = Extreme Greed (historically good time to be cautious)
    Free, no API key.
    """
    try:
        url  = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = resp.json()
        score = int(data["fear_and_greed"]["score"])
        rating = data["fear_and_greed"]["rating"].replace("_", " ").title()

        if score <= 25:
            emoji = "😱"
            advice = "Extreme Fear — historically a buying opportunity"
        elif score <= 45:
            emoji = "😨"
            advice = "Fear — market may be oversold"
        elif score <= 55:
            emoji = "😐"
            advice = "Neutral — no strong market-wide signal"
        elif score <= 75:
            emoji = "😏"
            advice = "Greed — be selective, don't chase"
        else:
            emoji = "🤑"
            advice = "Extreme Greed — consider reducing risk"

        logger.info(f"Fear & Greed: {score} ({rating})")
        return {
            "score":   score,
            "rating":  rating,
            "emoji":   emoji,
            "advice":  advice,
            "available": True,
        }
    except Exception as e:
        logger.warning(f"Fear & Greed fetch failed: {e}")
        return {"available": False}


def get_macro_calendar() -> list:
    """
    Returns upcoming macro events for the week (hardcoded weekly schedule).
    In reality these change weekly — this gives a structural reminder.
    Real macro calendars require paid APIs, so we provide a useful static guide.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    CT = ZoneInfo("America/Chicago")
    weekday = datetime.now(CT).weekday()

    # Fixed weekly schedule of common macro events
    WEEKLY_EVENTS = {
        0: ["🏦 Fed speakers often scheduled — watch for rate hints"],
        1: ["📊 Consumer Confidence (monthly, ~last Tue of month)"],
        2: ["📊 ADP Jobs Report (monthly) — preview of Friday NFP",
            "🏦 FOMC meeting possible (8x/year) — biggest market mover"],
        3: ["📊 Weekly Jobless Claims — labor market health",
            "📈 GDP data (quarterly)"],
        4: ["📊 Non-Farm Payrolls (first Fri of month) — major market mover",
            "📊 CPI / PPI inflation data (monthly) — Fed's key input"],
    }

    events = WEEKLY_EVENTS.get(weekday, [])
    if not events:
        events = ["No major scheduled macro events today"]
    return events


def format_market_context(benchmarks: dict, fear_greed: dict, sector_etfs: dict) -> str:
    """Format market context into a clean Telegram header for morning brief."""
    lines = [
        "🌍 *MARKET CONTEXT*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "_Read this before anything else — market direction affects ALL stocks_",
        "",
    ]

    # SPY / QQQ
    if benchmarks:
        lines.append("📊 *Overall Market:*")
        for ticker, d in benchmarks.items():
            emoji    = "📈" if d["chg"] >= 0 else "📉"
            trend_5d = f"  |  5-day: {d['trend_5d']:+.1f}%"
            label    = "S&P 500 (whole market)" if ticker == "SPY" else "Nasdaq 100 (tech-heavy)"
            lines.append(f"  {emoji} *{ticker}* ${d['price']} ({d['chg']:+.2f}%){trend_5d}")
            lines.append(f"     _{label}_")

        # Market mood based on SPY
        spy = benchmarks.get("SPY", {})
        qqq = benchmarks.get("QQQ", {})
        if spy and qqq:
            if spy["chg"] < -1.5:
                lines.append("\n  🚨 *Risk-off day* — market down sharply. Most stocks will follow. Be cautious.")
            elif spy["chg"] < -0.5:
                lines.append("\n  ⚠️ *Weak market* — headwinds today. Only highest-conviction setups.")
            elif spy["chg"] > 1.5:
                lines.append("\n  🚀 *Strong market* — rising tide. Momentum stocks may run further.")
            elif spy["chg"] > 0.5:
                lines.append("\n  🟢 *Positive market* — favorable conditions for long positions.")
            else:
                lines.append("\n  🟡 *Flat market* — stock-specific news will drive individual moves.")

    # Fear & Greed
    if fear_greed.get("available"):
        fg = fear_greed
        lines += [
            "",
            f"😱 *Fear & Greed Index:* {fg['score']}/100 — {fg['emoji']} {fg['rating']}",
            f"   _{fg['advice']}_",
            "   _0=Extreme Fear, 100=Extreme Greed_",
        ]

    # Sector ETF comparison
    if sector_etfs:
        lines += ["", "🏭 *Sector ETFs Today:*",
                  "_If your stock lags its ETF, it's underperforming the sector_", ""]
        for sector, d in sector_etfs.items():
            emoji = "📈" if d["chg"] >= 0 else "📉"
            lines.append(f"  {emoji} *{d['etf']}* ({sector}) {d['chg']:+.2f}%")

    lines.append("")
    return "\n".join(lines)
