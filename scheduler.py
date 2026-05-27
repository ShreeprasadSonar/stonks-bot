"""
Scheduled alert sender — called by GitHub Actions cron (alerts.yml).
Morning brief: full market overview with news + Reddit + political signals.
Closing report: day summary with gainers/losers + sentiment.
All times in Central Time (Chicago).
"""
import asyncio
import html as _html
import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Bot
from telegram.constants import ParseMode

_e = _html.escape   # HTML-escape helper for dynamic strings

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
            from reddit import get_yahoo_trending
            trending = get_yahoo_trending()
            if trending:
                ctx_msg += f"\n🔥 <b>Trending on Yahoo Finance:</b>\n   {', '.join(trending[:10])}\n   <i>Most-searched stocks right now</i>"
        except Exception:
            pass

        await bot.send_message(chat_id=CHAT_ID, text=ctx_msg, parse_mode=ParseMode.HTML)
        logger.info("Morning brief msg 0 sent (market context)")
        await asyncio.sleep(1)
    except Exception as e:
        logger.warning(f"Market context failed: {e}")

    try:
        from reddit import get_dynamic_tickers
        all_tickers = get_dynamic_tickers()
    except Exception:
        all_tickers = [t for tickers in SECTORS.values() for t in tickers]
    movers = get_top_movers(all_tickers)

    if not movers:
        await bot.send_message(
            chat_id=CHAT_ID,
            text="⚠️ Morning brief: Could not fetch market data. Yahoo Finance may be rate-limiting.",
            parse_mode=ParseMode.HTML
        )
        return

    # ── MESSAGE 1: Overview + Top Movers ─────────────────────────────────
    msg1_lines = [
        "🌅 <b>MORNING MARKET BRIEF</b>",
        f"📅 {ct_date()}  |  {ct_now()}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "🔥 <b>TOP PRE-MARKET MOVERS</b>",
        "<i>Stocks moving the most before market opens</i>",
        "",
    ]

    # Top 5 movers with RSI signal
    for m in movers[:5]:
        emoji    = "📈" if m["change_pct"] >= 0 else "📉"
        vol_flag = "  ⚡" if m["volume_ratio"] > 2 else ""
        tech     = get_technical_signals(m["history"])
        rsi_str  = f"  |  {_rsi_badge(tech['rsi'])}" if tech["rsi"] else ""
        msg1_lines.append(f"  {emoji} <b>{m['ticker']}</b>  {m['change_pct']:+.2f}%{vol_flag}{rsi_str}")

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
            "🚀 <b>Near 52-Week High Breakouts:</b>",
            f"   {', '.join(highs[:4])}",
            "   <i>Stocks near their strongest point in a year</i>",
        ]
    if lows:
        msg1_lines += [
            "",
            "🟢 <b>Oversold Opportunities (RSI &lt; 32):</b>",
            f"   {', '.join(lows[:4])}",
            "   <i>Heavy selling may have overextended — bounce candidates</i>",
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
            "⚠️ <b>Earnings Within 2 Weeks:</b>",
            f"   {', '.join(earnings_soon[:5])}",
            "   <i>Price can swing ±15%+ on earnings day — manage risk!</i>",
        ]

    msg1_lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💡 /analyze TICKER — full deep-dive report",
    ]

    await bot.send_message(
        chat_id=CHAT_ID, text="\n".join(msg1_lines), parse_mode=ParseMode.HTML
    )
    logger.info("Morning brief msg 1 sent (movers)")

    # ── MESSAGE 2: News + Reddit per sector ──────────────────────────────
    await asyncio.sleep(1)
    msg2_lines = [
        "📰 <b>TODAY'S KEY NEWS + REDDIT BUZZ</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "<i>What people are talking about this morning</i>",
        "",
    ]

    # Scan top 2 focus tickers per sector
    for sector, tickers in SECTORS.items():
        focus = [t for t in MORNING_FOCUS if t in tickers][:2] or tickers[:2]
        sector_lines = [f"<b>{sector}</b>"]
        has_content = False

        for ticker in focus:
            articles  = get_news(ticker, limit=5)
            sentiment = score_news(articles)
            reddit    = _get_reddit_buzz(ticker)

            top_headline = ""
            if articles:
                top_headline = _e(articles[0]["title"][:75])

            if top_headline or reddit:
                has_content = True
                sector_lines.append(f"  <b>{ticker}</b> — {sentiment['label']}")
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
        chat_id=CHAT_ID, text="\n".join(msg2_lines), parse_mode=ParseMode.HTML
    )
    logger.info("Morning brief msg 2 sent (news + reddit)")

    # ── MESSAGE 2b: Social Signals Block (Reddit hot + Congress trades) ───
    await asyncio.sleep(1)
    social_lines = [
        "📡 <b>SOCIAL &amp; POLITICAL PULSE</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    # Reddit hot tickers
    try:
        from social import get_reddit_hot_tickers
        hot = get_reddit_hot_tickers(limit=8)
        if hot:
            social_lines.append("💬 <b>Reddit Buzz — most-mentioned right now:</b>")
            for h in hot[:5]:
                social_lines.append(f"  • <b>{h['ticker']}</b> — {h['mentions']} mentions")
            social_lines.append("  <i>High Reddit activity = retail sentiment moving</i>")
            social_lines.append("")
    except Exception as e:
        logger.warning(f"Reddit hot tickers failed: {e}")

    # Congress trades in last 7 days across all tracked tickers
    try:
        from social import get_congress_trades
        congress_hits = []
        for ticker in MORNING_FOCUS:
            trades = get_congress_trades(ticker, recent_days=7)
            for tr in trades:
                congress_hits.append((ticker, tr))
        if congress_hits:
            social_lines.append("🏛️ <b>Congressional Trades — last 7 days:</b>")
            for ticker, tr in congress_hits[:6]:
                emoji = "🟢" if "purch" in tr["type"].lower() or "buy" in tr["type"].lower() else "🔴"
                social_lines.append(f"  {emoji} <b>{ticker}</b> — {_e(tr['name'])} ({tr['chamber']}) {_e(tr['type'])} · {tr['date']}")
            social_lines.append("  <i>Congress trades are public record — net buying is bullish signal</i>")
            social_lines.append("")
    except Exception as e:
        logger.warning(f"Congress trades failed: {e}")

    if len(social_lines) > 4:  # only send if we have actual content
        social_lines += [
            "━━━━━━━━━━━━━━━━━━━━━━",
            "💡 /social TICKER — full social intelligence report",
        ]
        await bot.send_message(
            chat_id=CHAT_ID, text="\n".join(social_lines), parse_mode=ParseMode.HTML
        )
        logger.info("Morning brief social block sent")

    # ── MESSAGE 2c: Narrative / Theme Tracker ─────────────────────────────
    await asyncio.sleep(1)
    try:
        from themes import score_themes
        theme_results = score_themes(use_trends=False)  # skip Google Trends for speed
        hot_themes    = [t for t in theme_results if t["score"] >= 15][:4]
        if hot_themes:
            th_lines = [
                "📡 <b>MARKET NARRATIVE TRACKER</b>",
                "<i>What institutional &amp; retail investors are focusing on today</i>",
                "━━━━━━━━━━━━━━━━━━━━━━",
                "",
            ]
            for th in hot_themes:
                tickers_str = "  ".join(th["tickers"][:5])
                th_lines.append(f"{th['momentum']}  <b>{_e(th['name'])}</b>")
                th_lines.append(f"   Plays: {tickers_str}")
                if th["top_headlines"]:
                    th_lines.append(f"   📰 <i>{_e(th['top_headlines'][0][:85])}</i>…")
                th_lines.append("")
            th_lines += [
                "━━━━━━━━━━━━━━━━━━━━━━",
                "💡 Tap 📡 Narrative Tracker in /market to see full theme analysis",
            ]
            await bot.send_message(
                chat_id=CHAT_ID, text="\n".join(th_lines), parse_mode=ParseMode.HTML
            )
            logger.info("Morning brief theme block sent")
    except Exception as e:
        logger.warning(f"Theme tracker failed: {e}")

    # ── MESSAGE 3: What to watch + sector overview ────────────────────────
    await asyncio.sleep(1)
    msg3_lines = [
        "🧠 <b>WHAT TO WATCH TODAY</b>",
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
            watchlist.append(f"  {emoji} <b>{m['ticker']}</b> — {', '.join(reasons[:2])}")

    if watchlist:
        for w in watchlist[:6]:
            msg3_lines.append(w)
    else:
        msg3_lines.append("  No extreme signals today — normal trading conditions")

    msg3_lines += [
        "",
        "📊 <b>SECTOR SNAPSHOT</b>",
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
            f"  {trend} <b>{sector}</b> avg {avg_chg:+.1f}% — "
            f"Best: {best['ticker']} {best['change_pct']:+.1f}%  |  "
            f"Worst: {worst['ticker']} {worst['change_pct']:+.1f}%"
        )

    msg3_lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "📅 <b>MACRO CALENDAR — TODAY'S EVENTS:</b>",
        "",
    ]
    macro_events = get_macro_calendar()
    for ev in macro_events:
        msg3_lines.append(f"   • {_e(ev)}")

    msg3_lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💡 /analyze TICKER — full analyst report on any stock",
        "💡 /market — real-time momentum + sector view",
        "💡 /brief morning — trigger this brief any time | /brief evening — closing report",
    ]

    await bot.send_message(
        chat_id=CHAT_ID, text="\n".join(msg3_lines), parse_mode=ParseMode.HTML
    )
    logger.info("Morning brief complete ✅")


