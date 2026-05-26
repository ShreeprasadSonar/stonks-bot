"""Fetch stock data from yfinance — free, no API key needed."""
import time
import logging
import yfinance as yf

logger = logging.getLogger(__name__)


def get_stock_info(ticker: str, retries: int = 3) -> dict:
    """Return a rich dict of stock fundamentals + price data with retry logic."""
    for attempt in range(retries):
        try:
            logger.info(f"[{ticker}] Fetching data (attempt {attempt+1}/{retries})...")
            stock = yf.Ticker(ticker)

            # Use download() — more reliable from cloud IPs than history()
            hist = yf.download(ticker, period="1y", auto_adjust=True,
                               progress=False, timeout=15)

            if hist.empty:
                logger.warning(f"[{ticker}] No price history returned — may be delisted or wrong symbol")
                return {"error": f"No data found for {ticker}. Check the ticker symbol is correct."}

            # Flatten multi-level columns if present
            if hasattr(hist.columns, "levels"):
                hist.columns = hist.columns.get_level_values(0)

            current_price = float(hist["Close"].iloc[-1])
            prev_close    = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current_price
            change_pct    = round((current_price - prev_close) / prev_close * 100, 2)
            week52_high   = float(hist["High"].max())
            week52_low    = float(hist["Low"].min())
            avg_volume    = float(hist["Volume"].mean())
            today_volume  = float(hist["Volume"].iloc[-1])

            # Fundamentals via fast_info (fewer requests, less rate limiting)
            fi         = stock.fast_info
            market_cap = getattr(fi, "market_cap", 0) or 0
            name       = getattr(fi, "symbol", ticker)
            sector     = "Unknown"
            pe_ratio   = None
            eps        = None
            rev_growth = None

            # Try full info for richer data
            try:
                info       = stock.info
                name       = info.get("longName", ticker)
                sector     = info.get("sector", "Unknown")
                pe_ratio   = info.get("trailingPE")
                eps        = info.get("trailingEps")
                rev_growth = info.get("revenueGrowth")
                if not market_cap:
                    market_cap = info.get("marketCap", 0) or 0
                logger.info(f"[{ticker}] ✅ Full info fetched — {name}, ${current_price:.2f} ({change_pct:+.2f}%)")
            except Exception as e:
                logger.warning(f"[{ticker}] ⚠️ Full info unavailable ({e}) — using price data only")

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
                "revenue_growth":rev_growth,
                "avg_volume":    int(avg_volume),
                "today_volume":  int(today_volume),
                "volume_ratio":  round(today_volume / avg_volume, 2) if avg_volume else 0,
                "sector":        sector,
                "history":       hist,
            }

        except Exception as e:
            wait = 2 ** attempt  # exponential backoff: 1s, 2s, 4s
            logger.error(f"[{ticker}] ❌ Attempt {attempt+1} failed: {e} — retrying in {wait}s")
            time.sleep(wait)

    logger.error(f"[{ticker}] ❌ All {retries} attempts failed — skipping")
    return {"error": f"Could not fetch data for {ticker} after {retries} attempts. Yahoo Finance may be rate-limiting."}


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
        time.sleep(1.0)  # Rate limit buffer
    logger.info(f"Successfully fetched {len(results)}/{len(tickers)} tickers")
    return sorted(results, key=lambda x: x["change_pct"], reverse=True)


def format_market_cap(cap: int) -> str:
    if cap >= 1_000_000_000_000:
        return f"${cap/1_000_000_000_000:.2f}T"
    if cap >= 1_000_000_000:
        return f"${cap/1_000_000_000:.2f}B"
    if cap >= 1_000_000:
        return f"${cap/1_000_000:.2f}M"
    return f"${cap:,}" if cap else "N/A"



def get_stock_info(ticker: str) -> dict:
    """Return a rich dict of stock fundamentals + price data."""
    try:
        stock = yf.Ticker(ticker)
        hist  = stock.history(period="1y")

        if hist.empty:
            return {"error": f"No data found for {ticker}"}

        current_price = hist["Close"].iloc[-1]
        week52_high   = hist["High"].max()
        week52_low    = hist["Low"].min()
        avg_volume    = hist["Volume"].mean()
        today_volume  = hist["Volume"].iloc[-1]

        # Use fast_info first (fewer API calls, less rate limiting)
        fi = stock.fast_info
        market_cap  = getattr(fi, "market_cap", 0) or 0
        pe_ratio    = None
        eps         = None
        rev_growth  = None
        sector      = "Unknown"
        name        = ticker

        # Try full info only if fast_info doesn't have what we need
        try:
            info       = stock.info
            name       = info.get("longName", ticker)
            sector     = info.get("sector", "Unknown")
            pe_ratio   = info.get("trailingPE")
            eps        = info.get("trailingEps")
            rev_growth = info.get("revenueGrowth")
            if not market_cap:
                market_cap = info.get("marketCap", 0) or 0
        except Exception:
            pass  # Fall back to fast_info values — still shows price/technical data

        return {
            "ticker":        ticker.upper(),
            "name":          name,
            "price":         round(current_price, 2),
            "change_pct":    round(getattr(fi, "regular_market_previous_close", current_price) and
                                   (current_price - fi.regular_market_previous_close) /
                                   fi.regular_market_previous_close * 100
                                   if hasattr(fi, "regular_market_previous_close") and fi.regular_market_previous_close
                                   else 0, 2),
            "week52_high":   round(week52_high, 2),
            "week52_low":    round(week52_low, 2),
            "market_cap":    int(market_cap),
            "pe_ratio":      pe_ratio,
            "eps":           eps,
            "revenue_growth":rev_growth,
            "avg_volume":    int(avg_volume),
            "today_volume":  int(today_volume),
            "volume_ratio":  round(today_volume / avg_volume, 2) if avg_volume else 0,
            "sector":        sector,
            "history":       hist,
        }
    except Exception as e:
        return {"error": f"Failed to fetch {ticker}: {str(e)}"}


def get_top_movers(tickers: list) -> list:
    """Return tickers sorted by today's % change with rate-limit-safe delays."""
    results = []
    for t in tickers:
        data = get_stock_info(t)
        if "error" not in data:
            results.append(data)
        time.sleep(0.8)  # Avoid Yahoo Finance 429 rate limit
    return sorted(results, key=lambda x: x["change_pct"], reverse=True)


def format_market_cap(cap: int) -> str:
    if cap >= 1_000_000_000_000:
        return f"${cap/1_000_000_000_000:.2f}T"
    if cap >= 1_000_000_000:
        return f"${cap/1_000_000_000:.2f}B"
    if cap >= 1_000_000:
        return f"${cap/1_000_000:.2f}M"
    return f"${cap:,}"
