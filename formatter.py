"""Format analysis results into readable, beginner-friendly Telegram messages."""
from datetime import datetime
from zoneinfo import ZoneInfo
from fetcher import format_market_cap

CT = ZoneInfo("America/Chicago")


def ct_now_str() -> str:
    return datetime.now(CT).strftime("%a %b %d, %I:%M %p CT")


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
    ticker    = stock["ticker"]
    name      = stock["name"]
    price     = stock["price"]
    chg       = stock["change_pct"]
    chg_emoji = "📈" if chg >= 0 else "📉"

    composite = int(
        tech["score"]  * 0.30 +
        fund["score"]  * 0.25 +
        max(0, min(100, (sentiment["score"] + 1) * 50)) * 0.20 +
        50             * 0.25
    )

    # 52W range bar
    try:
        w52_hi = float(tech["week52_high"])
        w52_lo = float(tech["week52_low"])
        pct_of_range = ((price - w52_lo) / (w52_hi - w52_lo) * 100) if w52_hi != w52_lo else 50
        range_bar = "▓" * int(pct_of_range / 10) + "░" * (10 - int(pct_of_range / 10))
        range_desc = f"{range_bar}  {pct_of_range:.0f}% of yearly range"
    except Exception:
        range_desc = ""

    # Earnings warning
    earnings_line = ""
    try:
        ed = stock.get("earnings_date")
        if ed:
            from datetime import datetime, timezone
            if hasattr(ed, "to_pydatetime"):
                ed = ed.to_pydatetime()
            now = datetime.now(timezone.utc)
            ed_aware = ed.replace(tzinfo=timezone.utc) if ed.tzinfo is None else ed
            days_away = (ed_aware - now).days
            if days_away <= 0:
                earnings_line = "⚠️ *Earnings just passed* — watch for post-earnings move"
            elif days_away <= 7:
                earnings_line = f"🚨 *Earnings in {days_away} days* — HIGH RISK period. Price can swing ±20%+"
            elif days_away <= 14:
                earnings_line = f"⚠️ *Earnings in {days_away} days* — stocks often run up beforehand"
            else:
                earnings_line = f"📅 *Next earnings:* ~{days_away} days away"
    except Exception:
        pass

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 *{name} ({ticker})*",
        f"🕐 {ct_now_str()}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"💵 *Price:* ${price}  {chg_emoji} *{chg:+.2f}%* today",
        f"🏦 *Market Cap:* {format_market_cap(stock['market_cap'])}  |  *Sector:* {stock['sector']}",
    ]
    if earnings_line:
        lines.append(f"   {earnings_line}")

    # Risk indicators row
    risk_parts = []
    if stock.get("beta") is not None:
        b = stock["beta"]
        beta_label = "High volatility" if b > 1.5 else ("Low volatility" if b < 0.8 else "Normal volatility")
        risk_parts.append(f"Beta {b} ({beta_label})")
    if stock.get("short_interest") is not None:
        si = stock["short_interest"]
        si_label = "🔴 Squeeze risk!" if si > 20 else ("⚠️ Elevated" if si > 10 else "Normal")
        risk_parts.append(f"Short {si}% float ({si_label})")
    if risk_parts:
        lines.append(f"   📌 {' | '.join(risk_parts)}")

    lines += [
        "",
        "📅 *52-Week Price Range:*",
        f"   Low: ${tech['week52_low']}  ——  High: ${tech['week52_high']}",
    ]
    if range_desc:
        lines.append(f"   {range_desc}")
        lines.append(f"   _{tech['high_label']}_")

    # Support / Resistance / ATR
    if tech.get("support") and tech.get("resistance"):
        lines += [
            "",
            "🎯 *Key Price Levels (20-day):*",
            f"   🟢 Support:    ${tech['support']}  ({tech['pct_to_support']:+.1f}% below current)",
            f"   🔴 Resistance: ${tech['resistance']}  ({tech['pct_to_resist']:+.1f}% above current)",
        ]
        if tech.get("atr"):
            lines.append(
                f"   📐 Daily Range (ATR): ±${tech['atr']}  "
                f"_→ set stop-loss ~${round(price - tech['atr'] * 1.5, 2)}_"
            )

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "📈 *TECHNICAL SIGNALS*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"   RSI: *{tech['rsi']}*  — {tech['rsi_label']}",
        f"   MACD: {tech['macd_label']}",
        f"   Trend: {tech['ma_label'] or 'Not enough data yet'}",
    ]

    # Bollinger Bands
    bb = tech.get("bollinger", {})
    if bb.get("signal"):
        pct_b = bb.get("pct_b")
        pct_b_str = f"  ({pct_b}% of band)" if pct_b is not None else ""
        lines.append(f"   BB: {bb['signal']}{pct_b_str}")
        if bb.get("lower") and bb.get("upper"):
            lines.append(f"      _Lower band: ${bb['lower']}  |  Upper band: ${bb['upper']}_")

    if tech["signals"]:
        lines.append("")
        lines.append("🚨 *Active Alerts:*")
        for s in tech["signals"]:
            lines.append(f"   {s}")

    # Confidence tier
    confidence = tech.get("confidence", "")
    if confidence:
        lines += ["", f"   🎖️ *Signal Confidence:* {confidence}"]

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "📐 *COMPANY HEALTH*",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for note in fund["notes"]:
        lines.append(f"   {note}")
    if not fund["notes"]:
        lines.append("   ⚠️ Fundamental data unavailable — check again later")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📰 *NEWS SENTIMENT:* {sentiment['label']}",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for n in sentiment.get("scored", [])[:3]:
        lines.append(f"   • {n['title'][:75]}…")
        lines.append(f"     ↳ {n['label']}")

    if reddit:
        lines += [""]
        if reddit.get("available") and reddit.get("mentions", 0) > 0:
            lines += [
                "━━━━━━━━━━━━━━━━━━━━━━",
                f"📱 *REDDIT BUZZ:* {reddit['hype_label']}",
                "━━━━━━━━━━━━━━━━━━━━━━",
                f"   Mood: {reddit['sentiment']}",
                f"   Mentions (24h): *{reddit['mentions']}*  |  Upvotes: *{reddit['upvotes']:,}*",
                f"   _/reddit {ticker} for full post details_",
            ]
        elif reddit.get("available"):
            lines += [
                "━━━━━━━━━━━━━━━━━━━━━━",
                "📱 *REDDIT BUZZ:* 🔇 No WSB/Reddit mentions today",
                "━━━━━━━━━━━━━━━━━━━━━━",
            ]

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🎯 *INVESTMENT SCORE: {composite}/100*",
        f"   {score_label(composite)}",
        "",
        f"   📝 _{score_summary(composite, ticker, tech, fund, sentiment)}_",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "⚠️ _Educational only — not financial advice._",
        "💡 _/explain rsi · /explain 52w · /explain score_",
    ]

    return "\n".join(lines)
    ticker    = stock["ticker"]
    name      = stock["name"]
    price     = stock["price"]
    chg       = stock["change_pct"]
    chg_emoji = "📈" if chg >= 0 else "📉"

    composite = int(
        tech["score"]  * 0.30 +
        fund["score"]  * 0.25 +
        max(0, min(100, (sentiment["score"] + 1) * 50)) * 0.20 +
        50             * 0.25
    )

    # Derive position vs 52W range
    try:
        w52_hi = float(tech["week52_high"])
        w52_lo = float(tech["week52_low"])
        pct_of_range = ((price - w52_lo) / (w52_hi - w52_lo) * 100) if w52_hi != w52_lo else 50
        range_bar = "▓" * int(pct_of_range / 10) + "░" * (10 - int(pct_of_range / 10))
        range_desc = f"{range_bar}  {pct_of_range:.0f}% of yearly range"
    except Exception:
        range_desc = ""

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 *{name} ({ticker})*",
        f"🕐 {ct_now_str()}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"💵 *Price:* ${price}  {chg_emoji} *{chg:+.2f}%* today",
        f"🏦 *Market Cap:* {format_market_cap(stock['market_cap'])}",
        f"📦 *Industry:* {stock['sector']}",
        "",
        "📅 *52-Week Price Range:*",
        f"   Low: ${tech['week52_low']}  ——  High: ${tech['week52_high']}",
    ]
    if range_desc:
        lines.append(f"   {range_desc}")
        lines.append(f"   _{tech['high_label']}_")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "📈 *TECHNICAL SIGNALS*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"   RSI: *{tech['rsi']}*  — {tech['rsi_label']}",
        f"   MACD: {tech['macd_label']}",
        f"   Moving Avg: {tech['ma_label'] or 'Not enough data yet'}",
    ]

    if tech["signals"]:
        lines.append("")
        lines.append("🚨 *Active Alerts:*")
        for s in tech["signals"]:
            lines.append(f"   {s}")

    lines += [
        "",
        "🧠 *What this means (plain English):*",
        f"   RSI < 30 = stock may be oversold (possible buy zone)",
        f"   RSI > 70 = stock may be overbought (be cautious)",
        f"   _Run /explain rsi for a full lesson_",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "📐 *COMPANY HEALTH (Fundamentals)*",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for note in fund["notes"]:
        lines.append(f"   {note}")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📰 *NEWS SENTIMENT:* {sentiment['label']}",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for n in sentiment.get("scored", [])[:3]:
        lines.append(f"   • {n['title'][:75]}…")
        lines.append(f"     ↳ {n['label']}")

    # Reddit section (optional — gracefully skipped if not available)
    if reddit:
        lines += [""]
        if reddit.get("available") and reddit.get("mentions", 0) > 0:
            lines += [
                "━━━━━━━━━━━━━━━━━━━━━━",
                f"📱 *REDDIT BUZZ:* {reddit['hype_label']}",
                "━━━━━━━━━━━━━━━━━━━━━━",
                f"   Mood: {reddit['sentiment']}",
                f"   Mentions (24h): *{reddit['mentions']}*  |  Upvotes: *{reddit['upvotes']:,}*",
                "   _Run /reddit " + stock["ticker"] + " for full post details_",
            ]
        elif reddit.get("available"):
            lines += [
                "━━━━━━━━━━━━━━━━━━━━━━",
                "📱 *REDDIT BUZZ:* 🔇 No mentions in last 24h",
                "━━━━━━━━━━━━━━━━━━━━━━",
            ]

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🎯 *INVESTMENT SCORE: {composite}/100*",
        f"   {score_label(composite)}",
        "",
        f"   📝 _{score_summary(composite, ticker, tech, fund, sentiment)}_",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "⚠️ _Educational only — not financial advice._",
        "💡 _/explain rsi · /explain macd · /explain pe_",
    ]

    return "\n".join(lines)


