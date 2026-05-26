"""
Scheduled alert sender — called by GitHub Actions cron.
Phase 6 will expand this significantly.
"""
import asyncio
import os
from datetime import datetime
from telegram import Bot
from telegram.constants import ParseMode

from config import TELEGRAM_TOKEN, SECTORS
from fetcher import get_top_movers
from technical import get_technical_signals

CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


async def send_premarket_brief(bot: Bot):
    all_tickers = [t for tickers in SECTORS.values() for t in tickers]
    movers = get_top_movers(all_tickers)

    lines = [
        f"🌅 *PRE-MARKET BRIEF — {datetime.now().strftime('%a %b %d')}*",
        "",
        "🔥 *Top Movers (Tracked Stocks):*",
    ]
    for m in movers[:5]:
        emoji = "📈" if m["change_pct"] >= 0 else "📉"
        vol   = " ⚡" if m["volume_ratio"] > 2 else ""
        lines.append(f"  {emoji} *{m['ticker']}* {m['change_pct']:+.2f}%{vol}")

    highs = []
    for m in movers:
        hist = m.get("history")
        if hist is not None:
            tech = get_technical_signals(hist)
            if tech["high_label"].startswith("-0") or tech["high_label"].startswith("-1"):
                highs.append(m["ticker"])
    if highs:
        lines += ["", f"🚀 *Near 52W Highs:* {', '.join(highs[:5])}"]

    lines += [
        "",
        "💡 Use /analyze <TICKER> for a full report.",
        "⚠️ _Not financial advice — educational only._",
    ]
    await bot.send_message(chat_id=CHAT_ID, text="\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def send_closing_report(bot: Bot):
    all_tickers = [t for tickers in SECTORS.values() for t in tickers]
    movers  = get_top_movers(all_tickers)
    gainers = [m for m in movers if m["change_pct"] > 0][:3]
    losers  = sorted(movers, key=lambda x: x["change_pct"])[:3]

    lines = [
        f"📊 *CLOSING REPORT — {datetime.now().strftime('%a %b %d')}*",
        "",
        "🏆 *Top Gainers (Tracked):*",
    ]
    for m in gainers:
        lines.append(f"  📈 *{m['ticker']}* +{m['change_pct']:.2f}%")

    lines += ["", "📉 *Top Losers (Tracked):*"]
    for m in losers:
        if m["change_pct"] < 0:
            lines.append(f"  📉 *{m['ticker']}* {m['change_pct']:.2f}%")

    lines += [
        "",
        "💡 Use /sector AI or /analyze NVDA for details.",
        "⚠️ _Not financial advice — educational only._",
    ]
    await bot.send_message(chat_id=CHAT_ID, text="\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def main():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID env vars.")
        return

    bot  = Bot(token=TELEGRAM_TOKEN)
    hour = datetime.utcnow().hour

    if hour == 13:
        await send_premarket_brief(bot)
    elif hour == 21:
        await send_closing_report(bot)
    else:
        await send_premarket_brief(bot)  # default for manual runs


if __name__ == "__main__":
    asyncio.run(main())