async def send_closing_report(bot: Bot):
    """End-of-day report: gainers, losers, sentiment summary, what moved markets."""
    logger.info("Building closing report...")

    try:
        from reddit import get_dynamic_tickers
        all_tickers = get_dynamic_tickers()
    except Exception:
        all_tickers = [t for tickers in SECTORS.values() for t in tickers]
    movers  = get_top_movers(all_tickers)
    gainers = [m for m in movers if m["change_pct"] > 0][:4]
    losers  = sorted(movers, key=lambda x: x["change_pct"])[:3]

    lines = [
        "📊 <b>MARKET CLOSE REPORT</b>",
        f"📅 {ct_date()}  |  {ct_now()}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "🏆 <b>Top Gainers Today:</b>",
        "<i>Stocks that moved up most — look for volume confirmation</i>",
        "",
    ]
    for m in gainers:
        tech     = get_technical_signals(m["history"])
        vol_note = "  ⚡ Vol spike!" if m["volume_ratio"] > 2 else ""
        rsi_note = f"  RSI {tech['rsi']}" if tech["rsi"] else ""
        lines.append(f"  📈 <b>{m['ticker']}</b>  +{m['change_pct']:.2f}%{vol_note}{rsi_note}")

    lines += [
        "",
        "📉 <b>Notable Losers:</b>",
        "<i>Check news to understand why — opportunity or warning?</i>",
        "",
    ]
    for m in losers:
        if m["change_pct"] < 0:
            articles  = get_news(m["ticker"], limit=3)
            top_news  = _e(articles[0]["title"][:60]) if articles else "No major news found"
            lines.append(f"  📉 <b>{m['ticker']}</b>  {m['change_pct']:.2f}%")
            lines.append(f"     📰 {top_news}…")

    # Sector performance
    lines += ["", "📊 <b>Sector Performance:</b>", ""]
    for sector, tickers in SECTORS.items():
        sector_data = [m for m in movers if m["ticker"] in tickers]
        if not sector_data:
            continue
        avg = sum(m["change_pct"] for m in sector_data) / len(sector_data)
        trend = "📈" if avg >= 0 else "📉"
        lines.append(f"  {trend} <b>{sector}:</b> avg {avg:+.1f}%")

    # Social sentiment for top movers
    try:
        from social import get_finviz_signals
        top_tickers = [m["ticker"] for m in gainers[:3]]
        finviz_lines = []
        for ticker in top_tickers:
            sig = get_finviz_signals(ticker)
            if sig.get("ratings"):
                latest = sig["ratings"][0]
                finviz_lines.append(f"  <b>{ticker}</b> — {_e(latest.get('action', ''))} {_e(latest.get('rating', ''))} @ ${latest.get('price_target', '?')} ({_e(latest.get('firm', ''))})")
        if finviz_lines:
            lines += ["", "🔬 <b>Analyst Actions — Today's Movers:</b>"] + finviz_lines
    except Exception:
        pass

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💡 /analyze TICKER — tomorrow's opportunity analysis",
        "💡 /market — see full momentum + sector view",
    ]
    await bot.send_message(
        chat_id=CHAT_ID, text="\n".join(lines), parse_mode=ParseMode.HTML
    )
    logger.info("Closing report sent ✅")


async def send_weekly_deepdive(bot: Bot):
    all_tickers = [t for tickers in SECTORS.values() for t in tickers]
    movers = get_top_movers(all_tickers)

    lines = [
        "📅 <b>WEEKLY DEEP-DIVE</b>",
        f"Week ending {ct_date()}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "📊 <b>Weekly Performance by Sector:</b>",
        "",
    ]
    for sector, tickers in SECTORS.items():
        lines.append(f"<b>{sector}</b>")
        sector_movers = [m for m in movers if m["ticker"] in tickers]
        for m in sorted(sector_movers, key=lambda x: x["change_pct"], reverse=True):
            emoji = "📈" if m["change_pct"] >= 0 else "📉"
            tech  = get_technical_signals(m["history"])
            rsi   = f"  RSI {tech['rsi']}" if tech["rsi"] else ""
            lines.append(f"  {emoji} <b>{m['ticker']}</b>  {m['change_pct']:+.2f}%{rsi}")
        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💡 /analyze TICKER — full report on any stock above",
    ]
    await bot.send_message(
        chat_id=CHAT_ID, text="\n".join(lines), parse_mode=ParseMode.HTML
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

