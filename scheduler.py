"""
Scheduled alert sender — called by GitHub Actions cron (alerts.yml).
Morning brief: full market overview with news + Reddit + political signals.
Closing report: day summary with gainers/losers + sentiment.
All times in Central Time (Chicago).
"""
import asyncio
import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Bot
from telegram.constants import ParseMode

from config import TELEGRAM_TOKEN, SECTORS
from fetcher import get_top_movers, get_stock_info
from technical import get_technical_signals
from news import get_news
from sentiment import score_news
from market_context import (
    get_market_benchmarks, get_fear_greed,
    get_sector_etf_performance, get_macro_calendar, format_market_context,
)

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s — %(message)s", level=logging.INFO)
logging.getLogger("yfinance").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("scheduler")

CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CT = ZoneInfo("America/Chicago")

# Key bellwether stocks for morning news scan (top 2 per sector)
MORNING_FOCUS = ["NVDA", "AMD", "MSFT", "GOOGL", "TSM", "ASML", "AMZN", "CRM"]


def ct_now() -> str:
    return datetime.now(CT).strftime("%a %b %d, %I:%M %p CT")


def ct_date() -> str:
    return datetime.now(CT).strftime("%A, %B %d")


def _rsi_badge(rsi) -> str:
    if rsi is None:   return ""
    if rsi < 30:      return f"RSI {rsi} 🟢"
    if rsi > 70:      return f"RSI {rsi} 🔴"
    return f"RSI {rsi} 🟡"


def _get_reddit_buzz(ticker: str) -> str:
    """Return a short Yahoo trending buzz string, or empty if not trending."""
    try:
        from reddit import get_reddit_sentiment
        r = get_reddit_sentiment(ticker, limit=10)
        if r.get("available") and r.get("in_trending"):
            rank = r.get("trend_rank")
            rank_str = f" #{rank}" if rank else ""
            return f"🔥 Yahoo Trending{rank_str} — {r['hype_label']}"
    except Exception:
        pass
    return ""


