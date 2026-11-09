
"""US Stock Strategy Lab v1.8 — Supabase 唯讀資料模組。

只供伺服器端使用，禁止在瀏覽器公開資料庫憑證。
目前讀取的是雲端快照，尚非即時雙向同步。
"""

import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

REQUIRED = (
    "SUPABASE_DB_HOST",
    "SUPABASE_DB_PORT",
    "SUPABASE_DB_NAME",
    "SUPABASE_DB_USER",
    "SUPABASE_DB_PASSWORD",
)


@contextmanager
def cloud_connection():
    """建立唯讀連線，結束時關閉。"""

    missing = [
        key for key in REQUIRED
        if not os.getenv(key)
    ]

    if missing:
        raise RuntimeError(
            "缺少 Supabase 連線設定："
            + ", ".join(missing)
        )

    with psycopg.connect(
        host=os.environ["SUPABASE_DB_HOST"],
        port=int(os.environ["SUPABASE_DB_PORT"]),
        dbname=os.environ["SUPABASE_DB_NAME"],
        user=os.environ["SUPABASE_DB_USER"],
        password=os.environ["SUPABASE_DB_PASSWORD"],
        sslmode="require",
        connect_timeout=15,
        autocommit=False,
    ) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SET TRANSACTION READ ONLY"
                )
                cursor.execute(
                    "SET LOCAL statement_timeout = '15000ms'"
                )

            yield conn
        finally:
            conn.rollback()


def get_cloud_counts():
    """只回傳三張表的資料筆數。"""

    with cloud_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    (SELECT COUNT(*)
                     FROM strategy_lab.telegram_strategy_state),
                    (SELECT COUNT(*)
                     FROM strategy_lab.telegram_backtest_results),
                    (SELECT COUNT(*)
                     FROM strategy_lab.web_state)
                """
            )

            a, b, c = cursor.fetchone()

    return {
        "telegram_strategy_state": a,
        "telegram_backtest_results": b,
        "web_state": c,
    }


def get_cloud_telegram_states():
    """取得 Telegram 各使用者已保存的策略狀態。"""

    with cloud_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    user_id,
                    last_strategy,
                    pending_strategy,
                    incomplete_strategy,
                    strategy_history,
                    updated_at
                FROM strategy_lab.telegram_strategy_state
                ORDER BY user_id
                """
            )

            rows = cursor.fetchall()

    columns = (
        "user_id",
        "last_strategy",
        "pending_strategy",
        "incomplete_strategy",
        "strategy_history",
        "updated_at",
    )

    return [
        dict(zip(columns, row))
        for row in rows
    ]


def get_cloud_telegram_backtests(
    user_id,
    limit=20,
):
    """取得指定 Telegram 使用者的最近回測。"""

    if user_id is None:
        raise ValueError("必須提供 user_id")

    limit = int(limit)

    if not 1 <= limit <= 100:
        raise ValueError(
            "limit 必須介於 1 到 100"
        )

    with cloud_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    user_id,
                    symbol,
                    strategy_json,
                    stats_json,
                    trades_json,
                    created_at
                FROM strategy_lab.telegram_backtest_results
                WHERE user_id = %s
                ORDER BY id DESC
                LIMIT %s
                """,
                (str(user_id), limit),
            )

            rows = cursor.fetchall()

    columns = (
        "id",
        "user_id",
        "symbol",
        "strategy_json",
        "stats_json",
        "trades_json",
        "created_at",
    )

    return [
        dict(zip(columns, row))
        for row in rows
    ]


def get_cloud_web_state():
    """取得目前雲端保存的網頁狀態。"""

    with cloud_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    payload,
                    updated_at
                FROM strategy_lab.web_state
                WHERE id = 1
                """
            )

            row = cursor.fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "payload": row[1],
        "updated_at": row[2],
    }
