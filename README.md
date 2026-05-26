# 📊 StockBot — Personal Stock Analyst Telegram Bot

A free Telegram bot that acts as your personal financial analyst.
Combines technical analysis, fundamental data, news sentiment, and political signals.

## 🚀 Quick Start

### 1. Get Your Telegram Bot Token
1. Open Telegram → search for **@BotFather**
2. Send `/newbot` → follow prompts → copy your token

### 2. Get Your Telegram Chat ID
1. Search for **@userinfobot** in Telegram → send any message → copy your chat ID

### 3. Get Free API Keys
- **Finnhub** (optional for Phase 1): https://finnhub.io → Sign up free → copy API key
- Reddit (optional for Phase 5): https://www.reddit.com/prefs/apps

### 4. Set Up GitHub Repository
1. Create a new GitHub repo
2. Upload all these files
3. Go to **Settings → Secrets and variables → Actions**
4. Add these secrets:
   - `TELEGRAM_BOT_TOKEN` = your bot token
   - `TELEGRAM_CHAT_ID`   = your chat ID
   - `FINNHUB_API_KEY`    = your Finnhub key (optional)

### 5. Enable GitHub Actions
Go to **Actions** tab in your repo → click **Enable Actions**

The bot will start automatically on every push.

## 📋 Bot Commands

| Command | Description |
|---|---|
| `/analyze NVDA` | Full analyst report with score |
| `/sector AI` | Top movers in AI sector |
| `/trending` | Today's top 5 momentum stocks |
| `/political NVDA` | Political & government signals |
| `/watch NVDA` | Add to watchlist |
| `/watchlist` | View your watchlist |
| `/explain rsi` | Learn what RSI means |

## 🏗️ Phases
- **Phase 1** ✅ Core bot + /analyze
- **Phase 2** 🔜 Technical analysis (RSI, MACD, MA)
- **Phase 3** 🔜 FinBERT AI news sentiment
- **Phase 4** 🔜 Congressional trades & political signals
- **Phase 5** 🔜 Reddit sentiment (WSB/r/investing)
- **Phase 6** 🔜 Full alert scheduler
- **Phase 7** 🔜 SQLite watchlist persistence

## ⚠️ Disclaimer
This bot is for educational purposes only. Not financial advice.
Always do your own research before investing.