async def send_morning_brief(bot: Bot):
    """
    Full morning market brief — the most important message of the day.
    Structured like a professional pre-market report.
    """
    logger.info("Building morning brief...")

    # ── MESSAGE 0: Market Context (SPY/QQQ + Fear & Greed + Sector ETFs) ─
    try:
        benchmarks  = get_market_benchmarks()
        fear_greed  = get_fear_greed()
        sector_etfs = get_sector_etf_performance()
        ctx_msg     = format_market_context(benchmarks, fear_greed, sector_etfs)

        # Append Yahoo trending tickers to market context
        try:
            from reddit import get_market_trending_summary
            trending = get_yahoo_trending()
            if trending:
                ctx_msg += f"\n🔥 *Trending on Yahoo Finance:*\n   {', '.join(trending[:10])}\n   _Most-searched stocks right now_"
        except Exception:
            pass

        await bot.send_message(chat_id=CHAT_ID, text=ctx_msg, parse_mode=ParseMode.MARKDOWN)
        logger.info("Morning brief msg 0 sent (market context)")
        await asyncio.sleep(1)
    except Exception as e:
        logger.warning(f"Market context failed: {e}")

    all_tickers = [t for tickers in SECTORS.values() for t in tickers]
    movers = get_top_movers(all_tickers)

    if not movers:
        await bot.send_message(
            chat_id=CHAT_ID,
            text="⚠️ Morning brief: Could not fetch market data. Yahoo Finance may be rate-limiting.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # ── MESSAGE 1: Overview + Top Movers ─────────────────────────────────
    msg1_lines = [
        f"🌅 *MORNING MARKET BRIEF*",
        f"📅 {ct_date()}  |  {ct_now()}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "🔥 *TOP PRE-MARKET MOVERS*",
        "_Stocks moving the most before market opens_",
        "",
    ]

    # Top 5 movers with RSI signal
    for m in movers[:5]:
        emoji    = "📈" if m["change_pct"] >= 0 else "📉"
        vol_flag = "  ⚡" if m["volume_ratio"] > 2 else ""
        tech     = get_technical_signals(m["history"])
        rsi_str  = f"  |  {_rsi_badge(tech['rsi'])}" if tech["rsi"] else ""
        msg1_lines.append(f"  {emoji} *{m['ticker']}*  {m['change_pct']:+.2f}%{vol_flag}{rsi_str}")

    # 52W high breakouts
    highs, lows = [], []
    for m in movers:
        tech = get_technical_signals(m["history"])
        try:
            pct = float(tech["high_label"].split("%")[0])
            if -3 <= pct <= 0:
                highs.append(m["ticker"])
        except Exception:
            pass
        if tech["rsi"] and tech["rsi"] < 32:
            lows.append(f"{m['ticker']} (RSI {tech['rsi']})")

    if highs:
        msg1_lines += [
            "",
            f"🚀 *Near 52-Week High Breakouts:*",
            f"   {', '.join(highs[:4])}",
            "   _Stocks near their strongest point in a year_",
        ]
    if lows:
        msg1_lines += [
            "",
            f"🟢 *Oversold Opportunities (RSI < 32):*",
            f"   {', '.join(lows[:4])}",
            "   _Heavy selling may have overextended — bounce candidates_",
        ]

    # Earnings warnings
    earnings_soon = []
    for m in movers:
        ed = m.get("earnings_date")
        if ed:
            try:
                from datetime import timezone
                now = datetime.now(timezone.utc)
                ed_aware = ed.replace(tzinfo=timezone.utc) if ed.tzinfo is None else ed
                days = (ed_aware - now).days
                if 0 <= days <= 14:
                    earnings_soon.append(f"{m['ticker']} ({days}d)")
            except Exception:
                pass
    if earnings_soon:
        msg1_lines += [
            "",
            "⚠️ *Earnings Within 2 Weeks:*",
            f"   {', '.join(earnings_soon[:5])}",
            "   _Price can swing ±15%+ on earnings day — manage risk!_",
        ]

    msg1_lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💡 /analyze TICKER — full deep-dive report",
    ]

    await bot.send_message(
        chat_id=CHAT_ID, text="\n".join(msg1_lines), parse_mode=ParseMode.MARKDOWN
    )
    logger.info("Morning brief msg 1 sent (movers)")

    # ── MESSAGE 2: News + Reddit per sector ──────────────────────────────
    await asyncio.sleep(1)
    msg2_lines = [
        "📰 *TODAY'S KEY NEWS + REDDIT BUZZ*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "_What people are talking about this morning_",
        "",
    ]

    # Scan top 2 focus tickers per sector
    for sector, tickers in SECTORS.items():
        focus = [t for t in MORNING_FOCUS if t in tickers][:2] or tickers[:2]
        sector_lines = [f"*{sector}*"]
        has_content = False

        for ticker in focus:
            articles  = get_news(ticker, limit=5)
            sentiment = score_news(articles)
            reddit    = _get_reddit_buzz(ticker)

            top_headline = ""
            if articles:
                top_headline = articles[0]["title"][:75]

            if top_headline or reddit:
                has_content = True
                sector_lines.append(f"  *{ticker}* — {sentiment['label']}")
                if top_headline:
                    sector_lines.append(f"    📰 {top_headline}…")
                if reddit:
                    sector_lines.append(f"    {reddit}")

        if has_content:
            msg2_lines += sector_lines
            msg2_lines.append("")

    msg2_lines += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💡 /political NVDA — check political signals for any stock",
    ]

    await bot.send_message(
        chat_id=CHAT_ID, text="\n".join(msg2_lines), parse_mode=ParseMode.MARKDOWN
    )
    logger.info("Morning brief msg 2 sent (news + reddit)")

    # ── MESSAGE 3: What to watch + sector overview ────────────────────────
    await asyncio.sleep(1)
    msg3_lines = [
        "🧠 *WHAT TO WATCH TODAY*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    watchlist = []
    for m in movers:
        tech   = get_technical_signals(m["history"])
        alerts = tech["signals"]
        rsi    = tech["rsi"]
        reasons = []

        if rsi and rsi < 30:
            reasons.append(f"oversold (RSI {rsi})")
        if rsi and rsi > 72:
            reasons.append(f"overbought (RSI {rsi})")
        if any("52-Week High" in s for s in alerts):
            reasons.append("near 52W high breakout")
        if any("volume" in s.lower() for s in alerts):
            reasons.append("extreme volume spike")
        if m["volume_ratio"] > 3:
            reasons.append(f"volume {m['volume_ratio']:.1f}x normal")

        if reasons:
            emoji = "📈" if m["change_pct"] >= 0 else "📉"
            watchlist.append(f"  {emoji} *{m['ticker']}* — {', '.join(reasons[:2])}")

    if watchlist:
        for w in watchlist[:6]:
            msg3_lines.append(w)
    else:
        msg3_lines.append("  No extreme signals today — normal trading conditions")

    msg3_lines += [
        "",
        "📊 *SECTOR SNAPSHOT*",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for sector, tickers in SECTORS.items():
        sector_data = [m for m in movers if m["ticker"] in tickers]
        if not sector_data:
            continue
        avg_chg = sum(m["change_pct"] for m in sector_data) / len(sector_data)
        trend   = "📈" if avg_chg >= 0 else "📉"
        best    = max(sector_data, key=lambda x: x["change_pct"])
        worst   = min(sector_data, key=lambda x: x["change_pct"])
        msg3_lines.append(
            f"  {trend} *{sector}* avg {avg_chg:+.1f}% — "
            f"Best: {best['ticker']} {best['change_pct']:+.1f}%  |  "
            f"Worst: {worst['ticker']} {worst['change_pct']:+.1f}%"
        )

    msg3_lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "📅 *MACRO CALENDAR — TODAY'S EVENTS:*",
        "",
    ]
    macro_events = get_macro_calendar()
    for ev in macro_events:
        msg3_lines.append(f"   • {ev}")

    msg3_lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "⚠️ _Not financial advice — educational only_",
        "💡 /analyze TICKER — full analyst report on any stock",
        "💡 /trending — real-time momentum ranking",
        "💡 /morning — trigger this brief any time | /evening — closing report",
    ]

    await bot.send_message(
        chat_id=CHAT_ID, text="\n".join(msg3_lines), parse_mode=ParseMode.MARKDOWN
    )
    logger.info("Morning brief complete ✅")


