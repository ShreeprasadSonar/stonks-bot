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

# Cache trending tickers so we don't hit Yahoo on every button press
_trending_cache: list = []
_trending_cache_time: float = 0.0


async def _get_suggestion_tickers() -> list:
    """
    Returns up to 8 suggestion tickers: trending-first, then popular fallbacks.
    Result is cached for 10 minutes to avoid repeated network calls.
    """
    import time
    global _trending_cache, _trending_cache_time
    if time.time() - _trending_cache_time < 600 and _trending_cache:
        return _trending_cache[:8]
    try:
        from reddit import get_trending_tickers
        SKIP = {"SPY", "QQQ", "DIA", "IWM", "VIX", "GLD", "SLV", "USO", "TLT", "BTC-USD", "ETH-USD"}
        live = [t for t in get_trending_tickers(20) if t.isalpha() and len(t) <= 5 and t not in SKIP]
        # Merge: trending first, fill remaining slots with popular fallbacks
        seen, merged = set(), []
        for t in live + POPULAR_TICKERS:
            if t not in seen:
                seen.add(t)
                merged.append(t)
        _trending_cache      = merged[:8]
        _trending_cache_time = time.time()
    except Exception:
        _trending_cache = POPULAR_TICKERS[:8]
    return _trending_cache


async def _ticker_kbd(cmd: str) -> InlineKeyboardMarkup:
    """Inline keyboard with live trending + popular tickers."""
    tickers = await _get_suggestion_tickers()
    rows, row = [], []
    for t in tickers:
        row.append(InlineKeyboardButton(t, callback_data=f"{cmd}:{t}"))
        if len(row) == 4:
            rows.append(row); row = []
    if row:
        rows.append(row)
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
            reply_markup=await _ticker_kbd("analyze"),
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


