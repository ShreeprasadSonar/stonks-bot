"""Main entry point for StockBot — with smart political news monitor."""
import logging
import os
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram.ext import ApplicationBuilder, CommandHandler, Application
from telegram.constants import ParseMode

from config import TELEGRAM_TOKEN, SECTORS
from commands import (
    cmd_start, cmd_help, cmd_analyze, cmd_sector,
    cmd_trending, cmd_political, cmd_explain,
    cmd_watch, cmd_unwatch, cmd_watchlist,
)
from news import get_news

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("yfinance").setLevel(logging.WARNING)

logger = logging.getLogger("StockBot")

CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CT = ZoneInfo("America/Chicago")

_seen_political: set = set()

# ── Impact scoring: higher = more important, only alert if score >= ALERT_THRESHOLD
ALERT_THRESHOLD = 7

IMPACT_SOURCES = {
    # CRITICAL (9-10) — market-moving tier
    "president":        10,
    "white house":      10,
    "trump":            10,
    "biden":            10,
    "harris":           9,
    "federal reserve":  9,
    "powell":           9,   # Fed Chair — interest rates move entire market
    # HIGH (7-8) — significant regulatory/legal
    "sec ":             8,   # space to avoid "sector"
    "doj":              8,
    "antitrust":        8,
    "executive order":  8,
    "congress":         7,
    "senate":           7,
    "senator":          7,
    "treasury":         7,
    "tariff":           7,
    # MEDIUM (5-6) — notable but less urgent
    "musk":             6,
    "pentagon":         6,
    "regulation":       5,
    "subsidy":          5,
    "contract":         5,
    # LOW (1-4) — skip these
    "government":       3,
    "federal":          3,
    "official":         2,
}

# Positive/negative impact words
POSITIVE_WORDS = ["support", "invest", "approve", "buy", "boost", "win",
                  "deal", "partnership", "subsidy", "contract", "award", "fund"]
NEGATIVE_WORDS = ["ban", "sanction", "fine", "sue", "block", "tariff",
                  "tax", "investigate", "probe", "restrict", "halt", "warn"]

ALL_TICKERS = [(t, sector) for sector, tickers in SECTORS.items() for t in tickers]


def score_political_impact(title: str) -> tuple[int, str, str]:
    """
    Returns (impact_score, source_label, sentiment_label).
    Only alert if impact_score >= ALERT_THRESHOLD.
    """
    title_lower = title.lower()
    max_score   = 0
    source      = ""

    for keyword, score in IMPACT_SOURCES.items():
        if keyword in title_lower and score > max_score:
            max_score = score
            source    = keyword.strip().title()

    # Sentiment
    positive = sum(1 for w in POSITIVE_WORDS if w in title_lower)
    negative = sum(1 for w in NEGATIVE_WORDS if w in title_lower)
    if positive > negative:
        sentiment = "🟢 Likely Positive for stock"
    elif negative > positive:
        sentiment = "🔴 Likely Negative for stock"
    else:
        sentiment = "🟡 Impact unclear — monitor closely"

    return max_score, source, sentiment


def impact_badge(score: int) -> str:
    if score >= 9:  return "🚨 CRITICAL"
    if score >= 7:  return "⚠️ HIGH IMPACT"
    if score >= 5:  return "📌 NOTABLE"
    return "ℹ️ LOW"


def ct_now() -> str:
    return datetime.now(CT).strftime("%a %b %d, %I:%M %p CT")


async def political_news_monitor(app: Application):
    """Background task — checks every 20 min, only alerts on high-impact news."""
    logger.info("🏛️ Political monitor started — threshold: impact >= 7 only")
    while True:
        try:
            for ticker, sector in ALL_TICKERS:
                articles = get_news(ticker, limit=15)
                for a in articles:
                    title_lower = a["title"].lower()
                    impact, source, sentiment = score_political_impact(title_lower)

                    if impact < ALERT_THRESHOLD:
                        continue  # Skip low-level mentions silently

                    key = a["title"][:80]
                    if key in _seen_political:
                        continue
                    _seen_political.add(key)

                    badge = impact_badge(impact)

                    # Plain-English explanation of why this matters
                    if impact >= 9:
                        why = f"🧠 *Why this matters:* {source} statements directly move markets. Traders react within minutes."
                    elif impact >= 7:
                        why = f"🧠 *Why this matters:* {source} has real authority to affect this company through regulation or legislation."
                    else:
                        why = f"🧠 *Why this matters:* Notable mention — worth monitoring but may not move price immediately."

                    msg = (
                        f"{badge} *POLITICAL ALERT — {ticker}*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"📰 {a['title']}\n\n"
                        f"👤 *Source level:* {source} (Impact: {impact}/10)\n"
                        f"📊 *Market signal:* {sentiment}\n"
                        f"🕐 {ct_now()}\n\n"
                        f"{why}\n\n"
                        f"💡 Run /analyze {ticker} for full investment report\n"
                        f"⚠️ _Educational only — not financial advice_"
                    )
                    if CHAT_ID:
                        await app.bot.send_message(
                            chat_id=CHAT_ID, text=msg,
                            parse_mode=ParseMode.MARKDOWN,
                            disable_web_page_preview=True
                        )
                        logger.info(f"🏛️ [{badge}] Political alert sent — {ticker}: {a['title'][:60]}")

                await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Political monitor error: {e}")

        logger.info("🏛️ Political check done — next in 20 min")
        await asyncio.sleep(1200)  # 20 minutes


