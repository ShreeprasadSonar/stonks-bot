"""Main entry point for StockBot — with smart political news monitor."""
import logging
import os
import json
import time as _time
import asyncio
import html as _html
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, Application
from telegram.constants import ParseMode
from telegram.error import NetworkError, TimedOut


from config import TELEGRAM_TOKEN, SECTORS
from commands import (
    cmd_start, cmd_help, cmd_analyze, cmd_market,
    cmd_social, cmd_political, cmd_watchlist,
    cmd_brief, cmd_explain, cmd_button_callback,
    cmd_alert, cmd_edgar,
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

# ── Persistent state ─────────────────────────────────────────────────────────
STATE_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
SEEN_FILE  = os.path.join(STATE_DIR, "seen_articles.json")
START_FILE = os.path.join(STATE_DIR, "last_startup.txt")


def _load_seen() -> set:
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_seen(seen: set):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(SEEN_FILE, "w") as f:
            json.dump(list(seen)[-500:], f)   # cap to avoid unbounded growth
    except Exception as e:
        logger.warning(f"Could not save seen articles: {e}")


def _should_send_startup() -> bool:
    """Return True only if the last startup message was sent > 6 hours ago."""
    try:
        with open(START_FILE) as f:
            return (_time.time() - float(f.read().strip())) > 6 * 3600
    except Exception:
        return True  # first run


def _mark_startup():
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(START_FILE, "w") as f:
            f.write(str(_time.time()))
    except Exception:
        pass


_seen_political: set = set()
_alert_cooldowns: dict = {}   # ticker → datetime of last alert

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


def _build_digest(items: list) -> str:
    """Build a single HTML digest message from multiple political alert items."""
    items_sorted = sorted(items, key=lambda x: x["impact"], reverse=True)[:8]
    lines = [
        "<b>🏛️ POLITICAL MARKET DIGEST</b>",
        f"<i>{ct_now()}</i>",
        "─────────────────────",
        "",
    ]
    tickers_seen: list = []
    for item in items_sorted:
        badge  = impact_badge(item["impact"])
        ticker = item["ticker"]
        if ticker not in tickers_seen:
            tickers_seen.append(ticker)

        summary = item.get("summary", "")
        summary_line = (
            f"\n   <i>{_html.escape(summary[:300])}</i>" if summary else ""
        )

        link     = item.get("link", "")
        news_src = _html.escape(item.get("news_source", ""))
        ref_str  = ""
        if link and news_src:
            ref_str = f'\n   📰 <a href="{_html.escape(link)}">{news_src}</a>'
        elif link:
            ref_str = f'\n   📰 <a href="{_html.escape(link)}">Read more</a>'

        why = (
            f"{item['source']} statements move markets immediately."
            if item["impact"] >= 9
            else f"{item['source']} has authority to affect {ticker} through regulation or legislation."
        )
        lines += [
            f"<b>{badge} — {ticker}</b>",
            f"   {_html.escape(item['title'])}{summary_line}",
            f"   {_html.escape(item['sentiment'])}{ref_str}",
            f"   <i>Impact {item['impact']}/10 · {_html.escape(why)}</i>",
            "",
        ]

    if tickers_seen:
        lines.append("  ".join(f"/analyze {t}" for t in tickers_seen[:5]))
    return "\n".join(lines)


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


async def price_alert_monitor(app: Application):
    """Check price alerts every 5 minutes and fire notifications."""
    import alerts as alert_db
    from fetcher import get_stock_info
    logger.info("💰 Price alert monitor started")
    while True:
        try:
            pending = alert_db.get_all_pending()
            by_ticker: dict = {}
            for a in pending:
                by_ticker.setdefault(a["ticker"], []).append(a)

            for ticker, ticker_alerts in by_ticker.items():
                try:
                    data = get_stock_info(ticker)
                    if "error" in data:
                        continue
                    price = data["price"]
                    for a in ticker_alerts:
                        triggered = (
                            (a["direction"] == "above" and price >= a["target"]) or
                            (a["direction"] == "below" and price <= a["target"])
                        )
                        if triggered:
                            arrow  = "▲" if a["direction"] == "above" else "▼"
                            change = data["change_pct"]
                            chg_emoji = "📈" if change >= 0 else "📉"
                            msg = (
                                f"🔔 <b>PRICE ALERT TRIGGERED</b>\n"
                                f"─────────────────────\n\n"
                                f"  {arrow} <b>{ticker}</b>  is now <b>${price}</b>\n"
                                f"  Your alert: {a['direction']} <b>${a['target']}</b>  ✅\n\n"
                                f"  {chg_emoji} Today: {change:+.2f}%\n\n"
                                f"/analyze {ticker}"
                            )
                            if CHAT_ID:
                                await app.bot.send_message(
                                    chat_id=a["chat_id"], text=msg,
                                    parse_mode="HTML", disable_web_page_preview=True
                                )
                            alert_db.mark_triggered(a["id"])
                            logger.info(f"🔔 Alert fired: {ticker} {a['direction']} {a['target']} (current: {price})")
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"Alert check error for {ticker}: {e}")
        except Exception as e:
            logger.error(f"Alert monitor error: {e}")
        await asyncio.sleep(300)  # 5 minutes


