"""Main entry point for StockBot — with background political news monitor."""
import logging
import os
import asyncio
from datetime import datetime, timezone
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
# Silence noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger("StockBot")

CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Track already-sent political alerts so we don't spam duplicates
_seen_political: set = set()

POLITICAL_FIGURES = [
    "trump", "biden", "harris", "musk", "powell",  # fed chair
    "president", "senator", "congress", "white house",
    "government", "federal reserve", "sec", "regulation",
    "tariff", "subsidy", "executive order", "pentagon",
    "treasury", "antitrust", "doj",
]

ALL_TICKERS = [(t, sector) for sector, tickers in SECTORS.items() for t in tickers]


async def political_news_monitor(app: Application):
    """Background task — checks every 15 min for political mentions of tracked stocks."""
    logger.info("🏛️ Political news monitor started — checking every 15 minutes")
    while True:
        try:
            for ticker, sector in ALL_TICKERS:
                articles = get_news(ticker, limit=15)
                for a in articles:
                    title_lower = a["title"].lower()
                    matched_kw  = [kw for kw in POLITICAL_FIGURES if kw in title_lower]
                    if not matched_kw:
                        continue

                    # Deduplicate by title
                    key = a["title"][:80]
                    if key in _seen_political:
                        continue
                    _seen_political.add(key)

                    # Build sentiment hint
                    positive = any(w in title_lower for w in ["good", "great", "support", "buy", "invest", "boost", "approve", "win"])
                    negative = any(w in title_lower for w in ["ban", "sanction", "fine", "sue", "block", "tariff", "tax", "investigate"])
                    sentiment = "🟢 Positive signal" if positive else ("🔴 Negative signal" if negative else "🟡 Neutral mention")

                    msg = (
                        f"🏛️ *POLITICAL ALERT — {ticker}* ({sector})\n\n"
                        f"📰 {a['title']}\n\n"
                        f"🔍 *Keywords detected:* {', '.join(matched_kw[:3])}\n"
                        f"📊 *Sentiment:* {sentiment}\n"
                        f"🕐 {a.get('published', 'Just now')}\n\n"
                        f"💡 Use /analyze {ticker} for full investment report\n"
                        f"⚠️ _Educational only — not financial advice_"
                    )
                    if CHAT_ID:
                        await app.bot.send_message(
                            chat_id=CHAT_ID, text=msg, parse_mode=ParseMode.MARKDOWN,
                            disable_web_page_preview=True
                        )
                        logger.info(f"🏛️ Political alert sent for {ticker}: {a['title'][:60]}")

                await asyncio.sleep(0.5)  # Small delay between tickers

        except Exception as e:
            logger.error(f"Political monitor error: {e}")

        logger.info("🏛️ Political news check complete — next check in 15 minutes")
        await asyncio.sleep(900)  # 15 minutes


async def send_startup_message(app: Application):
    """Send startup report + live snapshot + launch background political monitor."""
    logger.info("🟢 StockBot startup sequence initiated")

    if not CHAT_ID:
        logger.warning("⚠️ TELEGRAM_CHAT_ID not set — startup message skipped. Add it as a GitHub Secret.")
        asyncio.create_task(political_news_monitor(app))
        return

    # 1️⃣ Send the "bot is live" message immediately
    msg = (
        "🟢 *StockBot is LIVE!*\n\n"
        f"🕐 Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        "📌 *Commands:*\n"
        "  /analyze NVDA — Full analyst report\n"
        "  /sector AI — Top AI movers\n"
        "  /trending — Top 5 momentum stocks today\n"
        "  /political NVDA — Political signals\n"
        "  /watch NVDA — Add to watchlist\n"
        "  /explain rsi — Learn any metric\n\n"
        "🏛️ *Political Monitor:* ACTIVE\n"
        "⏰ *Scheduled alerts active via alerts.yml*\n\n"
        "📊 _Fetching live market snapshot… please wait 30 seconds_"
    )
    await app.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode=ParseMode.MARKDOWN)
    logger.info(f"✅ Startup message sent to chat {CHAT_ID}")

    # 2️⃣ Launch background tasks
    asyncio.create_task(political_news_monitor(app))
    asyncio.create_task(send_live_snapshot(app))
    logger.info("✅ All background tasks launched")


