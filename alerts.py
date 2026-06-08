"""Price alerts — /alert NVDA above 150 — checked every 5 min by background monitor."""
import sqlite3, logging, os
logger = logging.getLogger(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "watchlist.db")

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS price_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        chat_id INTEGER NOT NULL,
        ticker TEXT NOT NULL,
        target REAL NOT NULL,
        direction TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        triggered INTEGER DEFAULT 0
    )""")
    c.commit()
    return c

def add_alert(user_id, chat_id, ticker, target, direction):
    with _conn() as c:
        cur = c.execute("INSERT INTO price_alerts (user_id,chat_id,ticker,target,direction) VALUES (?,?,?,?,?)",
                        (user_id, chat_id, ticker.upper(), target, direction))
        c.commit(); return cur.lastrowid

def get_user_alerts(user_id):
    with _conn() as c:
        rows = c.execute("SELECT id,ticker,target,direction FROM price_alerts WHERE user_id=? AND triggered=0 ORDER BY created_at",(user_id,)).fetchall()
    return [{"id":r[0],"ticker":r[1],"target":r[2],"direction":r[3]} for r in rows]

def delete_alert(alert_id, user_id):
    with _conn() as c:
        c.execute("DELETE FROM price_alerts WHERE id=? AND user_id=?",(alert_id,user_id)); c.commit()

def get_all_pending():
    with _conn() as c:
        rows = c.execute("SELECT id,user_id,chat_id,ticker,target,direction FROM price_alerts WHERE triggered=0").fetchall()
    return [{"id":r[0],"user_id":r[1],"chat_id":r[2],"ticker":r[3],"target":r[4],"direction":r[5]} for r in rows]

def mark_triggered(alert_id):
    with _conn() as c:
        c.execute("UPDATE price_alerts SET triggered=1 WHERE id=?",(alert_id,)); c.commit()