async def political_news_monitor(app: Application):
    """Background task — checks every 20 min, sends one digest per cycle (not per article)."""
    global _seen_political
    _seen_political = _load_seen()   # restore across restarts
    logger.info("🏛️ Political monitor started — threshold: impact >= 7 only")
    while True:
        try:
            # Refresh dynamic tickers each cycle (Yahoo trending + themes + base)
            try:
                from reddit import get_dynamic_tickers
                monitor_tickers = [(t, "dynamic") for t in get_dynamic_tickers()]
            except Exception:
                monitor_tickers = ALL_TICKERS

            from datetime import timedelta, timezone
            now_utc      = datetime.now(timezone.utc)
            digest_items = []

            for ticker, _ in monitor_tickers:
                articles = get_news(ticker, limit=15)
                for a in articles:
                    title_lower = a["title"].lower()
                    impact, source, sentiment = score_political_impact(title_lower)

                    if impact < ALERT_THRESHOLD:
                        continue

                    key = a["title"][:80]
                    if key in _seen_political:
                        continue
                    _seen_political.add(key)

                    last_alert = _alert_cooldowns.get(ticker)
                    if last_alert and (now_utc - last_alert) < timedelta(hours=4):
                        logger.info(f"[{ticker}] Cooldown active — skipping")
                        continue
                    _alert_cooldowns[ticker] = now_utc

                    digest_items.append({
                        "ticker":      ticker,
                        "impact":      impact,
                        "source":      source,
                        "sentiment":   sentiment,
                        "title":       a["title"],
                        "summary":     a.get("summary", ""),
                        "link":        a.get("link", ""),
                        "news_source": a.get("source", ""),
                    })

                await asyncio.sleep(0.5)

            _save_seen(_seen_political)

            if digest_items and CHAT_ID:
                msg = _build_digest(digest_items)
                await app.bot.send_message(
                    chat_id=CHAT_ID, text=msg,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False,
                )
                logger.info(f"🏛️ Political digest sent — {len(digest_items)} alert(s)")

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
        "<b>Live Snapshot</b>",
        f"<i>{ct_now()}</i>",
        "─────────────────────",
        "",
    ]

    any_success = False
    for ticker in SNAPSHOT_TICKERS:
        try:
            stock = get_stock_info(ticker)
            if "error" in stock:
                lines.append(f"  <i>{ticker}: data unavailable</i>")
                continue

            chg      = stock["change_pct"]
            arrow    = "▲" if chg >= 0 else "▼"
            vol_flag = "  ⚡" if stock["volume_ratio"] > 3 else ""

            tech = get_technical_signals(stock["history"])

            rsi_note = ""
            if tech["rsi"]:
                if tech["rsi"] < 30:
                    rsi_note = f"  🟢 RSI {tech['rsi']} — oversold"
                elif tech["rsi"] > 70:
                    rsi_note = f"  🔴 RSI {tech['rsi']} — overbought"

            articles = fetch_news(ticker, limit=5)
            sent     = score_news(articles)

            lines.append(
                f"<b>{ticker}</b>  ${stock['price']}  {arrow} {chg:+.2f}%{vol_flag}\n"
                f"  52W  ${stock['week52_low']} – ${stock['week52_high']}{rsi_note}\n"
                f"  News  {sent['label']}"
            )
            any_success = True

        except Exception as e:
            logger.error(f"Snapshot failed for {ticker}: {e}")

    lines += [
        "",
        "─────────────────────",
        "/analyze NVDA  ·  /market",
    ]

    if any_success:
        await app.bot.send_message(chat_id=CHAT_ID, text="\n".join(lines), parse_mode=ParseMode.HTML)
        logger.info("✅ Live startup snapshot sent")
    else:
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text="Data unavailable at startup — Yahoo Finance may be rate-limiting.\nTry /analyze NVDA in 60 seconds.",
            parse_mode=ParseMode.HTML,
        )


