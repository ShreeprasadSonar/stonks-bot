"""Format analysis results into readable, beginner-friendly Telegram messages.
Uses HTML parse mode throughout — supports clickable hyperlinks in news.
"""
import html as _html
from datetime import datetime
from zoneinfo import ZoneInfo
from fetcher import format_market_cap

CT = ZoneInfo("America/Chicago")

DIV = "──────────────────────"   # clean thin divider


def ct_now_str() -> str:
    return datetime.now(CT).strftime("%a %b %d, %I:%M %p CT")


def _e(text) -> str:
    """Escape HTML special characters in user-provided content."""
    return _html.escape(str(text))


def score_label(score: int) -> str:
    if score >= 70: return "🟢 Strong Buy Signal"
    if score >= 50: return "🟡 Watch — Worth Monitoring"
    if score >= 30: return "🟠 Hold — Mixed Signals"
    return "🔴 Avoid — Bearish Signs"


def score_summary(score: int, ticker: str, tech: dict, fund: dict, sentiment: dict) -> str:
    """One-sentence plain-English explanation of the score."""
    reasons = []
    if tech["score"] >= 60:
        reasons.append("technical charts are looking bullish")
    elif tech["score"] <= 35:
        reasons.append("technical charts look weak")
    if fund["score"] >= 60:
        reasons.append("the company's financials are strong")
    elif fund["score"] <= 35:
        reasons.append("earnings/growth look concerning")
    sent_score = max(0, min(100, (sentiment["score"] + 1) * 50))
    if sent_score >= 60:
        reasons.append("recent news is mostly positive")
    elif sent_score <= 35:
        reasons.append("news headlines are mostly negative")
    if not reasons:
        return f"Signals are mixed for {ticker} — monitor closely before acting."
    return f"{ticker} scores {score}/100 because {', and '.join(reasons)}."


