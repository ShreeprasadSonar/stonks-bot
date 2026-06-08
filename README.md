# 📊 StockBot — Personal Stock Analyst Telegram Bot

A production-grade Telegram bot that acts as your personal financial analyst.
Combines technical analysis, fundamental data, phrase-level news sentiment, political signals, SEC filings, options flow, and real-time price alerts — all from **free data sources, no paid API keys required**.

---

## 🚀 Quick Start

### 1. Get Your Telegram Bot Token
1. Open Telegram → search for **@BotFather**
2. Send `/newbot` → follow prompts → copy your token

### 2. Get Your Telegram Chat ID
1. Search for **@userinfobot** in Telegram → send any message → copy your chat ID

### 3. Set Up GitHub Repository
1. Create a new GitHub repo and upload all files
2. Go to **Settings → Secrets and variables → Actions**
3. Add these secrets:

| Secret | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Your chat ID from @userinfobot |

> No paid API keys needed. All data sources are free.

### 4. Enable GitHub Actions
Go to the **Actions** tab → click **Enable Actions**.

The bot starts automatically on every push and runs scheduled briefs via cron.

---

## 📋 Commands

| Command | Description |
|---|---|
| `/analyze NVDA` | Full analyst report — price, technicals, fundamentals, news, options flow, insider trades, score |
| `/market` | Live dashboard — top movers, sector snapshot, social sentiment, narrative tracker |
| `/market AI` | Deep-dive into a specific sector (AI, Semiconductors, Cloud, Software) |
| `/market themes` | Full narrative tracker — which investment themes are heating up right now |
| `/social NVDA` | Reddit buzz, Yahoo trending, Congress trades, analyst ratings |
| `/political NVDA` | Political news + congressional insider trades for a ticker |
| `/alert NVDA above 150` | Set a price alert — fires when price crosses your target |
| `/alert list` | View your active price alerts |
| `/alert delete 3` | Remove alert #3 |
| `/edgar NVDA` | SEC EDGAR filings — 8-K material events + Form 4 insider buy/sell |
| `/watchlist` | View and manage your saved stocks |
| `/watchlist NVDA` | Add NVDA to watchlist |
| `/brief morning` | Trigger the full morning market brief on demand |
| `/brief evening` | Trigger the closing report on demand |
| `/explain rsi` | Plain-English guide to any metric |
| `/help` | Full command reference |

---

## 🤖 Background Monitors

These run 24/7 automatically — no manual trigger needed:

| Monitor | Frequency | What it does |
|---|---|---|
| **Political News Monitor** | Every 20 min | Scans trending stocks for high-impact political news (President, Fed, SEC, Congress). Batches into one digest. Remembers seen articles across restarts. |
| **Price Alert Monitor** | Every 5 min | Checks all pending user alerts against live prices. Fires Telegram notification instantly when triggered. |

---

## 🌅 Scheduled Briefs (GitHub Actions Cron)

| Time | Brief |
|---|---|
| 8:00 AM CT Mon–Fri | Morning pre-market brief |
| 4:30 PM CT Mon–Fri | Closing market report |
| 9:00 AM CT Sunday | Weekly deep-dive |

---

## 📁 Project Structure

```
stock-bot/
├── main.py           — Bot entry point, background monitors, startup logic
├── commands.py       — All Telegram command handlers + rate limiting + message chunking
├── config.py         — Environment variables, sector definitions
├── fetcher.py        — Stock price/fundamentals via yfinance (free)
├── technical.py      — RSI, MACD, Bollinger Bands, support/resistance, ATR
├── fundamental.py    — P/E, EPS, revenue growth scoring
├── sentiment.py      — Phrase-level + negation-aware news sentiment scoring
├── news.py           — Google News RSS with full article summaries + links
├── formatter.py      — HTML report formatting for Telegram
├── social.py         — Reddit RSS, Google Trends, Congress trades, Finviz
├── reddit.py         — Yahoo Finance trending + dynamic ticker selection
├── themes.py         — Investment narrative tracker (AI, Defense, Biotech, etc.)
├── market_context.py — SPY/QQQ benchmarks, Fear & Greed, sector ETFs, macro calendar
├── alerts.py         — Price alert CRUD (SQLite)
├── edgar.py          — SEC EDGAR 8-K filings + Form 4 insider transactions (free)
├── options.py        — Put/call ratio + unusual options activity (yfinance)
├── scheduler.py      — Morning brief, closing report, weekly deep-dive
├── watchlist.py      — SQLite watchlist persistence
└── state/
    ├── seen_articles.json   — Persists seen political articles across restarts
    └── last_startup.txt     — Suppresses repeated startup messages on redeploy
```

---

## ⚙️ How It Works

### Data Sources (all free)
| Data | Source |
|---|---|
| Stock prices, fundamentals, options | Yahoo Finance via `yfinance` |
| News headlines + summaries | Google News RSS |
| Reddit sentiment | r/wallstreetbets, r/stocks, r/investing RSS |
| Trending stocks | Yahoo Finance Trending API |
| Congress trades | housestockwatcher.com + senatestockwatcher.com |
| SEC filings | SEC EDGAR Atom RSS (free, no key) |
| Fear & Greed | CNN Fear & Greed Index API |
| Market themes | Google News + Reddit RSS + Google Trends |

### Sentiment Engine
Uses **phrase-level scoring with negation detection** — not a simple word bag.
- `"beats estimates"` → Bullish +0.8 (not just the word "beats")
- `"not bullish"` → correctly scores bearish (negation window)
- `"all-time high crash risk"` → correctly bearish (phrase context)

### Dynamic Ticker Selection
Each analysis cycle fetches tickers from three sources, merged in priority order:
1. Yahoo Finance Trending (what retail is actively searching right now)
2. Top investment theme tickers (from narrative tracker)
3. Base sector anchors (fallback)

### Production Safeguards
- **Rate limiting** — per-user cooldowns (analyze=10s, market=20s, brief=60s)
- **Message chunking** — splits at 4000 chars on line boundaries (Telegram limit = 4096)
- **Non-blocking async** — all Yahoo Finance calls run in `run_in_executor` so the event loop never freezes
- **Restart-safe state** — seen articles and startup timestamps persist to disk
- **Startup suppression** — won't spam you on frequent GitHub Actions redeploys (6h cooldown)

---

## ⚠️ Disclaimer
This bot is for educational and informational purposes only. Not financial advice.
Always do your own research before making any investment decisions.
