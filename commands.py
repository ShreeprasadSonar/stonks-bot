"""Telegram bot command handlers."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
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

# Popular tickers shown as quick-pick buttons when user taps a command with no ticker
POPULAR_TICKERS = ["NVDA", "MSFT", "AMD", "TSLA", "AAPL", "META", "GOOGL", "AMZN"]


def _ticker_buttons(cmd: str) -> InlineKeyboardMarkup:
    """Return an inline keyboard with popular tickers for the given command."""
    rows = []
    row  = []
    for i, t in enumerate(POPULAR_TICKERS):
        row.append(InlineKeyboardButton(t, callback_data=f"{cmd}:{t}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


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
        "/reddit <TICKER>    — Yahoo trending & social interest for a stock\n"
        "/watchlist          — View your watchlist\n"
        "/watch <TICKER>     — Add to watchlist\n"
        "/unwatch <TICKER>   — Remove from watchlist\n"
        "/explain <TERM>     — Plain-English explanation (rsi, macd, pe, 52w, golden, volume, sentiment, reddit)\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "📊 Which stock do you want to analyze?\nTap one below or type: /analyze NVDA",
            reply_markup=_ticker_buttons("analyze"),
        )
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
        await update.message.reply_text(report, parse_mode=ParseMode.HTML)

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
        await update.message.reply_text(
            "🏛️ Which stock do you want political signals for?\nTap one below or type: /political NVDA",
            reply_markup=_ticker_buttons("political"),
        )
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
        terms = list(EXPLAIN_DICT.keys())
        rows  = []
        row   = []
        for i, t in enumerate(terms):
            row.append(InlineKeyboardButton(t, callback_data=f"explain:{t}"))
            if len(row) == 3:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        await update.message.reply_text(
            "📚 Which term do you want explained?\nTap one below or type: /explain rsi",
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return
    term = context.args[0].lower()
    msg  = EXPLAIN_DICT.get(term)
    if not msg:
        terms = ", ".join(EXPLAIN_DICT.keys())
        await update.message.reply_text(f"Unknown term. Try: {terms}")
        return
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


# Persistent watchlist via SQLite (watchlist.py)

async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text(
            "📋 Which stock do you want to add to your watchlist?\nTap one below or type: /watch NVDA",
            reply_markup=_ticker_buttons("watch"),
        )
        return
    ticker = context.args[0].upper()
    wl_db.add_ticker(uid, ticker)
    await update.message.reply_text(f"✅ Added *{ticker}* to your watchlist.\nYour watchlist: " +
                                    ", ".join(wl_db.get_watchlist(uid)),
                                    parse_mode=ParseMode.MARKDOWN)

async def cmd_unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        wl = wl_db.get_watchlist(uid)
        if wl:
            rows = [[InlineKeyboardButton(t, callback_data=f"unwatch:{t}") for t in wl[i:i+4]]
                    for i in range(0, len(wl), 4)]
            await update.message.reply_text(
                "📋 Which stock do you want to remove from your watchlist?",
                reply_markup=InlineKeyboardMarkup(rows),
            )
        else:
            await update.message.reply_text("Your watchlist is empty. Use /watch NVDA to add stocks.")
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
        await update.message.reply_text(
            "📊 Which stock do you want Yahoo trending data for?\nTap one below or type: /reddit NVDA",
            reply_markup=_ticker_buttons("reddit"),
        )
        return

    ticker = context.args[0].upper()
    await update.message.reply_text(f"📊 Checking Yahoo Finance trending & sentiment for {ticker}…")


    try:
        data   = get_reddit_sentiment(ticker)
        report = format_reddit_report(ticker, data)
        report += (
            f"\n\n💡 /analyze {ticker} — full technical + fundamental report\n"
            f"<i>⚠️ High social hype ≠ good investment. Always check technicals.</i>"
        )
        await update.message.reply_text(report, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Yahoo trending fetch failed for {ticker}: {str(e)}")


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


async def cmd_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle inline keyboard button taps.
    Callback data format: "command:TICKER" or "explain:term"
    """
    query = update.callback_query
    await query.answer()  # dismiss the loading spinner

    data = query.data or ""
    if ":" not in data:
        return

    cmd, value = data.split(":", 1)
    chat_id    = query.message.chat_id
    uid        = query.from_user.id

    # Edit the original message so it shows what was selected
    await query.edit_message_text(f"✅ Selected: <b>{value}</b>", parse_mode=ParseMode.HTML)

    # Re-use the existing command logic by routing through a fake context
    # Instead, call the underlying logic directly
    if cmd == "analyze":
        ticker = value.upper()
        await context.bot.send_message(chat_id=chat_id, text=f"🔍 Analyzing {ticker}… please wait.")
        try:
            stock = get_stock_info(ticker)
            if "error" in stock:
                await context.bot.send_message(chat_id=chat_id, text=f"❌ {stock['error']}")
                return
            tech      = get_technical_signals(stock["history"])
            fund      = score_fundamentals(stock)
            articles  = get_news(ticker, stock["name"])
            sentiment = score_news(articles)
            reddit    = get_reddit_sentiment(ticker)
            report    = format_analyze_report(stock, tech, fund, sentiment, reddit)
            await context.bot.send_message(chat_id=chat_id, text=report, parse_mode=ParseMode.HTML)
        except Exception as e:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Error analyzing {ticker}: {e}")

    elif cmd == "political":
        ticker = value.upper()
        await context.bot.send_message(chat_id=chat_id, text=f"🏛️ Checking political signals for {ticker}…")
        stock = get_stock_info(ticker)
        hits  = check_political_mentions(ticker, stock.get("name", ticker))
        if not hits:
            await context.bot.send_message(chat_id=chat_id, text=f"No recent political news found for {ticker}.")
            return
        lines = [f"🏛️ *Political Signals for {ticker}*\n"]
        for h in hits[:5]:
            keywords = ", ".join(h["political_keywords"])
            lines.append(f"• {h['title'][:90]}…\n  _Keywords: {keywords}_\n")
        await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    elif cmd == "reddit":
        ticker = value.upper()
        await context.bot.send_message(chat_id=chat_id, text=f"📊 Checking Yahoo Finance trending for {ticker}…")
        try:
            data   = get_reddit_sentiment(ticker)
            report = format_reddit_report(ticker, data)
            report += (
                f"\n\n💡 /analyze {ticker} — full technical + fundamental report\n"
                f"<i>⚠️ Trending ≠ good investment. Always check technicals.</i>"
            )
            await context.bot.send_message(chat_id=chat_id, text=report, parse_mode=ParseMode.HTML)
        except Exception as e:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Failed: {e}")

    elif cmd == "explain":
        term = value.lower()
        msg  = EXPLAIN_DICT.get(term, f"Unknown term: {term}")
        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML)

    elif cmd == "watch":
        ticker = value.upper()
        wl_db.add_ticker(uid, ticker)
        wl = wl_db.get_watchlist(uid)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Added *{ticker}* to your watchlist.\nYour watchlist: {', '.join(wl)}",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif cmd == "unwatch":
        ticker = value.upper()
        wl_db.remove_ticker(uid, ticker)
        remaining = wl_db.get_watchlist(uid)
        msg = f"✅ Removed *{ticker}* from your watchlist."
        if remaining:
            msg += f"\nRemaining: {', '.join(remaining)}"
        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN)