def format_analyze_report(stock: dict, tech: dict, fund: dict, sentiment: dict, reddit: dict = None) -> str:
    """
    Returns an HTML-formatted report for Telegram (use ParseMode.HTML).
    News headlines are embedded hyperlinks — tap to read the full article.
    """
    ticker    = _e(stock["ticker"])
    name      = _e(stock["name"])
    price     = stock["price"]
    chg       = stock["change_pct"]
    chg_emoji = "📈" if chg >= 0 else "📉"
    chg_color = "+" if chg >= 0 else ""

    composite = int(
        tech["score"]  * 0.30 +
        fund["score"]  * 0.25 +
        max(0, min(100, (sentiment["score"] + 1) * 50)) * 0.20 +
        50             * 0.25
    )

    # ── 52W range bar ─────────────────────────────────────────
    try:
        w52_hi = float(tech["week52_high"])
        w52_lo = float(tech["week52_low"])
        pct_of_range = ((price - w52_lo) / (w52_hi - w52_lo) * 100) if w52_hi != w52_lo else 50
        blocks   = int(pct_of_range / 10)
        range_bar = "▓" * blocks + "░" * (10 - blocks)
        range_desc = f"{range_bar}  <i>{pct_of_range:.0f}% of yearly range</i>"
    except Exception:
        range_desc = ""

    # ── Earnings warning ──────────────────────────────────────
    earnings_line = ""
    try:
        ed = stock.get("earnings_date")
        if ed:
            from datetime import datetime as _dt, timezone
            if hasattr(ed, "to_pydatetime"):
                ed = ed.to_pydatetime()
            now      = _dt.now(timezone.utc)
            ed_aware = ed.replace(tzinfo=timezone.utc) if ed.tzinfo is None else ed
            days     = (ed_aware - now).days
            if days <= 0:
                earnings_line = "⚠️ <b>Earnings just passed</b> — watch for post-earnings move"
            elif days <= 7:
                earnings_line = f"🚨 <b>Earnings in {days} days</b> — HIGH RISK. Price can swing ±20%+"
            elif days <= 14:
                earnings_line = f"⚠️ <b>Earnings in {days} days</b> — stocks often run up beforehand"
            else:
                earnings_line = f"📅 Next earnings: ~{days} days away"
    except Exception:
        pass

    # ── Header ────────────────────────────────────────────────
    lines = [
        f"📊 <b>{name} ({ticker})</b>",
        f"🕐 {ct_now_str()}",
        DIV,
        "",
        f"💵 <b>${price}</b>  {chg_emoji} <b>{chg_color}{chg:.2f}%</b> today",
        f"🏦 {format_market_cap(stock['market_cap'])} cap  ·  {_e(stock['sector'])}",
    ]

    if earnings_line:
        lines += ["", earnings_line]

    # Risk row
    risk_parts = []
    if stock.get("beta") is not None:
        b = stock["beta"]
        blabel = "High volatility" if b > 1.5 else ("Low volatility" if b < 0.8 else "Normal volatility")
        risk_parts.append(f"Beta {b} ({blabel})")
    if stock.get("short_interest") is not None:
        si = stock["short_interest"]
        si_label = "🔴 Squeeze risk!" if si > 20 else ("⚠️ Elevated" if si > 10 else "Normal")
        risk_parts.append(f"Short {si}% float ({si_label})")
    if risk_parts:
        lines.append(f"📌 {_e('  ·  '.join(risk_parts))}")

    # ── 52-Week range ─────────────────────────────────────────
    lines += [
        "",
        DIV,
        f"📅 <b>52-Week Range</b>",
        f"   Low <b>${tech['week52_low']}</b>  {range_bar if range_desc else ''}  High <b>${tech['week52_high']}</b>",
    ]
    if range_desc:
        lines.append(f"   {range_desc}  ·  <i>{_e(tech['high_label'])}</i>")

    # ── Support / Resistance / ATR ────────────────────────────
    if tech.get("support") and tech.get("resistance"):
        lines += [
            "",
            f"🎯 <b>Key Levels</b>  <i>(20-day)</i>",
            f"   🟢 Support    <b>${tech['support']}</b>  <i>{tech['pct_to_support']:+.1f}% below</i>",
            f"   🔴 Resistance <b>${tech['resistance']}</b>  <i>{tech['pct_to_resist']:+.1f}% above</i>",
        ]
        if tech.get("atr"):
            sl = round(price - tech["atr"] * 1.5, 2)
            lines.append(f"   📐 ATR ±${tech['atr']}  →  <i>stop-loss ~${sl}</i>")

    # ── Technical signals ─────────────────────────────────────
    lines += [
        "",
        DIV,
        "📈 <b>TECHNICAL ANALYSIS</b>",
        "",
        f"   RSI <b>{tech['rsi']}</b>  {_e(tech['rsi_label'])}",
        f"   MACD   {_e(tech['macd_label'])}",
        f"   Trend  {_e(tech['ma_label'] or 'Not enough data yet')}",
    ]

    bb = tech.get("bollinger", {})
    if bb.get("signal"):
        pct_b_str = f"  <i>({bb['pct_b']}% of band)</i>" if bb.get("pct_b") is not None else ""
        lines.append(f"   BB     {_e(bb['signal'])}{pct_b_str}")

    if tech.get("signals"):
        lines += ["", "🚨 <b>Active Alerts</b>"]
        for s in tech["signals"]:
            lines.append(f"   {_e(s)}")

    confidence = tech.get("confidence", "")
    if confidence:
        lines += ["", f"   🎖️ <b>Confidence:</b> {_e(confidence)}"]

    # ── Fundamentals ──────────────────────────────────────────
    lines += [
        "",
        DIV,
        "📐 <b>COMPANY HEALTH</b>",
        "",
    ]
    if fund["notes"]:
        for note in fund["notes"]:
            lines.append(f"   {_e(note)}")
    else:
        lines.append("   ⚠️ Fundamental data unavailable — check again later")

    # ── News with clickable links ─────────────────────────────
    lines += [
        "",
        DIV,
        f"📰 <b>NEWS</b>  ·  {_e(sentiment['label'])}",
        "<i>Tap any headline to read the full article</i>",
        "",
    ]
    top_news = sentiment.get("scored", [])[:4]
    if top_news:
        for n in top_news:
            title = _e(n["title"][:80])
            url   = n.get("link", "")
            label = _e(n.get("label", ""))
            source = _e(n.get("source", ""))
            source_str = f"  <i>{source}</i>" if source else ""
            if url:
                lines.append(f'   • <a href="{url}">{title}</a>{source_str}')
            else:
                lines.append(f"   • {title}{source_str}")
            lines.append(f"     ↳ {label}")
    else:
        lines.append("   No news found today")

    # ── StockTwits ────────────────────────────────────────────
    if reddit and reddit.get("available"):
        lines += ["", DIV]
        if reddit.get("mentions", 0) > 0:
            watchers = reddit.get("watchers", 0)
            watcher_str = f"  ·  👀 <b>{watchers:,}</b> watching" if watchers else ""
            lines += [
                f"📱 <b>STOCKTWITS</b>  ·  {_e(reddit['hype_label'])}",
                "",
                f"   Mood: {_e(reddit['sentiment'])}{watcher_str}",
                f"   Recent messages: <b>{reddit['mentions']}</b>",
                f"   <i>Tap to view on StockTwits →</i> "
                f'<a href="https://stocktwits.com/symbol/{ticker}">stocktwits.com/{ticker}</a>',
            ]
        else:
            lines += [
                "📱 <b>STOCKTWITS</b>  ·  🔇 Quiet — no recent activity",
            ]

    # ── Investment Score ──────────────────────────────────────
    score_bar = "🟩" * (composite // 10) + "⬜" * (10 - composite // 10)
    lines += [
        "",
        DIV,
        f"🎯 <b>INVESTMENT SCORE: {composite}/100</b>",
        f"   {score_bar}",
        f"   {score_label(composite)}",
        "",
        f"   <i>{_e(score_summary(composite, stock['ticker'], tech, fund, sentiment))}</i>",
        DIV,
        "",
        "⚠️ <i>Educational only — not financial advice</i>",
        "💡 /explain rsi  ·  /explain score  ·  /explain 52w",
    ]

    return "\n".join(lines)


EXPLAIN_DICT = {
    "rsi": (
        "📊 <b>RSI — Relative Strength Index</b>\n\n"
        "<b>Simple version:</b> RSI tells you if too many people are buying or selling a stock right now.\n\n"
        "• <b>Below 30</b> 🟢 = Oversold — heavy selling happened. May be a buying opportunity.\n"
        "  <i>Like a store clearance sale — but check WHY it's on sale.</i>\n"
        "• <b>Above 70</b> 🔴 = Overbought — heavy buying happened. Stock may be due for a dip.\n"
        "• <b>30–70</b> 🟡 = Normal range — no extreme signal.\n\n"
        "📌 <b>Real example:</b> NVDA RSI dropped to 28 in Jan 2024 → it rallied 40% over the next 3 months."
    ),
    "macd": (
        "📊 <b>MACD — Momentum Indicator</b>\n\n"
        "<b>Simple version:</b> MACD shows whether a stock's speed (momentum) is increasing or decreasing.\n\n"
        "• <b>Bullish crossover</b> 🟢 = Momentum turning positive. Like a car shifting into a higher gear.\n"
        "• <b>Bearish crossover</b> 🔴 = Momentum slowing. The trend may be reversing.\n\n"
        "📌 <b>Tip:</b> MACD crossovers are more powerful when the RSI also confirms the direction."
    ),
    "pe": (
        "📊 <b>P/E Ratio — Price-to-Earnings</b>\n\n"
        "<b>Simple version:</b> How many years of profit are you paying for?\n\n"
        "• <b>P/E 10</b> = You pay $10 for every $1 of annual profit. Cheap.\n"
        "• <b>P/E 20</b> = Fair value for most stable companies.\n"
        "• <b>P/E 50+</b> = Very expensive — betting on future explosive growth.\n\n"
        "📌 <b>Context matters:</b> AI/tech stocks often have P/E 40–100 because investors expect massive growth."
    ),
    "52w": (
        "📊 <b>52-Week High &amp; Low</b>\n\n"
        "<b>Simple version:</b> The highest and lowest price over the past 12 months.\n\n"
        "• <b>Near 52W High</b> 🚀 = Stock is at its strongest point in a year. Strong momentum.\n"
        "• <b>Near 52W Low</b> ⚠️ = Stock is at its weakest point. Could be a bargain — or still falling.\n\n"
        "📌 <b>Tip:</b> A breakout above the 52W high (on high volume) is one of the strongest buy signals traders use."
    ),
    "golden": (
        "📊 <b>Golden Cross &amp; Death Cross</b>\n\n"
        "These compare the 50-day and 200-day moving averages.\n\n"
        "• <b>Golden Cross</b> 🌙 = 50-day crosses ABOVE 200-day. Historically bullish — long-term uptrend.\n"
        "• <b>Death Cross</b> ☠️ = 50-day crosses BELOW 200-day. Historically bearish — downtrend warning.\n\n"
        "📌 <b>History:</b> The S&amp;P 500 golden cross in late 2023 preceded a 25% rally."
    ),
    "volume": (
        "📊 <b>Volume Spike</b>\n\n"
        "<b>Simple version:</b> Way more shares than normal were traded today.\n\n"
        "• <b>2x+ normal volume on UP day</b> 🟢 = Strong buying conviction — institutional money moving in.\n"
        "• <b>2x+ normal volume on DOWN day</b> 🔴 = Heavy selling — possible panic or bad news.\n\n"
        "📌 <b>Rule of thumb:</b> Never trust a price move without checking if volume confirms it."
    ),
    "sentiment": (
        "📊 <b>News Sentiment</b>\n\n"
        "<b>Simple version:</b> The bot reads today's headlines and scores the mood.\n\n"
        "• <b>Bullish</b> 🟢 = Headlines are mostly positive about the company\n"
        "• <b>Bearish</b> 🔴 = More negative news than positive\n"
        "• <b>Neutral</b> 🟡 = Mixed or no significant news today\n\n"
        "📌 <b>Tip:</b> Sentiment changes fast. Check again after earnings or major news events."
    ),
    "score": (
        "📊 <b>Investment Score (0–100)</b>\n\n"
        "The bot combines 4 signals into one easy score:\n\n"
        "• 30% Technical (RSI, MACD, Moving Averages)\n"
        "• 25% Fundamental (P/E, revenue growth, EPS)\n"
        "• 20% Sentiment (news headlines mood)\n"
        "• 25% Momentum (price trend, volume)\n\n"
        "🟢 <b>70–100</b> = Strong Buy Signal\n"
        "🟡 <b>50–70</b>  = Worth watching\n"
        "🟠 <b>30–50</b>  = Mixed — hold off\n"
        "🔴 <b>0–30</b>   = Avoid for now\n\n"
        "📌 <b>Important:</b> No score is a guarantee. Always do your own research."
    ),
    "bb": (
        "📊 <b>Bollinger Bands</b>\n\n"
        "<b>Simple version:</b> A price channel showing normal vs extreme price moves.\n\n"
        "• <b>At Lower Band</b> 🟢 = Price is unusually low — possible bounce zone.\n"
        "• <b>At Upper Band</b> 🔴 = Price is unusually high — possible pullback zone.\n"
        "• <b>Mid-Band</b> = Normal territory — no strong signal.\n\n"
        "📌 <b>Power tip:</b> When RSI &lt; 35 AND price touches the lower band at the same time → "
        "that's a high-confidence oversold signal. Both indicators agreeing = stronger signal."
    ),
    "reddit": (
        "📱 <b>StockTwits Social Sentiment</b>\n\n"
        "<b>Simple version:</b> How much retail traders on StockTwits are talking about a stock.\n"
        "StockTwits is finance-only — every post is about stocks, so it's a cleaner signal than Reddit.\n\n"
        "• <b>Extreme Hype</b> 🚀 = High message volume — strong retail interest\n"
        "• <b>High Buzz</b> 🔥 = Active discussion — worth monitoring\n"
        "• <b>Moderate</b> 💬 = Normal chatter — not a strong signal alone\n"
        "• <b>Low/None</b> 🔇 = Quiet — institutional action may dominate\n\n"
        "📌 <b>Sentiment labels:</b> Traders self-tag posts as Bullish 👍 or Bearish 👎.\n"
        "When 65%+ tag Bullish with high activity — that's meaningful retail conviction.\n\n"
        "⚠️ <b>Warning:</b> Social hype moves fast. Always combine with RSI + fundamentals before acting."
    ),
}