async def send_live_snapshot(app: Application):
    """Fetch and send a live market snapshot ~30s after startup."""
    await asyncio.sleep(5)
    logger.info("📊 Fetching live startup snapshot...")

    from fetcher import get_stock_info
    from technical import get_technical_signals
    from sentiment import score_news
    from news import get_news as fetch_news

    SNAPSHOT_TICKERS = ["NVDA", "MSFT", "AMD"]

    lines = [
        f"📊 *LIVE MARKET SNAPSHOT*",
        f"🕐 {ct_now()}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    any_success = False
    for ticker in SNAPSHOT_TICKERS:
        try:
            stock = get_stock_info(ticker)
            if "error" in stock:
                lines.append(f"⚠️ *{ticker}:* Data unavailable right now")
                continue

            chg      = stock["change_pct"]
            emoji    = "📈" if chg >= 0 else "📉"
            vol_flag = " ⚡ *Volume spike!*" if stock["volume_ratio"] > 3 else ""

            tech = get_technical_signals(stock["history"])

            rsi_note = ""
            if tech["rsi"]:
                if tech["rsi"] < 30:
                    rsi_note = f"\n   🟢 RSI {tech['rsi']} — Oversold (potential buy zone)"
                elif tech["rsi"] > 70:
                    rsi_note = f"\n   🔴 RSI {tech['rsi']} — Overbought (be cautious)"
                else:
                    rsi_note = f"\n   🟡 RSI {tech['rsi']} — Normal range"

            articles = fetch_news(ticker, limit=5)
            sent     = score_news(articles)

            lines.append(
                f"{emoji} *{ticker}* — ${stock['price']} ({chg:+.2f}%){vol_flag}\n"
                f"   📅 52W Low: ${stock['week52_low']}  |  High: ${stock['week52_high']}{rsi_note}\n"
                f"   📰 News today: {sent['label']}"
            )
            any_success = True

        except Exception as e:
            logger.error(f"Snapshot failed for {ticker}: {e}")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💡 /analyze NVDA — full deep-dive on any stock",
        "💡 /trending — all top movers right now",
        "⚠️ _Not financial advice_",
    ]

    if any_success:
        await app.bot.send_message(chat_id=CHAT_ID, text="\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        logger.info("✅ Live startup snapshot sent")
    else:
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text=(
                "⚠️ *Live data unavailable right now*\n\n"
                "Yahoo Finance may be rate-limiting. This is normal at startup.\n"
                "Try /analyze NVDA in 60 seconds — it should work fine."
            ),
            parse_mode=ParseMode.MARKDOWN
        )


async def send_startup_message(app: Application):
    """Send startup report + live snapshot + launch background tasks."""
    logger.info("🟢 StockBot startup sequence initiated")

    if not CHAT_ID:
        logger.warning("⚠️ TELEGRAM_CHAT_ID not set — add it as a GitHub Secret")
        asyncio.create_task(political_news_monitor(app))
        return

    msg = (
        "🟢 *StockBot is LIVE!*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 *Started:* {ct_now()}\n\n"
        "📌 *Commands:*\n"
        "  /analyze NVDA — Full analyst report with score\n"
        "  /sector AI — Top movers in AI/Semi/Cloud/Software\n"
        "  /trending — Today's top 5 momentum stocks\n"
        "  /political NVDA — Political & government signals\n"
        "  /watch NVDA — Add to your watchlist\n"
        "  /explain rsi — Plain-English metric guide\n\n"
        "🏛️ *Smart Political Monitor:* ON\n"
        "   Only fires for President, Fed Chair, SEC, Congress\n"
        "   Low-level mentions are silently ignored\n\n"
        "⏰ *Auto Reports (alerts.yml):*\n"
        "   🌅 8:00 AM CT Mon–Fri — Pre-market brief\n"
        "   📊 4:30 PM CT Mon–Fri — Closing report\n"
        "   📅 Sunday 9:00 AM CT — Weekly deep-dive\n\n"
        "📊 _Fetching live snapshot in a moment…_\n"
        "⚠️ _Educational use only. Not financial advice._"
    )
    await app.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode=ParseMode.MARKDOWN)
    logger.info(f"✅ Startup message sent to chat {CHAT_ID}")

    asyncio.create_task(political_news_monitor(app))
    asyncio.create_task(send_live_snapshot(app))
    logger.info("✅ Background tasks launched")


def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("❌ TELEGRAM_BOT_TOKEN not set. Add it as a GitHub Secret.")

    logger.info("Initializing StockBot...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(send_startup_message).build()

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("analyze",   cmd_analyze))
    app.add_handler(CommandHandler("sector",    cmd_sector))
    app.add_handler(CommandHandler("trending",  cmd_trending))
    app.add_handler(CommandHandler("political", cmd_political))
    app.add_handler(CommandHandler("explain",   cmd_explain))
    app.add_handler(CommandHandler("watch",     cmd_watch))
    app.add_handler(CommandHandler("unwatch",   cmd_unwatch))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))

    logger.info("✅ StockBot running — listening for commands")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
