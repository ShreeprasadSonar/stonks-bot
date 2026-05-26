"""Fetch stock data from yfinance — free, no API key needed."""
import time
import logging
from datetime import datetime, timezone
import yfinance as yf

logger = logging.getLogger(__name__)


def get_stock_info(ticker: str, retries: int = 3) -> dict:
    """Return a rich dict of stock data with retry + exponential backoff."""
    for attempt in range(retries):
        try:
            logger.info(f"[{ticker}] Fetching data (attempt {attempt+1}/{retries})...")
            stock = yf.Ticker(ticker)

            hist = yf.download(ticker, period="1y", auto_adjust=True,
                               progress=False, timeout=15)
            if hist.empty:
                logger.warning(f"[{ticker}] No price history — may be delisted or wrong symbol")
                return {"error": f"No data found for {ticker}. Check the ticker symbol is correct."}

            if hasattr(hist.columns, "levels"):
                hist.columns = hist.columns.get_level_values(0)

            current_price = float(hist["Close"].iloc[-1])
            prev_close    = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current_price
            change_pct    = round((current_price - prev_close) / prev_close * 100, 2)
            week52_high   = float(hist["High"].max())
            week52_low    = float(hist["Low"].min())
            avg_volume    = float(hist["Volume"].mean())
            today_volume  = float(hist["Volume"].iloc[-1])

            fi         = stock.fast_info
            market_cap = getattr(fi, "market_cap", 0) or 0
            name       = ticker
            sector     = "Unknown"
            pe_ratio   = None
            eps        = None
            rev_growth = None
            beta       = None
            short_interest = None  # % of float shorted — high = squeeze risk
            earnings_date  = None  # next expected earnings

            try:
                info       = stock.info
                name       = info.get("longName", ticker)
                sector     = info.get("sector", "Unknown")
                pe_ratio   = info.get("trailingPE")
                eps        = info.get("trailingEps")
                rev_growth = info.get("revenueGrowth")
                beta       = info.get("beta")
                short_pct  = info.get("shortPercentOfFloat")
                if short_pct:
                    short_interest = round(short_pct * 100, 1)  # convert to % e.g. 5.2
                if not market_cap:
                    market_cap = info.get("marketCap", 0) or 0
                logger.info(f"[{ticker}] ✅ Fetched — {name}, ${current_price:.2f} ({change_pct:+.2f}%)")
            except Exception as e:
                logger.warning(f"[{ticker}] ⚠️ Full info unavailable ({e}) — using price data only")

            # Earnings date — try calendar first, then info
            try:
                cal = stock.calendar
                if isinstance(cal, dict):
                    ed = cal.get("Earnings Date")
                    if ed and len(ed) > 0:
                        earnings_date = ed[0]
                elif hasattr(cal, "iloc") and not cal.empty:
                    if "Earnings Date" in cal.columns:
                        earnings_date = cal["Earnings Date"].iloc[0]
            except Exception:
                pass  # earnings date is optional

            return {
                "ticker":        ticker.upper(),
                "name":          name,
                "price":         round(current_price, 2),
                "change_pct":    change_pct,
                "week52_high":   round(week52_high, 2),
                "week52_low":    round(week52_low, 2),
                "market_cap":    int(market_cap),
                "pe_ratio":      pe_ratio,
                "eps":           eps,
                "revenue_growth": rev_growth,
                "beta":          round(beta, 2) if beta else None,
                "short_interest": short_interest,
                "earnings_date": earnings_date,
                "avg_volume":    int(avg_volume),
                "today_volume":  int(today_volume),
                "volume_ratio":  round(today_volume / avg_volume, 2) if avg_volume else 0,
                "sector":        sector,
                "history":       hist,
            }

        except Exception as e:
            wait = 2 ** attempt
            logger.error(f"[{ticker}] ❌ Attempt {attempt+1} failed: {e} — retrying in {wait}s")
            time.sleep(wait)

    logger.error(f"[{ticker}] ❌ All {retries} attempts failed")
    return {"error": f"Could not fetch data for {ticker}. Yahoo Finance may be rate-limiting."}


def get_top_movers(tickers: list) -> list:
    """Return tickers sorted by today's % change."""
    logger.info(f"Fetching movers for {len(tickers)} tickers: {tickers}")
    results = []
    for t in tickers:
        data = get_stock_info(t)
        if "error" not in data:
            results.append(data)
        else:
            logger.warning(f"[{t}] Skipped: {data['error']}")
        time.sleep(1.0)
    logger.info(f"Fetched {len(results)}/{len(tickers)} tickers")
    return sorted(results, key=lambda x: x["change_pct"], reverse=True)


def format_market_cap(cap: int) -> str:
    if cap >= 1_000_000_000_000:
        return f"${cap/1_000_000_000_000:.2f}T"
    if cap >= 1_000_000_000:
        return f"${cap/1_000_000_000:.2f}B"
    if cap >= 1_000_000:
        return f"${cap/1_000_000:.2f}M"
    return f"${cap:,}" if cap else "N/A"

