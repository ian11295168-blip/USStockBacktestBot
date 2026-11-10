
import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("TELEGRAM_DATA_DIR") or ROOT).resolve()
DB_PATH = DATA_DIR / "strategies.db"


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def now():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS strategy_state (
                user_id INTEGER PRIMARY KEY,
                last_strategy TEXT,
                pending_strategy TEXT,
                incomplete_strategy TEXT,
                strategy_history TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                strategy_json TEXT NOT NULL,
                stats_json TEXT NOT NULL,
                trades_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)


def save_state(user_id, state):
    init_db()

    pending = state.get("pending")

    with connect() as conn:
        conn.execute("""
            INSERT INTO strategy_state (
                user_id,
                last_strategy,
                pending_strategy,
                incomplete_strategy,
                strategy_history,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                last_strategy = excluded.last_strategy,
                pending_strategy = excluded.pending_strategy,
                incomplete_strategy = excluded.incomplete_strategy,
                strategy_history = excluded.strategy_history,
                updated_at = excluded.updated_at
        """, (
            int(user_id),
            json.dumps(
                state.get("last_strategy"),
                ensure_ascii=False
            ),
            json.dumps(
                pending,
                ensure_ascii=False
            ),
            json.dumps(
                state.get("incomplete_strategy"),
                ensure_ascii=False
            ),
            json.dumps(
                state.get("strategy_history", []),
                ensure_ascii=False
            ),
            now()
        ))


def load_state(user_id):
    init_db()

    with connect() as conn:
        row = conn.execute("""
            SELECT
                last_strategy,
                pending_strategy,
                incomplete_strategy,
                strategy_history
            FROM strategy_state
            WHERE user_id = ?
        """, (int(user_id),)).fetchone()

    if row is None:
        return {
            "last_strategy": None,
            "pending": None,
            "incomplete_strategy": None,
            "strategy_history": []
        }

    return {
        "last_strategy": json.loads(row[0]),
        "pending": json.loads(row[1]),
        "incomplete_strategy": json.loads(row[2]),
        "strategy_history": json.loads(row[3])
    }


def save_backtest(user_id, strategy, stats, trades):
    init_db()

    def encode(value):
        if hasattr(value, "isoformat"):
            return value.isoformat()
        raise TypeError(
            f"無法序列化的資料類型：{type(value)}"
        )

    with connect() as conn:
        cursor = conn.execute("""
            INSERT INTO backtest_results (
                user_id,
                symbol,
                strategy_json,
                stats_json,
                trades_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            int(user_id),
            strategy["symbol"],
            json.dumps(
                strategy,
                ensure_ascii=False,
                default=encode
            ),
            json.dumps(
                stats,
                ensure_ascii=False,
                default=encode
            ),
            json.dumps(
                trades,
                ensure_ascii=False,
                default=encode
            ),
            now()
        ))

        return cursor.lastrowid


def get_latest_backtest(user_id):
    init_db()

    with connect() as conn:
        row = conn.execute("""
            SELECT
                id,
                symbol,
                strategy_json,
                stats_json,
                trades_json,
                created_at
            FROM backtest_results
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
        """, (int(user_id),)).fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "symbol": row[1],
        "strategy": json.loads(row[2]),
        "stats": json.loads(row[3]),
        "trades": json.loads(row[4]),
        "created_at": row[5]
    }


if __name__ == "__main__":
    init_db()
    print("SQLite 資料庫初始化成功")
    print("資料庫位置：", DB_PATH)