async def send_startup_message(app: Application):
    """Send startup report + live snapshot + launch background tasks."""
    logger.info("🟢 StockBot startup sequence initiated")

    # Register commands so Telegram shows the autocomplete menu when user types /
    from telegram import BotCommand
    try:
        await app.bot.set_my_commands([
            BotCommand("analyze",   "Full analyst report — /analyze NVDA"),
            BotCommand("market",    "Top movers + sector view"),
            BotCommand("social",    "Reddit · Trends · Congress · Analysts — /social NVDA"),
            BotCommand("political", "Political signals + congress trades — /political NVDA"),
            BotCommand("watchlist", "Manage your watchlist"),
            BotCommand("brief",     "Morning or evening market brief"),
            BotCommand("explain",   "Learn a metric — /explain rsi"),
            BotCommand("alert",     "Price alert — /alert NVDA above 150"),
            BotCommand("edgar",     "SEC filings + insider trades — /edgar NVDA"),
            BotCommand("help",      "Show all commands"),
        ])
        logger.info("✅ Bot commands registered (autocomplete menu active)")
    except Exception as e:
        logger.warning(f"Could not set bot commands: {e}")

    if not CHAT_ID:
        logger.warning("⚠️ TELEGRAM_CHAT_ID not set — add it as a GitHub Secret")
        asyncio.create_task(political_news_monitor(app))
        asyncio.create_task(price_alert_monitor(app))
        return

    # Suppress startup noise on frequent restarts (e.g. GitHub Actions redeploys)
    if not _should_send_startup():
        logger.info("⏭️ Startup message suppressed — restarted recently (< 6 h)")
        asyncio.create_task(political_news_monitor(app))
        asyncio.create_task(price_alert_monitor(app))
        return

    _mark_startup()

    msg = (
        "<b>StockBot</b> is live\n"
        f"<i>{ct_now()}</i>\n"
        "─────────────────────\n\n"
        "<b>Commands</b>\n"
        "  /analyze NVDA — full analyst report\n"
        "  /market — top movers + sector view\n"
        "  /social NVDA — Reddit · Trends · Congress\n"
        "  /political NVDA — political signals\n"
        "  /watchlist — manage saved stocks\n"
        "  /brief — morning or evening brief\n"
        "  /explain rsi — metric guide\n\n"
        "<b>Political Monitor</b>  active\n"
        "  Alerts only for: President, Fed Chair, SEC, Congress\n\n"
        "<b>Scheduled Briefs</b>  (GitHub Actions)\n"
        "  🌅 8:00 AM CT Mon–Fri — pre-market\n"
        "  📊 4:30 PM CT Mon–Fri — closing\n"
        "  📅 Sunday 9:00 AM CT — weekly\n\n"
        "<i>Fetching live snapshot…</i>"
    )
    await app.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode=ParseMode.HTML)
    logger.info(f"✅ Startup message sent to chat {CHAT_ID}")

    asyncio.create_task(political_news_monitor(app))
    asyncio.create_task(price_alert_monitor(app))
    asyncio.create_task(send_live_snapshot(app))
    logger.info("✅ Background tasks launched")


def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("❌ TELEGRAM_BOT_TOKEN not set. Add it as a GitHub Secret.")

    logger.info("Initializing StockBot...")
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .post_init(send_startup_message)
        .build()
    )

    # ── Error handler: silently retry transient network drops ────────────
    async def error_handler(update, context):
        err = context.error
        if isinstance(err, (NetworkError, TimedOut)):
            # GitHub Actions network blips — normal, bot auto-retries
            logger.warning(f"⚠️ Network blip (auto-retrying): {err.__class__.__name__}")
        else:
            logger.error(f"❌ Unhandled error: {err}", exc_info=context.error)

    app.add_error_handler(error_handler)
    # ─────────────────────────────────────────────────────────────────────

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("analyze",   cmd_analyze))
    app.add_handler(CommandHandler("market",    cmd_market))
    app.add_handler(CommandHandler("social",    cmd_social))
    app.add_handler(CommandHandler("political", cmd_political))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))
    app.add_handler(CommandHandler("brief",     cmd_brief))
    app.add_handler(CommandHandler("explain",   cmd_explain))
    app.add_handler(CommandHandler("alert",     cmd_alert))
    app.add_handler(CommandHandler("edgar",     cmd_edgar))
    app.add_handler(CallbackQueryHandler(cmd_button_callback))

    logger.info("✅ StockBot running — listening for commands")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
