"""Format analysis results into readable Telegram messages."""
from fetcher import format_market_cap


def score_label(score: int) -> str:
    if score >= 70: return "🟢 Strong Buy Signal"
    if score >= 50: return "🟡 Watch / Accumulate"
    if score >= 30: return "🟠 Hold / Neutral"
    return "🔴 Avoid / Bearish"


def format_analyze_report(stock: dict, tech: dict, fund: dict, sentiment: dict) -> str:
    ticker    = stock["ticker"]
    name      = stock["name"]
    price     = stock["price"]
    chg       = stock["change_pct"]
    chg_emoji = "📈" if chg >= 0 else "📉"

    # Composite score
    composite = int(
        tech["score"]  * 0.30 +
        fund["score"]  * 0.25 +
        max(0, min(100, (sentiment["score"] + 1) * 50)) * 0.20 +
        50             * 0.25   # momentum + political placeholder for Phase 1
    )

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 *{name} ({ticker})*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"💵 *Price:* ${price}  {chg_emoji} {chg:+.2f}%",
        f"🏦 *Market Cap:* {format_market_cap(stock['market_cap'])}",
        f"📦 *Sector:* {stock['sector']}",
        "",
        "📅 *52-Week Range:*",
        f"   High: ${tech['week52_high']}  ({tech['high_label']})",
        f"   Low:  ${tech['week52_low']}   ({tech['low_label']})",
        "",
        "📈 *TECHNICAL SIGNALS*",
        f"   RSI ({tech['rsi']}): {tech['rsi_label']}",
        f"   MACD: {tech['macd_label']}",
        f"   MA:   {tech['ma_label'] or 'Not enough data yet'}",
    ]

    if tech["signals"]:
        lines.append("")
        lines.append("🚨 *ALERTS:*")
        for s in tech["signals"]:
            lines.append(f"   {s}")

    lines += ["", "📐 *FUNDAMENTAL SIGNALS*"]
    for note in fund["notes"]:
        lines.append(f"   {note}")

    lines += ["", f"📰 *NEWS SENTIMENT:* {sentiment['label']}"]
    for n in sentiment.get("scored", [])[:3]:
        lines.append(f"   • {n['title'][:80]}... {n['label']}")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🎯 *INVESTMENT SCORE: {composite}/100*",
        f"   {score_label(composite)}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "⚠️ _This is educational info, not financial advice._",
        "💡 _New? Try /explain rsi or /explain pe_",
    ]

    return "\n".join(lines)


EXPLAIN_DICT = {
    "rsi": (
        "📊 *RSI — Relative Strength Index*\n\n"
        "RSI measures if a stock has been bought or sold too aggressively.\n\n"
        "• *Below 30* = Oversold 🟢 — Stock may be cheap. Like a sale — but check WHY it dropped.\n"
        "• *Above 70* = Overbought 🔴 — Stock may be expensive. A pullback is possible.\n"
        "• *30–70* = Normal range 🟡\n\n"
        "📌 *Example:* NVDA RSI = 28 → It's been heavily sold. Many traders see this as a buying opportunity."
    ),
    "macd": (
        "📊 *MACD — Moving Average Convergence Divergence*\n\n"
        "MACD shows whether a stock's momentum is speeding up or slowing down.\n\n"
        "• *Bullish crossover* 🟢 = Short-term momentum rising above long-term. Think: car shifting into higher gear.\n"
        "• *Bearish crossover* 🔴 = Momentum slowing down. Could be time to be cautious.\n\n"
        "📌 *Example:* NVDA MACD crosses bullish → many traders take this as a buy signal."
    ),
    "pe": (
        "📊 *P/E Ratio — Price to Earnings*\n\n"
        "P/E tells you how many years of profit you're paying for when buying the stock.\n\n"
        "• *P/E 10* = You pay $10 for every $1 the company earns. Cheap.\n"
        "• *P/E 20* = Fair value for most companies.\n"
        "• *P/E 50+* = Very expensive. You're betting on future growth.\n\n"
        "📌 *Example:* NVDA P/E = 35 → Investors expect strong growth to justify the price."
    ),
    "52w": (
        "📊 *52-Week High & Low*\n\n"
        "This is the highest and lowest price the stock reached in the past year.\n\n"
        "• *Near 52W High* 🚀 = Strong momentum. Stock is at its best in a year.\n"
        "• *Near 52W Low* ⚠️ = Stock struggling. Either a bargain or a falling knife — research why.\n\n"
        "📌 *Tip:* Breakouts above the 52W high often signal strong upward momentum."
    ),
    "golden": (
        "📊 *Golden Cross & Death Cross*\n\n"
        "These are signals based on 50-day and 200-day Moving Averages.\n\n"
        "• *Golden Cross* 🌙 = 50-day average rises ABOVE 200-day. Historically bullish. Long-term uptrend beginning.\n"
        "• *Death Cross* ☠️ = 50-day average falls BELOW 200-day. Historically bearish. Downtrend warning.\n\n"
        "📌 *Tip:* Golden crosses on high volume are stronger signals."
    ),
    "volume": (
        "📊 *Volume Spike*\n\n"
        "Volume = how many shares were traded today vs the normal daily average.\n\n"
        "• *2x+ normal volume* = Something big is happening. Big investors are active.\n"
        "• High volume on UP day = Strong buying conviction 🟢\n"
        "• High volume on DOWN day = Heavy selling pressure 🔴\n\n"
        "📌 *Rule:* Never ignore a big price move without checking if volume confirms it."
    ),
    "sentiment": (
        "📊 *News Sentiment*\n\n"
        "The bot reads today's news headlines about the stock and scores them.\n\n"
        "• *Bullish* 🟢 = More positive news than negative\n"
        "• *Bearish* 🔴 = More negative news\n"
        "• *Neutral* 🟡 = Mixed or no significant news\n\n"
        "📌 *Tip:* Sentiment alone isn't enough — always combine with technical signals."
    ),
}
