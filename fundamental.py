"""Fundamental analysis with plain-English explanations."""


def score_fundamentals(info: dict) -> dict:
    score = 50
    notes = []

    pe = info.get("pe_ratio")
    if pe:
        if pe < 15:
            notes.append(f"📉 P/E {pe:.1f} — Cheap vs market (avg ~20). You pay ${pe:.0f} per $1 of profit.")
            score += 15
        elif pe < 25:
            notes.append(f"🟡 P/E {pe:.1f} — Fair value range.")
            score += 5
        elif pe < 40:
            notes.append(f"🟠 P/E {pe:.1f} — Pricey. Growth must justify cost.")
            score -= 5
        else:
            notes.append(f"🔴 P/E {pe:.1f} — Very expensive. High expectations priced in.")
            score -= 15

    rev_growth = info.get("revenue_growth")
    if rev_growth:
        pct = round(rev_growth * 100, 1)
        if pct > 20:
            notes.append(f"🚀 Revenue growing {pct}% YoY — strong growth company.")
            score += 15
        elif pct > 10:
            notes.append(f"🟢 Revenue growing {pct}% YoY — healthy growth.")
            score += 8
        elif pct > 0:
            notes.append(f"🟡 Revenue growing {pct}% YoY — slow but positive.")
            score += 2
        else:
            notes.append(f"🔴 Revenue shrinking {pct}% YoY — concerning.")
            score -= 15

    eps = info.get("eps")
    if eps:
        if eps > 5:
            notes.append(f"💰 EPS ${eps:.2f} — Very profitable.")
            score += 10
        elif eps > 0:
            notes.append(f"🟢 EPS ${eps:.2f} — Profitable.")
            score += 5
        else:
            notes.append(f"🔴 EPS ${eps:.2f} — Not yet profitable. Higher risk.")
            score -= 10

    return {
        "score": max(0, min(100, score)),
        "notes": notes,
    }