EXPLAIN_DICT = {
    "rsi": (
        "📊 *RSI — Relative Strength Index*\n\n"
        "*Simple version:* RSI tells you if too many people are buying or selling a stock right now.\n\n"
        "• *Below 30* 🟢 = Oversold — heavy selling happened. May be a buying opportunity.\n"
        "  _Like a store clearance sale — but check WHY it's on sale._\n"
        "• *Above 70* 🔴 = Overbought — heavy buying happened. Stock may be due for a dip.\n"
        "• *30–70* 🟡 = Normal range — no extreme signal.\n\n"
        "📌 *Real example:* NVDA RSI dropped to 28 in Jan 2024 → it rallied 40% over the next 3 months."
    ),
    "macd": (
        "📊 *MACD — Momentum Indicator*\n\n"
        "*Simple version:* MACD shows whether a stock's speed (momentum) is increasing or decreasing.\n\n"
        "• *Bullish crossover* 🟢 = Momentum turning positive. Like a car shifting into a higher gear.\n"
        "• *Bearish crossover* 🔴 = Momentum slowing. The trend may be reversing.\n\n"
        "📌 *Tip:* MACD crossovers are more powerful when the RSI also confirms the direction."
    ),
    "pe": (
        "📊 *P/E Ratio — Price-to-Earnings*\n\n"
        "*Simple version:* How many years of profit are you paying for?\n\n"
        "• *P/E 10* = You pay $10 for every $1 of annual profit. Cheap.\n"
        "• *P/E 20* = Fair value for most stable companies.\n"
        "• *P/E 50+* = Very expensive — betting on future explosive growth.\n\n"
        "📌 *Context matters:* AI/tech stocks often have P/E 40–100 because investors expect massive growth."
    ),
    "52w": (
        "📊 *52-Week High & Low*\n\n"
        "*Simple version:* The highest and lowest price over the past 12 months.\n\n"
        "• *Near 52W High* 🚀 = Stock is at its strongest point in a year. Strong momentum.\n"
        "• *Near 52W Low* ⚠️ = Stock is at its weakest point. Could be a bargain — or still falling.\n\n"
        "📌 *Tip:* A *breakout* above the 52W high (on high volume) is one of the strongest buy signals traders use."
    ),
    "golden": (
        "📊 *Golden Cross & Death Cross*\n\n"
        "These compare the 50-day and 200-day moving averages.\n\n"
        "• *Golden Cross* 🌙 = 50-day average crosses ABOVE 200-day. Historically bullish — long-term uptrend.\n"
        "• *Death Cross* ☠️ = 50-day average crosses BELOW 200-day. Historically bearish — downtrend warning.\n\n"
        "📌 *History:* The S&P 500 golden cross in late 2023 preceded a 25% rally."
    ),
    "volume": (
        "📊 *Volume Spike*\n\n"
        "*Simple version:* Way more shares than normal were traded today.\n\n"
        "• *2x+ normal volume on UP day* 🟢 = Strong buying conviction — institutional money moving in.\n"
        "• *2x+ normal volume on DOWN day* 🔴 = Heavy selling — possible panic or bad news.\n\n"
        "📌 *Rule of thumb:* Never trust a price move without checking if volume confirms it."
    ),
    "sentiment": (
        "📊 *News Sentiment*\n\n"
        "*Simple version:* The bot reads today's headlines and scores the mood.\n\n"
        "• *Bullish* 🟢 = Headlines are mostly positive about the company\n"
        "• *Bearish* 🔴 = More negative news than positive\n"
        "• *Neutral* 🟡 = Mixed or no significant news today\n\n"
        "📌 *Tip:* Sentiment changes fast. Check again after earnings or major news events."
    ),
    "score": (
        "📊 *Investment Score (0–100)*\n\n"
        "The bot combines 4 signals into one easy score:\n\n"
        "• 30% Technical (RSI, MACD, Moving Averages)\n"
        "• 25% Fundamental (P/E, revenue growth, EPS)\n"
        "• 20% Sentiment (news headlines mood)\n"
        "• 25% Momentum (price trend, volume)\n\n"
        "🟢 70–100 = Strong Buy Signal\n"
        "🟡 50–70  = Worth watching\n"
        "🟠 30–50  = Mixed — hold off\n"
        "🔴 0–30   = Avoid for now\n\n"
        "📌 *Important:* No score is a guarantee. Always do your own research."
    ),
    "reddit": (
        "📱 *Reddit / WSB Social Sentiment*\n\n"
        "*Simple version:* How much retail traders on Reddit are talking about a stock.\n\n"
        "• *Extreme Hype* 🚀 = Thousands of mentions — could mean a short squeeze OR a pump-and-dump incoming\n"
        "• *High Buzz* 🔥 = Heavy retail interest — worth watching closely\n"
        "• *Moderate* 💬 = Normal chatter — not a strong signal alone\n"
        "• *Low/None* 🔇 = Institutions are more in control — less retail volatility\n\n"
        "📌 *Warning:* High WSB hype is a double-edged signal.\n"
        "   GameStop (GME) 2021 = extreme hype → 2,000% gain then 90% crash.\n"
        "   Always combine with RSI + fundamentals before acting."
    ),
}



