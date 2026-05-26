import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN")
FINNHUB_KEY        = os.getenv("FINNHUB_API_KEY")
REDDIT_CLIENT_ID   = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT  = os.getenv("REDDIT_USER_AGENT", "StockBot/1.0")

# Default watchlist sectors
SECTORS = {
    "AI":             ["NVDA", "AMD", "MSFT", "GOOGL", "META", "SMCI"],
    "Semiconductors": ["TSM", "ASML", "AMAT", "LRCX", "INTC"],
    "Cloud":          ["AMZN", "SNOW", "DDOG", "NET"],
    "Software":       ["CRM", "NOW", "ADBE", "ORCL"],
}

# Composite score weights
WEIGHTS = {
    "technical":    0.30,
    "fundamental":  0.25,
    "sentiment":    0.20,
    "momentum":     0.15,
    "political":    0.10,
}
