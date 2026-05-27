"""Telegram bot command handlers — consolidated 8-command interface."""
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from fetcher     import get_stock_info, get_top_movers
from news        import get_news, check_political_mentions
from technical   import get_technical_signals
from fundamental import score_fundamentals
from sentiment   import score_news
from formatter   import format_analyze_report, EXPLAIN_DICT, _e
from reddit      import get_reddit_sentiment, format_reddit_report
from social      import get_full_social_report, get_congress_trades, get_reddit_hot_tickers
from config      import SECTORS
import watchlist as wl_db

POPULAR_TICKERS = ["NVDA", "MSFT", "AMD", "TSLA", "AAPL", "META", "GOOGL", "AMZN"]


def _ticker_kbd(cmd: str) -> InlineKeyboardMarkup:
    rows, row = [], []
    for t in POPULAR_TICKERS:
        row.append(InlineKeyboardButton(t, callback_data=f"{cmd}:{t}"))
        if len(row) == 4:
            rows.append(row); row = []
    if row: rows.append(row)
    return InlineKeyboardMarkup(rows)


# ── /start  (alias for /help)
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_help(update, context)


# ── /help
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "<b>StockBot</b>\n"
        "─────────────────────\n\n"
        "  /analyze &lt;TICKER&gt;    Full analyst report\n"
        "  /market              Top movers + sector view\n"
        "  /social &lt;TICKER&gt;    Reddit · Google Trends · Congress · Analyst ratings\n"
        "  /political &lt;TICKER&gt; Political news + congressional trades\n"
        "  /watchlist           Manage your saved stocks\n"
        "  /brief               Morning or evening market brief\n"
        "  /explain &lt;TERM&gt;     Learn any metric (rsi · macd · pe · 52w · bb · score)\n"
        "  /help                This menu"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

 
