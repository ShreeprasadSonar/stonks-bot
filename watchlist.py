"""
Persistent watchlist using SQLite (Python stdlib — no install needed).
Survives bot restarts. Stored in watchlist.db in the working directory.
"""
import sqlite3
import logging
import os

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "watchlist.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            user_id INTEGER NOT NULL,
            ticker  TEXT    NOT NULL,
            added_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, ticker)
        )
    """)
    conn.commit()
    return conn


def add_ticker(user_id: int, ticker: str) -> bool:
    """Add ticker to user's watchlist. Returns True if new, False if already existed."""
    ticker = ticker.upper().strip()
    try:
        with _get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO watchlist (user_id, ticker) VALUES (?, ?)",
                (user_id, ticker)
            )
            conn.commit()
        logger.info(f"Watchlist: added {ticker} for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Watchlist add error: {e}")
        return False


def remove_ticker(user_id: int, ticker: str) -> bool:
    """Remove ticker from user's watchlist."""
    ticker = ticker.upper().strip()
    try:
        with _get_conn() as conn:
            conn.execute(
                "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
                (user_id, ticker)
            )
            conn.commit()
        logger.info(f"Watchlist: removed {ticker} for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Watchlist remove error: {e}")
        return False


def get_watchlist(user_id: int) -> list[str]:
    """Return list of tickers in user's watchlist, ordered by date added."""
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY added_at",
                (user_id,)
            ).fetchall()
        return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"Watchlist fetch error: {e}")
        return []


def get_all_watched_tickers() -> list[str]:
    """Return all unique tickers across all users — used for watchlist alerts."""
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT ticker FROM watchlist ORDER BY ticker"
            ).fetchall()
        return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"Watchlist fetch all error: {e}")
        return []