async def send_live_snapshot(app: Application):
    """Fetch and send a live market snapshot ~30s after startup."""
    await asyncio.sleep(5)  # Let bot fully initialize first
    logger.info("📊 Fetching live startup snapshot...")

    from fetcher import get_stock_info
    from technical import get_technical_signals
    from sentiment import score_news
    from news import get_news as fetch_news

    # Pick 3 key bellwether stocks for the snapshot
    SNAPSHOT_TICKERS = ["NVDA", "MSFT", "AMD"]

    lines = [
        f"📊 *LIVE MARKET SNAPSHOT*",
        f"🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    any_success = False
    for ticker in SNAPSHOT_TICKERS:
        try:
            stock = get_stock_info(ticker)
            if "error" in stock:
                lines.append(f"⚠️ *{ticker}:* {stock['error']}")
                continue

            chg     = stock["change_pct"]
            emoji   = "📈" if chg >= 0 else "📉"
            vol_flag = " ⚡ Vol spike!" if stock["volume_ratio"] > 2 else ""

            tech = get_technical_signals(stock["history"])
            rsi_short = ""
            if tech["rsi"]:
                if tech["rsi"] < 30:   rsi_short = " | RSI 🟢 Oversold"
                elif tech["rsi"] > 70: rsi_short = " | RSI 🔴 Overbought"

            # Quick news sentiment (3 headlines)
            articles  = fetch_news(ticker, limit=5)
            from sentiment import score_news
            sent      = score_news(articles)

            lines.append(
                f"{emoji} *{ticker}* — ${stock['price']} ({chg:+.2f}%){vol_flag}\n"
                f"   52W: ${stock['week52_low']} — ${stock['week52_high']}{rsi_short}\n"
                f"   News: {sent['label']}"
            )
            any_success = True

        except Exception as e:
            logger.error(f"Snapshot failed for {ticker}: {e}")
            lines.append(f"⚠️ *{ticker}:* Could not fetch data")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💡 Use /analyze NVDA for a full deep-dive report",
        "💡 Use /trending for all top movers",
        "⚠️ _Not financial advice_",
    ]

    if any_success:
        await app.bot.send_message(
            chat_id=CHAT_ID, text="\n".join(lines), parse_mode=ParseMode.MARKDOWN
        )
        logger.info("✅ Live startup snapshot sent")
    else:
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text="⚠️ Could not fetch live data right now — Yahoo Finance may be rate-limiting. Try /analyze NVDA in a moment.",
            parse_mode=ParseMode.MARKDOWN
        )
        logger.warning("⚠️ Startup snapshot failed for all tickers")


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

    logger.info("✅ StockBot is running and listening for commands")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()


from config import TELEGRAM_TOKEN
from commands import (
    cmd_start, cmd_help, cmd_analyze, cmd_sector,
    cmd_trending, cmd_political, cmd_explain,
    cmd_watch, cmd_unwatch, cmd_watchlist,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


async def send_startup_message(app):
    """Send a startup report when the bot goes live."""
    if not CHAT_ID:
        return
    msg = (
        "🟢 *StockBot is LIVE!*\n\n"
        f"🕐 Started at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        "📌 *Ready to use:*\n"
        "  /analyze NVDA — Full analyst report\n"
        "  /sector AI — Top AI sector movers\n"
        "  /trending — Today's top 5 momentum stocks\n"
        "  /political NVDA — Political signals\n"
        "  /explain rsi — Learn any metric\n\n"
        "⏰ *Scheduled alerts:*\n"
        "  🌅 Pre-market brief: 8:00 AM EST (Mon–Fri)\n"
        "  📊 Closing report: 4:30 PM EST (Mon–Fri)\n"
        "  📅 Weekly deep-dive: Sunday 9:00 AM EST\n\n"
        "⚠️ _Educational use only. Not financial advice._"
    )
    await app.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode=ParseMode.MARKDOWN)


def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set. Copy .env.example to .env and fill it in.")

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

    logger.info("StockBot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