# ── /analyze
async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Which stock do you want to analyze?",
            reply_markup=_ticker_kbd("analyze"),
        )
        return
    ticker = context.args[0].upper()
    await update.message.reply_text(f"Analyzing <b>{_e(ticker)}</b>…", parse_mode=ParseMode.HTML)
    try:
        stock     = get_stock_info(ticker)
        if "error" in stock:
            await update.message.reply_text(f"❌ {stock['error']}")
            return
        tech      = get_technical_signals(stock["history"])
        fund      = score_fundamentals(stock)
        articles  = get_news(ticker, stock["name"])
        sentiment = score_news(articles)
        reddit    = get_reddit_sentiment(ticker)
        report    = format_analyze_report(stock, tech, fund, sentiment, reddit)
        await update.message.reply_text(report, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# ── /market  (replaces /trending + /sector + /buzz)
async def cmd_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Top movers overview + sector buttons + Reddit hot tickers."""
    # If a sector name is passed (/market AI), show that sector
    if context.args:
        sector_name = " ".join(context.args).title()
        matched = next(
            (k for k in SECTORS if k.lower() in sector_name.lower() or sector_name.lower() in k.lower()),
            None,
        )
        if matched:
            await update.message.reply_text(f"Fetching <b>{_e(matched)}</b> sector…", parse_mode=ParseMode.HTML)
            movers = get_top_movers(SECTORS[matched])
            lines  = [f"<b>{_e(matched)} Sector</b>", "─────────────────────", ""]
            for m in movers:
                arrow    = "▲" if m["change_pct"] >= 0 else "▼"
                vol_flag = "  ⚡" if m["volume_ratio"] > 2 else ""
                lines.append(f"<b>{m['ticker']}</b>  ${m['price']}  {arrow} {m['change_pct']:+.2f}%{vol_flag}")
            lines.append("\n/analyze &lt;TICKER&gt; for a full report")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
            return
        await update.message.reply_text(
            f"Unknown sector. Available: {', '.join(SECTORS.keys())}",
            parse_mode=ParseMode.HTML,
        )
        return

    # No args — show top movers + sector buttons
    await update.message.reply_text("Scanning market…")

    all_tickers = [t for tickers in SECTORS.values() for t in tickers]
    movers      = get_top_movers(all_tickers)[:8]

    lines = ["<b>Top Movers</b>", "─────────────────────", ""]
    for i, m in enumerate(movers, 1):
        arrow    = "▲" if m["change_pct"] >= 0 else "▼"
        vol_flag = "  ⚡" if m["volume_ratio"] > 2.5 else ""
        lines.append(f"{i}.  <b>{m['ticker']}</b>  ${m['price']}  {arrow} {m['change_pct']:+.2f}%{vol_flag}")

    # Reddit hot tickers block
    try:
        hot = get_reddit_hot_tickers(limit=6)
        if hot:
            lines += ["", "<b>Reddit Buzz</b>  <i>most-mentioned right now</i>"]
            for h in hot[:5]:
                lines.append(f"  <b>{_e(h['ticker'])}</b>  {h['mentions']} mentions")
    except Exception:
        pass

    lines.append("\n/analyze &lt;TICKER&gt;  ·  /market &lt;SECTOR&gt; for sector view")

    # Sector quick-pick buttons
    sector_rows = [[InlineKeyboardButton(s, callback_data=f"market:{s}") for s in list(SECTORS.keys())[i:i+2]]
                   for i in range(0, len(SECTORS), 2)]
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(sector_rows),
    )


# ── /social  (replaces /reddit + /buzz + old /social)
async def cmd_social(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reddit + Google Trends + Congress + Finviz for a ticker."""
    if not context.args:
        await update.message.reply_text(
            "Which stock do you want the social intelligence report for?",
            reply_markup=_ticker_kbd("social"),
        )
        return
    ticker = context.args[0].upper()
    await update.message.reply_text(
        f"Gathering social intelligence for <b>{_e(ticker)}</b>…\n"
        f"<i>Reddit · Google Trends · Congress · Analysts</i>",
        parse_mode=ParseMode.HTML,
    )
    try:
        report = get_full_social_report(ticker)
        await update.message.reply_text(report, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Social report failed: {e}")


# ── /political
async def cmd_political(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Which stock do you want political signals for?",
            reply_markup=_ticker_kbd("political"),
        )
        return
    ticker = context.args[0].upper()
    await update.message.reply_text(f"Checking political signals for <b>{_e(ticker)}</b>…", parse_mode=ParseMode.HTML)

    stock  = get_stock_info(ticker)
    hits   = check_political_mentions(ticker, stock.get("name", ticker))
    trades = get_congress_trades(ticker, recent_days=90)

    if not hits and not trades:
        await update.message.reply_text(f"No political signals or congressional trades found for {ticker}.")
        return

    lines = [f"<b>Political Signals — {_e(ticker)}</b>", "─────────────────────", ""]

    if hits:
        lines.append("<b>Political News</b>")
        for h in hits[:5]:
            keywords = ", ".join(h["political_keywords"])
            lines.append(f"• {_e(h['title'][:90])}")
            lines.append(f"  <i>{_e(keywords)}</i>")
        lines.append("")

    if trades:
        buy_cnt  = sum(1 for t in trades if "purch" in t["type"].lower() or "buy" in t["type"].lower())
        sell_cnt = len(trades) - buy_cnt
        lines.append(f"<b>Congressional Trades  (last 90 days)</b>")
        lines.append(f"  🟢 {buy_cnt} buys  ·  🔴 {sell_cnt} sells")
        for tr in trades[:5]:
            emoji = "🟢" if "purch" in tr["type"].lower() or "buy" in tr["type"].lower() else "🔴"
            lines.append(f"  {emoji} <b>{_e(tr['name'])}</b>  ({tr['chamber']})  {_e(tr['type'])}  ·  {tr['date']}")
        if buy_cnt >= sell_cnt * 2 and buy_cnt >= 2:
            lines.append("  <i>Net buying by Congress — historically bullish</i>")
        elif sell_cnt >= buy_cnt * 2 and sell_cnt >= 2:
            lines.append("  <i>Net selling by Congress — monitor carefully</i>")

    lines.append(f"\n/social {ticker}  ·  /analyze {ticker}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ── /watchlist  (replaces /watch + /unwatch + /watchlist)
async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View watchlist and manage it via inline buttons."""
    uid = update.effective_user.id
    wl  = wl_db.get_watchlist(uid)

    # If arg given, add it directly: /watchlist NVDA
    if context.args:
        ticker = context.args[0].upper()
        wl_db.add_ticker(uid, ticker)
        wl = wl_db.get_watchlist(uid)
        await update.message.reply_text(
            f"✅ Added <b>{_e(ticker)}</b>\nWatchlist: {', '.join(wl)}",
            parse_mode=ParseMode.HTML,
        )
        return

    if not wl:
        await update.message.reply_text(
            "Your watchlist is empty.\n\nTap a stock below to add it:",
            reply_markup=_ticker_kbd("watchlist_add"),
        )
        return

    items = "\n".join(f"  • <b>{_e(t)}</b>" for t in wl)
    remove_rows = [[InlineKeyboardButton(f"✖ {t}", callback_data=f"watchlist_remove:{t}") for t in wl[i:i+3]]
                   for i in range(0, len(wl), 3)]
    add_row = [InlineKeyboardButton("＋ Add stock", callback_data="watchlist_add:show")]

    await update.message.reply_text(
        f"<b>Watchlist</b>\n─────────────────────\n\n{items}\n\n"
        f"Tap ✖ to remove  ·  /analyze &lt;TICKER&gt; for report",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(remove_rows + [add_row]),
    )


# ── /brief  (replaces /morning + /evening)
async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trigger morning or evening brief on demand."""
    arg = context.args[0].lower() if context.args else ""

    if arg in ("morning", "am", "open"):
        await _run_morning(update, context)
    elif arg in ("evening", "pm", "close", "closing"):
        await _run_evening(update, context)
    else:
        await update.message.reply_text(
            "Which brief would you like?",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🌅 Morning Brief", callback_data="brief:morning"),
                InlineKeyboardButton("📊 Closing Report", callback_data="brief:evening"),
            ]]),
        )