async def send_closing_report(bot: Bot):
    """End-of-day report: gainers, losers, sentiment summary, what moved markets."""
    logger.info("Building closing report...")

    all_tickers = [t for tickers in SECTORS.values() for t in tickers]
    movers  = get_top_movers(all_tickers)
    gainers = [m for m in movers if m["change_pct"] > 0][:4]
    losers  = sorted(movers, key=lambda x: x["change_pct"])[:3]

    lines = [
        f"📊 *MARKET CLOSE REPORT*",
        f"📅 {ct_date()}  |  {ct_now()}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "🏆 *Top Gainers Today:*",
        "_Stocks that moved up most — look for volume confirmation_",
        "",
    ]
    for m in gainers:
        tech     = get_technical_signals(m["history"])
        vol_note = "  ⚡ Vol spike!" if m["volume_ratio"] > 2 else ""
        rsi_note = f"  RSI {tech['rsi']}" if tech["rsi"] else ""
        lines.append(f"  📈 *{m['ticker']}*  +{m['change_pct']:.2f}%{vol_note}{rsi_note}")

    lines += [
        "",
        "📉 *Notable Losers:*",
        "_Check news to understand why — opportunity or warning?_",
        "",
    ]
    for m in losers:
        if m["change_pct"] < 0:
            articles  = get_news(m["ticker"], limit=3)
            top_news  = articles[0]["title"][:60] if articles else "No major news found"
            lines.append(f"  📉 *{m['ticker']}*  {m['change_pct']:.2f}%")
            lines.append(f"     📰 {top_news}…")

    # Sector performance
    lines += ["", "📊 *Sector Performance:*", ""]
    for sector, tickers in SECTORS.items():
        sector_data = [m for m in movers if m["ticker"] in tickers]
        if not sector_data:
            continue
        avg = sum(m["change_pct"] for m in sector_data) / len(sector_data)
        trend = "📈" if avg >= 0 else "📉"
        lines.append(f"  {trend} *{sector}:* avg {avg:+.1f}%")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💡 /analyze TICKER — tomorrow's opportunity analysis",
        "💡 /trending — see full momentum table",
        "⚠️ _Not financial advice — educational only_",
    ]
    await bot.send_message(
        chat_id=CHAT_ID, text="\n".join(lines), parse_mode=ParseMode.MARKDOWN
    )
    logger.info("Closing report sent ✅")


async def send_weekly_deepdive(bot: Bot):
    all_tickers = [t for tickers in SECTORS.values() for t in tickers]
    movers = get_top_movers(all_tickers)

    lines = [
        f"📅 *WEEKLY DEEP-DIVE*",
        f"Week ending {ct_date()}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "📊 *Weekly Performance by Sector:*",
        "",
    ]
    for sector, tickers in SECTORS.items():
        lines.append(f"*{sector}*")
        sector_movers = [m for m in movers if m["ticker"] in tickers]
        for m in sorted(sector_movers, key=lambda x: x["change_pct"], reverse=True):
            emoji = "📈" if m["change_pct"] >= 0 else "📉"
            tech  = get_technical_signals(m["history"])
            rsi   = f"  RSI {tech['rsi']}" if tech["rsi"] else ""
            lines.append(f"  {emoji} *{m['ticker']}*  {m['change_pct']:+.2f}%{rsi}")
        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💡 /analyze TICKER — full report on any stock above",
        "⚠️ _Not financial advice — educational only_",
    ]
    await bot.send_message(
        chat_id=CHAT_ID, text="\n".join(lines), parse_mode=ParseMode.MARKDOWN
    )


async def main():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("❌ Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID env vars.")
        return

    bot     = Bot(token=TELEGRAM_TOKEN)
    hour_ct = datetime.now(CT).hour
    weekday = datetime.now(CT).weekday()

    print(f"[scheduler] Running at {ct_now()} — CT hour: {hour_ct}, weekday: {weekday}")

    if hour_ct == 8:
        print("[scheduler] Sending morning brief (3 messages)...")
        await send_morning_brief(bot)
    elif hour_ct == 16:
        print("[scheduler] Sending closing report...")
        await send_closing_report(bot)
    elif hour_ct == 9 and weekday == 6:
        print("[scheduler] Sending weekly deep-dive...")
        await send_weekly_deepdive(bot)
    else:
        print("[scheduler] Off-schedule — sending morning brief as default")
        await send_morning_brief(bot)

    print("[scheduler] Done ✅")


if __name__ == "__main__":
    asyncio.run(main())

