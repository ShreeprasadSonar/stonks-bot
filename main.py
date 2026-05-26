"""Main entry point for StockBot."""
import logging
from telegram.ext import ApplicationBuilder, CommandHandler

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


def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set. Copy .env.example to .env and fill it in.")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

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
