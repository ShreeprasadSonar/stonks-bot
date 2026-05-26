"""Main entry point for StockBot."""
import logging
import os
from datetime import datetime
from telegram import Bot
from telegram.ext import ApplicationBuilder, CommandHandler
from telegram.constants import ParseMode

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
