"""Telegram bot command handlers."""
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from fetcher    import get_stock_info, get_top_movers
from news       import get_news, check_political_mentions
from technical  import get_technical_signals
from fundamental import score_fundamentals
from sentiment  import score_news
from formatter  import format_analyze_report, EXPLAIN_DICT
from reddit     import get_reddit_sentiment, format_reddit_report
from config     import SECTORS
import watchlist as wl_db


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 *Welcome to StockBot!*\n\n"
        "I'm your personal stock analyst — I give you plain-English signals so you can make better investment decisions.\n\n"
        "📌 *Commands:*\n"
        "  /analyze NVDA — Full analyst report\n"
        "  /sector AI — Top movers in a sector\n"
        "  /trending — Today's top momentum stocks\n"
        "  /political NVDA — Political & news signals\n"
        "  /watchlist — Your saved stocks\n"
        "  /explain rsi — Learn what RSI means\n"
        "  /help — Show all commands\n\n"
        "💡 _Start with_ /analyze NVDA _to see a full report._"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📖 *StockBot Commands*\n\n"
        "/analyze <TICKER>   — Full report: price, technicals, fundamentals, sentiment, Reddit buzz\n"
        "/sector <NAME>      — Top movers in AI / Semiconductors / Cloud / Software\n"
        "/trending           — Top 5 stocks by momentum today\n"
        "/political <TICKER> — Congressional trades & political news\n"
        "/reddit <TICKER>    — StockTwits social sentiment & trader mood\n"
        "/watchlist          — View your watchlist\n"
        "/watch <TICKER>     — Add to watchlist\n"
        "/unwatch <TICKER>   — Remove from watchlist\n"
        "/explain <TERM>     — Plain-English explanation (rsi, macd, pe, 52w, golden, volume, sentiment, reddit)\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /analyze NVDA")
        return

    ticker = context.args[0].upper()
    await update.message.reply_text(f"🔍 Analyzing {ticker}… please wait.")

    try:
        stock = get_stock_info(ticker)
        if "error" in stock:
            await update.message.reply_text(f"❌ {stock['error']}")
            return

        tech      = get_technical_signals(stock["history"])
        fund      = score_fundamentals(stock)
        articles  = get_news(ticker, stock["name"])
        sentiment = score_news(articles)
        reddit    = get_reddit_sentiment(ticker)

        report = format_analyze_report(stock, tech, fund, sentiment, reddit)
        await update.message.reply_text(report, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        await update.message.reply_text(f"❌ Error analyzing {ticker}: {str(e)}")


async def cmd_sector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sector_name = " ".join(context.args).title() if context.args else ""

    matched = None
    for key in SECTORS:
        if key.lower() in sector_name.lower() or sector_name.lower() in key.lower():
            matched = key
            break

    if not matched:
        sectors_list = ", ".join(SECTORS.keys())
        await update.message.reply_text(f"Usage: /sector AI\nAvailable: {sectors_list}")
        return

    tickers = SECTORS[matched]
    await update.message.reply_text(f"🔍 Fetching {matched} sector movers…")

    movers = get_top_movers(tickers)
    lines  = [f"📊 *{matched} Sector — Top Movers*\n"]
    for m in movers:
        emoji    = "📈" if m["change_pct"] >= 0 else "📉"
        vol_flag = " ⚡ Vol spike!" if m["volume_ratio"] > 2 else ""
        lines.append(f"{emoji} *{m['ticker']}* ${m['price']} ({m['change_pct']:+.2f}%){vol_flag}")
    lines.append("\n💡 Use /analyze NVDA for a deep dive on any stock.")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_trending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_tickers = [t for tickers in SECTORS.values() for t in tickers]
    await update.message.reply_text("🔍 Finding today's top movers…")
    movers = get_top_movers(all_tickers)[:5]
    lines  = ["🔥 *Today's Top 5 Momentum Stocks*\n"]
    for i, m in enumerate(movers, 1):
        emoji = "📈" if m["change_pct"] >= 0 else "📉"
        lines.append(f"{i}. {emoji} *{m['ticker']}* — ${m['price']} ({m['change_pct']:+.2f}%)")
    lines.append("\n💡 Use /analyze <TICKER> for a full report.")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_political(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /political NVDA")
        return

    ticker = context.args[0].upper()
    await update.message.reply_text(f"🏛️ Checking political signals for {ticker}…")

    stock = get_stock_info(ticker)
    hits  = check_political_mentions(ticker, stock.get("name", ticker))

    if not hits:
        await update.message.reply_text(f"No recent political news found for {ticker}.")
        return

    lines = [f"🏛️ *Political Signals for {ticker}*\n"]
    for h in hits[:5]:
        keywords = ", ".join(h["political_keywords"])
        lines.append(f"• {h['title'][:90]}…\n  _Keywords: {keywords}_\n")
    lines.append("💡 Congressional buy/sell alerts coming in Phase 4!")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_explain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        terms = ", ".join(EXPLAIN_DICT.keys())
        await update.message.reply_text(f"Usage: /explain rsi\nAvailable terms: {terms}")
        return
    term = context.args[0].lower()
    msg  = EXPLAIN_DICT.get(term)
    if not msg:
        terms = ", ".join(EXPLAIN_DICT.keys())
        await update.message.reply_text(f"Unknown term. Try: {terms}")
        return
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# Persistent watchlist via SQLite (watchlist.py)

async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /watch NVDA")
        return
    ticker = context.args[0].upper()
    wl_db.add_ticker(uid, ticker)
    await update.message.reply_text(f"✅ Added *{ticker}* to your watchlist.\nYour watchlist: " +
                                    ", ".join(wl_db.get_watchlist(uid)),
                                    parse_mode=ParseMode.MARKDOWN)

async def cmd_unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /unwatch NVDA")
        return
    ticker = context.args[0].upper()
    wl_db.remove_ticker(uid, ticker)
    remaining = wl_db.get_watchlist(uid)
    msg = f"✅ Removed *{ticker}* from your watchlist."
    if remaining:
        msg += f"\nRemaining: {', '.join(remaining)}"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    wl  = wl_db.get_watchlist(uid)
    if not wl:
        await update.message.reply_text("Your watchlist is empty.\nUse /watch NVDA to add stocks.")
        return
    lines = ["📋 *Your Watchlist:*\n"] + [f"• {t}" for t in wl]
    lines.append("\n💡 Use /analyze NVDA for a full report on any stock.")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_reddit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /reddit NVDA")
        return

    ticker = context.args[0].upper()
    await update.message.reply_text(f"📱 Checking StockTwits sentiment for {ticker}… (no login needed)")


    try:
        data   = get_reddit_sentiment(ticker)
        report = format_reddit_report(ticker, data)
        report += (
            f"\n\n💡 /analyze {ticker} — full technical + fundamental report\n"
            f"⚠️ _High social hype ≠ good investment. Always check technicals._"
        )
        await update.message.reply_text(report, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ StockTwits fetch failed for {ticker}: {str(e)}")


async def cmd_morning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually trigger the morning brief on demand."""
    import os
    from telegram import Bot
    from scheduler import send_morning_brief
    await update.message.reply_text("🌅 Generating your morning brief… (3 messages, takes ~30s)")
    try:
        bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN", ""))
        chat_id = str(update.effective_chat.id)
        os.environ["TELEGRAM_CHAT_ID"] = chat_id
        await send_morning_brief(bot)
    except Exception as e:
        await update.message.reply_text(f"❌ Morning brief failed: {e}")


async def cmd_evening(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually trigger the closing report on demand."""
    import os
    from telegram import Bot
    from scheduler import send_closing_report
    await update.message.reply_text("📊 Generating closing report… (takes ~20s)")
    try:
        bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN", ""))
        chat_id = str(update.effective_chat.id)
        os.environ["TELEGRAM_CHAT_ID"] = chat_id
        await send_closing_report(bot)
    except Exception as e:
        await update.message.reply_text(f"❌ Closing report failed: {e}")

