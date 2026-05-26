"""
Scheduled alert sender — called by GitHub Actions cron (alerts.yml).
Sends pre-market brief, closing report, and weekly deep-dive.
All times displayed in Central Time (Chicago).
"""
import asyncio
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Bot
from telegram.constants import ParseMode

from config import TELEGRAM_TOKEN, SECTORS
from fetcher import get_top_movers
from technical import get_technical_signals

CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CT = ZoneInfo("America/Chicago")


def ct_now() -> str:
    return datetime.now(CT).strftime("%a %b %d, %I:%M %p CT")


def ct_date() -> str:
    return datetime.now(CT).strftime("%A %b %d")


async def send_premarket_brief(bot: Bot):
    all_tickers = [t for tickers in SECTORS.values() for t in tickers]
    movers = get_top_movers(all_tickers)

    lines = [
        f"🌅 *PRE-MARKET BRIEF*",
        f"📅 {ct_date()}  |  {ct_now()}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "🔥 *Top 5 Movers (Pre-market):*",
        "_How much each stock moved overnight_",
        "",
    ]
    for m in movers[:5]:
        emoji    = "📈" if m["change_pct"] >= 0 else "📉"
        vol_flag = "  ⚡ High volume!" if m["volume_ratio"] > 2 else ""
        lines.append(f"  {emoji} *{m['ticker']}*  {m['change_pct']:+.2f}%{vol_flag}")

    # 52W high alerts
    highs = []
    for m in movers:
        hist = m.get("history")
        if hist is not None and len(hist) > 0:
            tech = get_technical_signals(hist)
            try:
                pct_from_high = float(tech["high_label"].replace("%", "").replace(" from 52W High", "").strip())
                if -3 <= pct_from_high <= 3:
                    highs.append(m["ticker"])
            except Exception:
                pass
    if highs:
        lines += [
            "",
            f"🚀 *Near 52-Week Highs:* {', '.join(highs[:5])}",
            "_These stocks are near their strongest price in a year_",
        ]

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💡 /analyze NVDA — full report on any stock",
        "💡 /sector AI — top AI/Semi/Cloud movers",
        "⚠️ _Not financial advice — educational only_",
    ]
    await bot.send_message(chat_id=CHAT_ID, text="\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def send_closing_report(bot: Bot):
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
        "_Stocks that moved up the most_",
        "",
    ]
    for m in gainers:
        vol_note = "  ⚡" if m["volume_ratio"] > 2 else ""
        lines.append(f"  📈 *{m['ticker']}*  +{m['change_pct']:.2f}%{vol_note}")

    lines += [
        "",
        "📉 *Notable Losers:*",
        "_Stocks that dropped — worth understanding why_",
        "",
    ]
    for m in losers:
        if m["change_pct"] < 0:
            lines.append(f"  📉 *{m['ticker']}*  {m['change_pct']:.2f}%")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💡 /trending — see the full momentum ranking",
        "💡 /analyze TICKER — deep-dive any of these",
        "⚠️ _Not financial advice — educational only_",
    ]
    await bot.send_message(chat_id=CHAT_ID, text="\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def send_weekly_deepdive(bot: Bot):
    all_tickers = [t for tickers in SECTORS.values() for t in tickers]
    movers = get_top_movers(all_tickers)

    lines = [
        f"📅 *WEEKLY DEEP-DIVE*",
        f"Week of {ct_date()}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "📊 *All Tracked Stocks — Weekly Snapshot:*",
        "",
    ]
    for sector, tickers in SECTORS.items():
        lines.append(f"*{sector}*")
        sector_movers = [m for m in movers if m["ticker"] in tickers]
        for m in sorted(sector_movers, key=lambda x: x["change_pct"], reverse=True):
            emoji = "📈" if m["change_pct"] >= 0 else "📉"
            lines.append(f"  {emoji} *{m['ticker']}*  {m['change_pct']:+.2f}%")
        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💡 Use /analyze TICKER for a full investment report on any stock above",
        "⚠️ _Not financial advice — educational only_",
    ]
    await bot.send_message(chat_id=CHAT_ID, text="\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def main():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("❌ Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID env vars.")
        return

    bot  = Bot(token=TELEGRAM_TOKEN)
    hour_ct = datetime.now(CT).hour

    print(f"[scheduler] Running at {ct_now()} — CT hour: {hour_ct}")

    if hour_ct == 8:
        print("[scheduler] Sending pre-market brief...")
        await send_premarket_brief(bot)
    elif hour_ct == 16:
        print("[scheduler] Sending closing report...")
        await send_closing_report(bot)
    elif hour_ct == 9 and datetime.now(CT).weekday() == 6:
        print("[scheduler] Sending weekly deep-dive...")
        await send_weekly_deepdive(bot)
    else:
        print("[scheduler] Off-schedule run — sending pre-market brief as default")
        await send_premarket_brief(bot)

    print("[scheduler] Done ✅")


if __name__ == "__main__":
    asyncio.run(main())

