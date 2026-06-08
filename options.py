"""Options flow — put/call ratio and unusual activity from yfinance (free)."""
import logging
import yfinance as yf
logger = logging.getLogger(__name__)

def get_options_flow(ticker: str) -> dict:
    """Compute put/call ratio from yfinance options chain across next 3 expirations."""
    try:
        stock = yf.Ticker(ticker)
        exps  = stock.options
        if not exps:
            return {"available": False, "reason": "No options data for this ticker"}

        total_call_oi = total_put_oi = 0
        total_call_vol = total_put_vol = 0
        notable = []

        for exp in exps[:3]:
            try:
                chain = stock.option_chain(exp)
                calls, puts = chain.calls, chain.puts
                total_call_oi  += calls.get("openInterest", 0).sum() if "openInterest" in calls.columns else 0
                total_put_oi   += puts.get("openInterest",  0).sum() if "openInterest" in puts.columns  else 0
                total_call_vol += calls.get("volume", 0).sum() if "volume" in calls.columns else 0
                total_put_vol  += puts.get("volume",  0).sum() if "volume" in puts.columns  else 0
                # Unusual: volume > 3x open interest AND volume > 500 — fresh money entering
                for df, kind in [(calls, "CALL"), (puts, "PUT")]:
                    for _, row in df.iterrows():
                        oi  = row.get("openInterest") or 0
                        vol = row.get("volume") or 0
                        if oi > 100 and vol > oi * 3 and vol > 500:
                            notable.append({"type": kind, "strike": row.get("strike",0),
                                            "exp": exp, "vol": int(vol), "oi": int(oi),
                                            "ratio": round(vol/oi, 1)})
            except Exception:
                continue

        pc_vol = round(total_put_vol / total_call_vol, 2) if total_call_vol > 0 else None
        pc_oi  = round(total_put_oi  / total_call_oi,  2) if total_call_oi  > 0 else None

        if pc_vol is None:
            signal = "🟡 Insufficient volume data"
        elif pc_vol > 1.5:
            signal = "🔴 Bearish — heavy put buying (smart money hedging or betting down)"
        elif pc_vol > 1.0:
            signal = "🟡 Mildly bearish — more puts than calls"
        elif pc_vol < 0.5:
            signal = "🟢 Bullish — heavy call buying (market expects move up)"
        elif pc_vol < 0.8:
            signal = "🟢 Mildly bullish — more calls than puts"
        else:
            signal = "🟡 Neutral — balanced options activity"

        notable.sort(key=lambda x: x["vol"], reverse=True)
        return {"available": True, "ticker": ticker, "put_call_vol": pc_vol, "put_call_oi": pc_oi,
                "signal": signal, "total_call_vol": int(total_call_vol), "total_put_vol": int(total_put_vol),
                "notable": notable[:5]}
    except Exception as e:
        logger.warning(f"[{ticker}] Options flow failed: {e}")
        return {"available": False, "reason": str(e)}

def format_options_report(ticker: str, data: dict) -> str:
    import html as _h
    t = _h.escape(ticker)
    if not data.get("available"):
        return f"<b>📊 OPTIONS FLOW — {t}</b>\n  <i>{_h.escape(data.get('reason','Unavailable'))}</i>"
    pc_vol = data.get("put_call_vol")
    pc_oi  = data.get("put_call_oi")
    lines = [f"<b>📊 OPTIONS FLOW — {t}</b>",
             "<i>What sophisticated traders are betting — real money, real conviction</i>",
             "─────────────────────", "",
             f"  Put/Call Ratio (Volume): <b>{pc_vol}</b>  <i>(below 0.7 = bullish, above 1.3 = bearish)</i>",
             f"  Put/Call Ratio (OI):     <b>{pc_oi}</b>",
             f"  Call Volume: {data['total_call_vol']:,}   Put Volume: {data['total_put_vol']:,}",
             "", f"  {data['signal']}"]
    if data.get("notable"):
        lines += ["", "<b>⚡ Unusual Activity</b>  <i>(volume >> open interest = new position opened today)</i>"]
        for n in data["notable"][:4]:
            emoji = "🟢" if n["type"] == "CALL" else "🔴"
            lines.append(f"  {emoji} <b>{n['type']}</b> ${n['strike']} exp {n['exp']}  "
                        f"Vol {n['vol']:,}  OI {n['oi']:,}  ({n['ratio']}x)")
    lines += ["", "<i>High call volume = bullish speculation. High put volume = bearish hedge or bet.</i>",
              "<i>Unusual volume = large new position — track direction closely.</i>"]
    return "\n".join(lines)