async def _run_morning(update, context):
    await update.message.reply_text("🌅 Generating morning brief… (~30s)")
    try:
        from scheduler import send_morning_brief
        bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN", ""))
        os.environ["TELEGRAM_CHAT_ID"] = str(update.effective_chat.id)
        await send_morning_brief(bot)
    except Exception as e:
        await update.message.reply_text(f"❌ Morning brief failed: {e}")


async def _run_evening(update, context):
    await update.message.reply_text("📊 Generating closing report… (~20s)")
    try:
        from scheduler import send_closing_report
        bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN", ""))
        os.environ["TELEGRAM_CHAT_ID"] = str(update.effective_chat.id)
        await send_closing_report(bot)
    except Exception as e:
        await update.message.reply_text(f"❌ Closing report failed: {e}")


# ── /explain
async def cmd_explain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        terms = list(EXPLAIN_DICT.keys())
        rows, row = [], []
        for t in terms:
            row.append(InlineKeyboardButton(t, callback_data=f"explain:{t}"))
            if len(row) == 3:
                rows.append(row); row = []
        if row: rows.append(row)
        await update.message.reply_text(
            "Which term do you want explained?",
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return
    term = context.args[0].lower()
    msg  = EXPLAIN_DICT.get(term)
    if not msg:
        await update.message.reply_text(f"Unknown term. Available: {', '.join(EXPLAIN_DICT.keys())}")
        return
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


# ── Inline button callback handler
async def cmd_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    data   = query.data or ""
    if ":" not in data:
        return

    cmd, value = data.split(":", 1)
    chat_id    = query.message.chat_id
    uid        = query.from_user.id

    await query.edit_message_text(f"<b>{_e(value)}</b> selected", parse_mode=ParseMode.HTML)

    async def send(text, mode=ParseMode.HTML):
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=mode)

    if cmd == "analyze":
        ticker = value.upper()
        await send(f"Analyzing <b>{_e(ticker)}</b>…")
        try:
            stock     = get_stock_info(ticker)
            if "error" in stock:
                await send(f"❌ {stock['error']}"); return
            report = format_analyze_report(
                stock,
                get_technical_signals(stock["history"]),
                score_fundamentals(stock),
                score_news(get_news(ticker, stock["name"])),
                get_reddit_sentiment(ticker),
            )
            await send(report)
        except Exception as e:
            await send(f"❌ {e}")

    elif cmd == "market":
        sector_name = value.title()
        matched = next((k for k in SECTORS if k.lower() in sector_name.lower()), None)
        if matched:
            movers = get_top_movers(SECTORS[matched])
            lines  = [f"<b>{_e(matched)} Sector</b>", "─────────────────────", ""]
            for m in movers:
                arrow = "▲" if m["change_pct"] >= 0 else "▼"
                lines.append(f"<b>{m['ticker']}</b>  ${m['price']}  {arrow} {m['change_pct']:+.2f}%")
            lines.append("\n/analyze &lt;TICKER&gt; for a full report")
            await send("\n".join(lines))

    elif cmd == "social":
        ticker = value.upper()
        await send(f"Gathering social data for <b>{_e(ticker)}</b>…")
        try:
            await send(get_full_social_report(ticker))
        except Exception as e:
            await send(f"❌ {e}")

    elif cmd == "political":
        ticker = value.upper()
        await send(f"Checking political signals for <b>{_e(ticker)}</b>…")
        stock  = get_stock_info(ticker)
        hits   = check_political_mentions(ticker, stock.get("name", ticker))
        trades = get_congress_trades(ticker, recent_days=90)
        if not hits and not trades:
            await send(f"No political signals found for {ticker}."); return
        lines = [f"<b>Political Signals — {_e(ticker)}</b>", "─────────────────────", ""]
        for h in hits[:4]:
            lines.append(f"• {_e(h['title'][:90])}")
        if trades:
            buy_cnt  = sum(1 for t in trades if "purch" in t["type"].lower())
            sell_cnt = len(trades) - buy_cnt
            lines += ["", f"<b>Congress Trades:</b>  🟢 {buy_cnt} buys  ·  🔴 {sell_cnt} sells"]
        await send("\n".join(lines))

    elif cmd == "brief":
        if value == "morning":
            await send("🌅 Generating morning brief…")
            try:
                from scheduler import send_morning_brief
                bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN", ""))
                os.environ["TELEGRAM_CHAT_ID"] = str(chat_id)
                await send_morning_brief(bot)
            except Exception as e:
                await send(f"❌ {e}")
        elif value == "evening":
            await send("📊 Generating closing report…")
            try:
                from scheduler import send_closing_report
                bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN", ""))
                os.environ["TELEGRAM_CHAT_ID"] = str(chat_id)
                await send_closing_report(bot)
            except Exception as e:
                await send(f"❌ {e}")

    elif cmd == "explain":
        msg = EXPLAIN_DICT.get(value.lower(), f"Unknown term: {value}")
        await send(msg)

    elif cmd == "watchlist_add":
        if value == "show":
            await context.bot.send_message(
                chat_id=chat_id,
                text="Which stock to add?",
                reply_markup=_ticker_kbd("watchlist_add"),
            )
        else:
            ticker = value.upper()
            wl_db.add_ticker(uid, ticker)
            wl = wl_db.get_watchlist(uid)
            await send(f"✅ Added <b>{_e(ticker)}</b>\nWatchlist: {', '.join(wl)}")

    elif cmd == "watchlist_remove":
        ticker = value.upper()
        wl_db.remove_ticker(uid, ticker)
        remaining = wl_db.get_watchlist(uid)
        msg = f"✅ Removed <b>{_e(ticker)}</b>"
        if remaining:
            msg += f"\nWatchlist: {', '.join(remaining)}"
        await send(msg)
