"""Technical analysis signals with plain-English explanations."""
import pandas as pd
try:
    import pandas_ta as ta
    HAS_TA = True
except ImportError:
    HAS_TA = False


def calculate_rsi(hist: pd.DataFrame, period: int = 14) -> float:
    if HAS_TA:
        rsi_series = ta.rsi(hist["Close"], length=period)
        return round(rsi_series.iloc[-1], 2) if rsi_series is not None else None
    # Fallback manual calculation
    delta = hist["Close"].diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss
    rsi   = 100 - (100 / (1 + rs))
    return round(rsi.iloc[-1], 2)


def calculate_macd(hist: pd.DataFrame) -> dict:
    if HAS_TA:
        macd = ta.macd(hist["Close"])
        if macd is not None:
            return {
                "macd":   round(macd["MACD_12_26_9"].iloc[-1], 4),
                "signal": round(macd["MACDs_12_26_9"].iloc[-1], 4),
                "hist":   round(macd["MACDh_12_26_9"].iloc[-1], 4),
            }
    # Fallback
    ema12       = hist["Close"].ewm(span=12).mean()
    ema26       = hist["Close"].ewm(span=26).mean()
    macd_line   = ema12 - ema26
    signal_line = macd_line.ewm(span=9).mean()
    return {
        "macd":   round(macd_line.iloc[-1], 4),
        "signal": round(signal_line.iloc[-1], 4),
        "hist":   round((macd_line - signal_line).iloc[-1], 4),
    }


def calculate_moving_averages(hist: pd.DataFrame) -> dict:
    close = hist["Close"]
    ma50  = close.rolling(50).mean().iloc[-1]  if len(close) >= 50  else None
    ma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None
    return {
        "ma50":  round(ma50, 2)  if ma50  else None,
        "ma200": round(ma200, 2) if ma200 else None,
    }


def get_technical_signals(hist: pd.DataFrame) -> dict:
    """Run all technical indicators and return signals + plain English."""
    price  = hist["Close"].iloc[-1]
    rsi    = calculate_rsi(hist)
    macd   = calculate_macd(hist)
    mas    = calculate_moving_averages(hist)

    signals = []
    score   = 50  # neutral baseline

    # ── RSI ──────────────────────────────────────────────────
    rsi_label = ""
    if rsi is not None:
        if rsi < 30:
            rsi_label = "🟢 Oversold (potential buy zone)"
            score += 15
        elif rsi < 50:
            rsi_label = "🟡 Neutral-Low"
            score += 5
        elif rsi < 70:
            rsi_label = "🟡 Neutral-High"
            score -= 5
        else:
            rsi_label = "🔴 Overbought (caution)"
            score -= 15

    # ── MACD ─────────────────────────────────────────────────
    if macd["macd"] > macd["signal"]:
        macd_label = "🟢 Bullish crossover (momentum rising)"
        score += 10
    else:
        macd_label = "🔴 Bearish crossover (momentum falling)"
        score -= 10

    # ── Moving Averages ───────────────────────────────────────
    ma_label = ""
    if mas["ma50"] and mas["ma200"]:
        if mas["ma50"] > mas["ma200"]:
            ma_label = "🌙 Golden Cross — short-term trend above long-term (bullish)"
            score += 10
        else:
            ma_label = "☠️ Death Cross — short-term trend below long-term (bearish)"
            score -= 10
    elif mas["ma50"]:
        if price > mas["ma50"]:
            ma_label = "🟢 Price above 50-day average (positive momentum)"
            score += 5
        else:
            ma_label = "🔴 Price below 50-day average (weak momentum)"
            score -= 5

    # ── 52-Week position ──────────────────────────────────────
    week52_high   = hist["High"].max()
    week52_low    = hist["Low"].min()
    pct_from_high = round((price - week52_high) / week52_high * 100, 1)
    pct_from_low  = round((price - week52_low)  / week52_low  * 100, 1)
    high_label    = f"{pct_from_high}% from 52W high"
    low_label     = f"+{pct_from_low}% above 52W low"

    if pct_from_high >= -2:
        signals.append("🚀 Near 52-Week High Breakout!")
        score += 10
    if pct_from_low <= 5:
        signals.append("⚠️ Near 52-Week Low — watch closely")
        score -= 5

    return {
        "rsi":         rsi,
        "rsi_label":   rsi_label,
        "macd":        macd,
        "macd_label":  macd_label,
        "ma50":        mas["ma50"],
        "ma200":       mas["ma200"],
        "ma_label":    ma_label,
        "week52_high": round(week52_high, 2),
        "week52_low":  round(week52_low, 2),
        "high_label":  high_label,
        "low_label":   low_label,
        "signals":     signals,
        "score":       max(0, min(100, score)),
    }