# ── /market  — full market intelligence dashboard
async def cmd_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Full market dashboard: movers + sectors + social + trends + narratives."""
    from fetcher import get_top_movers
    from technical import get_technical_signals
    from reddit import get_dynamic_tickers, get_trending_tickers

    # ── Sector deep-dive if arg given: /market AI
    if context.args:
        sector_name = " ".join(context.args).title()
        # Special keyword: /market themes
        if context.args[0].lower() == "themes":
            await update.message.reply_text("📡 Scanning market narratives…")
            try:
                from themes import score_themes, format_themes_report
                results = score_themes(use_trends=False)
                await update.message.reply_text(format_themes_report(results), parse_mode=ParseMode.HTML)
            except Exception as e:
                await update.message.reply_text(f"❌ Themes scan failed: {e}")
            return

        matched = next(
            (k for k in SECTORS if k.lower() in sector_name.lower() or sector_name.lower() in k.lower()), None
        )
        if matched:
            await _send_sector_detail(update, matched)
            return
        await update.message.reply_text(
            f"Unknown sector. Available: {', '.join(SECTORS.keys())} · themes",
            parse_mode=ParseMode.HTML,
        )
        return

    # ── Full dashboard (no args) ──────────────────────────────────────────
    await update.message.reply_text(
        "📊 Building market dashboard…\n<i>~4 sections, takes ~20 seconds</i>",
        parse_mode=ParseMode.HTML,
    )

    # ── MSG 1: Top Movers ─────────────────────────────────────────────────
    try:
        all_tickers = get_dynamic_tickers()
    except Exception:
        all_tickers = [t for tickers in SECTORS.values() for t in tickers]

    movers = get_top_movers(all_tickers)
    gainers = sorted(movers, key=lambda x: x["change_pct"], reverse=True)[:5]
    losers  = sorted(movers, key=lambda x: x["change_pct"])[:3]

    m1 = ["<b>📈 TOP MOVERS TODAY</b>", "─────────────────────", ""]
    m1.append("<b>Gainers</b>")
    for m in gainers:
        vol_flag = "  ⚡" if m["volume_ratio"] > 2.5 else ""
        tech     = get_technical_signals(m["history"])
        rsi_str  = f"  RSI {tech['rsi']}" if tech.get("rsi") else ""
        m1.append(f"  ▲ <b>{m['ticker']}</b>  ${m['price']}  <b>+{m['change_pct']:.2f}%</b>{vol_flag}{rsi_str}")

    m1 += ["", "<b>Laggards</b>"]
    for m in losers:
        if m["change_pct"] < 0:
            m1.append(f"  ▼ <b>{m['ticker']}</b>  ${m['price']}  <b>{m['change_pct']:.2f}%</b>")

    # Volume spikes
    vol_spikes = [m for m in movers if m["volume_ratio"] > 3][:3]
    if vol_spikes:
        m1 += ["", "<b>⚡ Unusual Volume</b>  <i>(3x+ normal — someone is moving)</i>"]
        for m in vol_spikes:
            m1.append(f"  <b>{m['ticker']}</b>  {m['volume_ratio']:.1f}x normal volume")

    await update.message.reply_text("\n".join(m1), parse_mode=ParseMode.HTML)

    # ── MSG 2: Sector Snapshot ────────────────────────────────────────────
    m2 = ["<b>📊 SECTOR SNAPSHOT</b>", "─────────────────────", ""]
    for sector, tickers in SECTORS.items():
        sector_data = [m for m in movers if m["ticker"] in tickers]
        if not sector_data:
            continue
        avg_chg = sum(m["change_pct"] for m in sector_data) / len(sector_data)
        trend   = "▲" if avg_chg >= 0 else "▼"
        best    = max(sector_data, key=lambda x: x["change_pct"])
        worst   = min(sector_data, key=lambda x: x["change_pct"])
        bar     = "🟩" * max(0, min(5, int((avg_chg + 3) / 1.2))) + "⬜" * max(0, 5 - max(0, min(5, int((avg_chg + 3) / 1.2))))
        m2.append(
            f"<b>{sector}</b>  {bar}  {trend} {avg_chg:+.1f}%\n"
            f"  Best: <b>{best['ticker']}</b> {best['change_pct']:+.1f}%  ·  "
            f"Worst: <b>{worst['ticker']}</b> {worst['change_pct']:+.1f}%"
        )

    # Inline buttons to drill into each sector
    sector_rows = [[InlineKeyboardButton(s, callback_data=f"market:{s}") for s in list(SECTORS.keys())[i:i+2]]
                   for i in range(0, len(SECTORS), 2)]
    await update.message.reply_text(
        "\n".join(m2),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(sector_rows),
    )

    # ── MSG 3: Social Sentiment ───────────────────────────────────────────
    m3 = ["<b>💬 SOCIAL SENTIMENT</b>", "─────────────────────", ""]

    # Yahoo Finance trending
    try:
        trending = get_trending_tickers(15)
        if trending:
            m3.append("<b>🔥 Yahoo Finance Trending</b>  <i>(most-searched right now)</i>")
            ranked = "  ".join(f"<b>{_e(t)}</b>" for t in trending[:10])
            m3 += [f"  {ranked}", ""]
    except Exception:
        pass

    # Reddit hot tickers
    try:
        hot = get_reddit_hot_tickers(limit=8)
        if hot:
            m3.append("<b>Reddit Buzz</b>  <i>r/wallstreetbets · r/stocks</i>")
            for h in hot[:6]:
                bar = "█" * min(10, h["mentions"] // 2) if h["mentions"] > 1 else "░"
                m3.append(f"  <b>{_e(h['ticker'])}</b>  {bar}  {h['mentions']} mentions")
            m3.append("")
    except Exception:
        pass

    # News sentiment for top 3 movers
    try:
        from sentiment import score_news
        from news import get_news
        m3.append("<b>News Mood — Top Movers</b>")
        for m in gainers[:3]:
            articles = get_news(m["ticker"], limit=5)
            sent     = score_news(articles)
            m3.append(f"  <b>{m['ticker']}</b>  {sent['label']}")
    except Exception:
        pass

    await update.message.reply_text("\n".join(m3), parse_mode=ParseMode.HTML)

    # ── MSG 4: Narrative Tracker ──────────────────────────────────────────
    try:
        from themes import score_themes
        theme_results = score_themes(use_trends=False)
        hot_themes    = [t for t in theme_results if t["score"] >= 10][:5]

        m4 = ["<b>📡 NARRATIVE TRACKER</b>", "<i>What smart money is focused on</i>", "─────────────────────", ""]
        for th in hot_themes:
            tickers_str = "  ".join(f"<b>{_e(tk)}</b>" for tk in th["tickers"][:5])
            m4.append(f"{th['momentum']}  <b>{_e(th['name'])}</b>")
            m4.append(f"  {tickers_str}")
            if th["top_headlines"]:
                m4.append(f"  <i>📰 {_e(th['top_headlines'][0][:90])}</i>")
            m4.append("")

        themes_btn = [[InlineKeyboardButton("📡 Full Narrative Report", callback_data="market:themes")]]
        await update.message.reply_text(
            "\n".join(m4),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(themes_btn),
        )
    except Exception as e:
        await update.message.reply_text(f"<i>Narrative tracker unavailable: {e}</i>", parse_mode=ParseMode.HTML)


async def _send_sector_detail(update, sector_name: str):
    """Send a detailed breakdown of a single sector."""
    from technical import get_technical_signals
    from sentiment import score_news
    from news import get_news

    await update.message.reply_text(f"Fetching <b>{_e(sector_name)}</b> sector detail…", parse_mode=ParseMode.HTML)
    movers = get_top_movers(SECTORS[sector_name])

    lines = [f"<b>{_e(sector_name)} Sector — Full View</b>", "─────────────────────", ""]
    for m in sorted(movers, key=lambda x: x["change_pct"], reverse=True):
        arrow    = "▲" if m["change_pct"] >= 0 else "▼"
        vol_flag = "  ⚡" if m["volume_ratio"] > 2 else ""
        tech     = get_technical_signals(m["history"])
        rsi_str  = f"  RSI {tech['rsi']}" if tech.get("rsi") else ""

        # Quick news sentiment
        try:
            articles = get_news(m["ticker"], limit=3)
            sent     = score_news(articles)
            mood     = sent["label"]
        except Exception:
            mood = ""

        mood_str = f"  {mood}" if mood else ""
        lines.append(
            f"<b>{m['ticker']}</b>  ${m['price']}  {arrow} {m['change_pct']:+.2f}%"
            f"{vol_flag}{rsi_str}{mood_str}"
        )
        if tech.get("signals"):
            for sig in tech["signals"][:1]:
                lines.append(f"  <i>⚡ {_e(sig)}</i>")

    lines += ["", "/analyze &lt;TICKER&gt; for a deep-dive"]
    ticker_btns = [[InlineKeyboardButton(m["ticker"], callback_data=f"analyze:{m['ticker']}") for m in movers[i:i+4]]
                   for i in range(0, len(movers), 4)]
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(ticker_btns),
    )


# ── /social  (replaces /reddit + /buzz + old /social)
async def cmd_social(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reddit + Google Trends + Congress + Finviz for a ticker."""
    if not context.args:
        await update.message.reply_text(
            "Which stock do you want the social intelligence report for?",
            reply_markup=await _ticker_kbd("social"),
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
            reply_markup=await _ticker_kbd("political"),
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
            reply_markup=await _ticker_kbd("watchlist_add"),
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
        if value == "themes":
            await send("📡 Scanning market narratives…")
            try:
                from themes import score_themes, format_themes_report
                results = score_themes(use_trends=False)
                await send(format_themes_report(results))
            except Exception as e:
                await send(f"❌ Themes scan failed: {e}")
            return
        sector_name = value.title()
        matched = next((k for k in SECTORS if k.lower() in sector_name.lower()), None)
        if matched:
            from technical import get_technical_signals
            from sentiment import score_news
            from news import get_news
            movers = get_top_movers(SECTORS[matched])
            lines  = [f"<b>{_e(matched)} Sector</b>", "─────────────────────", ""]
            for m in sorted(movers, key=lambda x: x["change_pct"], reverse=True):
                arrow    = "▲" if m["change_pct"] >= 0 else "▼"
                vol_flag = "  ⚡" if m["volume_ratio"] > 2 else ""
                tech     = get_technical_signals(m["history"])
                rsi_str  = f"  RSI {tech['rsi']}" if tech.get("rsi") else ""
                try:
                    sent = score_news(get_news(m["ticker"], limit=3))
                    mood = f"  {sent['label']}"
                except Exception:
                    mood = ""
                lines.append(f"<b>{m['ticker']}</b>  ${m['price']}  {arrow} {m['change_pct']:+.2f}%{vol_flag}{rsi_str}{mood}")
            lines.append("\nTap a ticker for full analysis:")
            ticker_btns = [[InlineKeyboardButton(m["ticker"], callback_data=f"analyze:{m['ticker']}") for m in movers[i:i+4]]
                           for i in range(0, len(movers), 4)]
            await context.bot.send_message(
                chat_id=chat_id, text="\n".join(lines),
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(ticker_btns),
            )

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
                reply_markup=await _ticker_kbd("watchlist_add"),
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
