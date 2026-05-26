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


def calculate_atr(hist: pd.DataFrame, period: int = 14) -> float:
    """Average True Range — measures daily volatility in dollar terms."""
    high  = hist["High"]
    low   = hist["Low"]
    close = hist["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().iloc[-1]
    return round(float(atr), 2) if not pd.isna(atr) else None


def get_support_resistance(hist: pd.DataFrame) -> dict:
    """
    Simple key price levels from recent price action.
    - Resistance = highest high in last 20 trading days
    - Support = lowest low in last 20 trading days
    - Also uses 50-day MA as dynamic support/resistance
    """
    price   = float(hist["Close"].iloc[-1])
    recent  = hist.tail(20)
    resist  = round(float(recent["High"].max()), 2)
    support = round(float(recent["Low"].min()),  2)

    pct_to_resist  = round((resist  - price) / price * 100, 1)
    pct_to_support = round((price - support) / price * 100, 1)

    return {
        "resistance":      resist,
        "support":         support,
        "pct_to_resist":   pct_to_resist,    # + means upside to resistance
        "pct_to_support":  pct_to_support,   # + means downside to support
    }


def calculate_bollinger_bands(hist: pd.DataFrame, period: int = 20) -> dict:
    """
    Bollinger Bands: 20-day MA ± 2 standard deviations.
    Lower band touch + RSI < 35 = high-confidence oversold zone.
    Upper band touch + RSI > 65 = high-confidence overbought zone.
    """
    if len(hist) < period:
        return {"upper": None, "lower": None, "mid": None, "signal": "", "pct_b": None}
    close  = hist["Close"].astype(float)
    mid    = close.rolling(period).mean().iloc[-1]
    std    = close.rolling(period).std().iloc[-1]
    upper  = mid + 2 * std
    lower  = mid - 2 * std
    price  = float(close.iloc[-1])
    band_w = upper - lower if (upper - lower) != 0 else 1
    pct_b  = round((price - lower) / band_w * 100, 1)   # 0=at lower, 100=at upper

    if price <= lower * 1.01:
        signal = "🟢 At Lower Band — potential bounce zone (oversold region)"
    elif price >= upper * 0.99:
        signal = "🔴 At Upper Band — potential pullback zone (overbought region)"
    elif pct_b < 30:
        signal = "🟡 Below Mid-Band — mild weakness"
    elif pct_b > 70:
        signal = "🟡 Above Mid-Band — mild strength"
    else:
        signal = "⚪ Mid-Band — no strong Bollinger signal"

    return {
        "upper":  round(float(upper), 2),
        "lower":  round(float(lower), 2),
        "mid":    round(float(mid), 2),
        "signal": signal,
        "pct_b":  pct_b,
    }


def get_technical_signals(hist: pd.DataFrame) -> dict:
    """Run all technical indicators and return signals + plain English."""
    price  = float(hist["Close"].iloc[-1])
    rsi    = calculate_rsi(hist)
    macd   = calculate_macd(hist)
    mas    = calculate_moving_averages(hist)
    atr    = calculate_atr(hist)
    levels = get_support_resistance(hist)
    bb     = calculate_bollinger_bands(hist)

    signals = []
    score   = 50

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
            ma_label = "🌙 Golden Cross — uptrend confirmed (bullish)"
            score += 10
        else:
            ma_label = "☠️ Death Cross — downtrend confirmed (bearish)"
            score -= 10
    elif mas["ma50"]:
        if price > mas["ma50"]:
            ma_label = "🟢 Price above 50-day avg (positive momentum)"
            score += 5
        else:
            ma_label = "🔴 Price below 50-day avg (weak momentum)"
            score -= 5

    # ── 52-Week position ──────────────────────────────────────
    week52_high   = hist["High"].max()
    week52_low    = hist["Low"].min()
    pct_from_high = round((price - float(week52_high)) / float(week52_high) * 100, 1)
    pct_from_low  = round((price - float(week52_low))  / float(week52_low)  * 100, 1)
    high_label    = f"{pct_from_high}% from 52W high"
    low_label     = f"+{pct_from_low}% above 52W low"

    if pct_from_high >= -2:
        signals.append("🚀 Near 52-Week High — potential breakout!")
        score += 10
    if pct_from_low <= 5:
        signals.append("⚠️ Near 52-Week Low — watch closely")
        score -= 5

    # ── Bollinger Bands ──────────────────────────────────────
    if bb["signal"]:
        if "Lower Band" in bb["signal"] and rsi is not None and rsi < 35:
            signals.append("🟢 BB + RSI: Double oversold confirmation — high-confidence buy zone")
            score += 8
        elif "Upper Band" in bb["signal"] and rsi is not None and rsi > 65:
            signals.append("🔴 BB + RSI: Double overbought confirmation — high-confidence caution zone")
            score -= 8
        elif "Lower Band" in bb["signal"]:
            score += 3
        elif "Upper Band" in bb["signal"]:
            score -= 3

    # ── Volume ───────────────────────────────────────────────
    volume_ratio = 1.0
    if len(hist) >= 20:
        avg_vol_20   = hist["Volume"].tail(20).mean()
        today_vol    = hist["Volume"].iloc[-1]
        volume_ratio = round(float(today_vol / avg_vol_20), 2) if avg_vol_20 > 0 else 1.0
        if today_vol > avg_vol_20 * 3:
            signals.append("⚡ Extreme volume spike (3x+ normal) — big move in progress")
            score += 5
        elif today_vol > avg_vol_20 * 2:
            signals.append("⚡ High volume (2x+ normal) — institutional activity")

    # ── Confidence tier ──────────────────────────────────────
    bullish_count = sum(1 for s in signals if any(w in s for w in ["🟢", "🌙", "🚀"]))
    bearish_count = sum(1 for s in signals if any(w in s for w in ["🔴", "☠️", "⚠️"]))
    if bullish_count >= 2 and bearish_count == 0:
        confidence = "⭐ High confidence — multiple bullish signals agree"
    elif bearish_count >= 2 and bullish_count == 0:
        confidence = "⭐ High confidence — multiple bearish signals agree"
    elif bullish_count > 0 and bearish_count > 0:
        confidence = "⚠️ Mixed signals — indicators disagree, higher risk"
    else:
        confidence = "ℹ️ Low signal strength — not enough data to be confident"

    return {
        "rsi":            rsi,
        "rsi_label":      rsi_label,
        "macd":           macd,
        "macd_label":     macd_label,
        "ma50":           mas["ma50"],
        "ma200":          mas["ma200"],
        "ma_label":       ma_label,
        "week52_high":    round(float(week52_high), 2),
        "week52_low":     round(float(week52_low), 2),
        "high_label":     high_label,
        "low_label":      low_label,
        "atr":            atr,
        "support":        levels["support"],
        "resistance":     levels["resistance"],
        "pct_to_resist":  levels["pct_to_resist"],
        "pct_to_support": levels["pct_to_support"],
        "bollinger":      bb,
        "volume_ratio":   volume_ratio,
        "signals":        signals,
        "confidence":     confidence,
        "score":          max(0, min(100, score)),
    }

