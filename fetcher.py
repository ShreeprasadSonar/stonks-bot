"""Fetch stock data from yfinance — free, no API key needed."""
import yfinance as yf
import pandas as pd


def get_stock_info(ticker: str) -> dict:
    """Return a rich dict of stock fundamentals + price data."""
    stock = yf.Ticker(ticker)
    info  = stock.info
    hist  = stock.history(period="1y")

    if hist.empty:
        return {"error": f"No data found for {ticker}"}

    current_price = hist["Close"].iloc[-1]
    week52_high   = hist["High"].max()
    week52_low    = hist["Low"].min()
    avg_volume    = hist["Volume"].mean()
    today_volume  = hist["Volume"].iloc[-1]

    return {
        "ticker":        ticker.upper(),
        "name":          info.get("longName", ticker),
        "price":         round(current_price, 2),
        "change_pct":    round(info.get("regularMarketChangePercent", 0), 2),
        "week52_high":   round(week52_high, 2),
        "week52_low":    round(week52_low, 2),
        "market_cap":    info.get("marketCap", 0),
        "pe_ratio":      info.get("trailingPE", None),
        "eps":           info.get("trailingEps", None),
        "revenue_growth":info.get("revenueGrowth", None),
        "avg_volume":    int(avg_volume),
        "today_volume":  int(today_volume),
        "volume_ratio":  round(today_volume / avg_volume, 2) if avg_volume else 0,
        "sector":        info.get("sector", "Unknown"),
        "history":       hist,
    }


def get_top_movers(tickers: list) -> list:
    """Return tickers sorted by today's % change."""
    results = []
    for t in tickers:
        data = get_stock_info(t)
        if "error" not in data:
            results.append(data)
    return sorted(results, key=lambda x: x["change_pct"], reverse=True)


def format_market_cap(cap: int) -> str:
    if cap >= 1_000_000_000_000:
        return f"${cap/1_000_000_000_000:.2f}T"
    if cap >= 1_000_000_000:
        return f"${cap/1_000_000_000:.2f}B"
    if cap >= 1_000_000:
        return f"${cap/1_000_000:.2f}M"
    return f"${cap:,}"
