
"""US Stock Strategy Lab v2.3
Telegram SQLite 與 Supabase 唯讀差異檢查。

用途：
    python check_telegram_cloud_sync.py

只比較：
- Telegram 策略狀態
- Telegram 歷史回測

安全：
- 不修改 SQLite
- 不修改 Supabase
- 不輸出 user_id、策略內容或交易紀錄
- 不處理網頁 web_state
"""

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import psycopg
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
LOCAL_DB = ROOT / "strategies.db"

load_dotenv(ROOT / ".env")

REQUIRED_ENV = (
    "SUPABASE_DB_HOST",
    "SUPABASE_DB_PORT",
    "SUPABASE_DB_NAME",
    "SUPABASE_DB_USER",
    "SUPABASE_DB_PASSWORD",
)

JSON_FIELDS = {
    "strategy_state": (
        "last_strategy",
        "pending_strategy",
        "incomplete_strategy",
        "strategy_history",
    ),
    "backtest_results": (
        "strategy_json",
        "stats_json",
        "trades_json",
    ),
}


def normalize_json(value):
    """讓 SQLite JSON 文字與 PostgreSQL JSONB 可比較。"""

    if value is None:
        return None

    if isinstance(value, bytes):
        value = value.decode("utf-8")

    if isinstance(value, str):
        value = json.loads(value)

    return value


def read_sqlite():
    if not LOCAL_DB.is_file():
        raise RuntimeError(
            "找不到 strategies.db"
        )

    uri = LOCAL_DB.resolve().as_uri() + "?mode=ro"

    with closing(
        sqlite3.connect(
            uri,
            uri=True,
            timeout=15,
        )
    ) as conn:
        conn.row_factory = sqlite3.Row

        states = [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    user_id,
                    last_strategy,
                    pending_strategy,
                    incomplete_strategy,
                    strategy_history,
                    updated_at
                FROM strategy_state
                """
            )
        ]

        backtests = [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    id,
                    user_id,
                    symbol,
                    strategy_json,
                    stats_json,
                    trades_json,
                    created_at
                FROM backtest_results
                """
            )
        ]

    for row in states:
        row["user_id"] = str(row["user_id"])

        for field in JSON_FIELDS["strategy_state"]:
            row[field] = normalize_json(row[field])

    for row in backtests:
        row["user_id"] = str(row["user_id"])

        for field in JSON_FIELDS["backtest_results"]:
            row[field] = normalize_json(row[field])

    return states, backtests


def read_supabase():
    missing = [
        name for name in REQUIRED_ENV
        if not os.getenv(name)
    ]

    if missing:
        raise RuntimeError(
            "Supabase 連線設定不完整"
        )

    with closing(
        psycopg.connect(
            host=os.environ["SUPABASE_DB_HOST"],
            port=int(os.environ["SUPABASE_DB_PORT"]),
            dbname=os.environ["SUPABASE_DB_NAME"],
            user=os.environ["SUPABASE_DB_USER"],
            password=os.environ["SUPABASE_DB_PASSWORD"],
            sslmode="require",
            connect_timeout=15,
            autocommit=False,
        )
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(
                "SET LOCAL statement_timeout = '20000ms'"
            )

            cur.execute(
                """
                SELECT
                    user_id,
                    last_strategy,
                    pending_strategy,
                    incomplete_strategy,
                    strategy_history,
                    updated_at
                FROM strategy_lab.telegram_strategy_state
                """
            )

            state_columns = [
                item.name for item in cur.description
            ]

            states = [
                dict(zip(state_columns, values))
                for values in cur.fetchall()
            ]

            cur.execute(
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
                """
            )

            backtest_columns = [
                item.name for item in cur.description
            ]

            backtests = [
                dict(zip(backtest_columns, values))
                for values in cur.fetchall()
            ]

        conn.rollback()

    return states, backtests


def compare_rows(local, cloud, key):
    """比較筆數、缺少資料及相同主鍵的內容。"""

    local_index = {
        str(row[key]): row
        for row in local
    }

    cloud_index = {
        str(row[key]): row
        for row in cloud
    }

    local_keys = set(local_index)
    cloud_keys = set(cloud_index)

    only_local = local_keys - cloud_keys
    only_cloud = cloud_keys - local_keys
    common = local_keys & cloud_keys

    changed = 0

    for record_key in common:
        local_row = local_index[record_key]
        cloud_row = cloud_index[record_key]

        if local_row != cloud_row:
            changed += 1

    return {
        "local_count": len(local),
        "cloud_count": len(cloud),
        "only_local": len(only_local),
        "only_cloud": len(only_cloud),
        "changed": changed,
        "same": len(common) - changed,
    }


def print_report(title, report):
    print()
    print(title)
    print("-" * 42)

    print(
        "本機 SQLite：",
        report["local_count"],
        "筆",
    )

    print(
        "Supabase：",
        report["cloud_count"],
        "筆",
    )

    print(
        "✅ 內容相同：",
        report["same"],
        "筆",
    )

    print(
        "📥 只在本機：",
        report["only_local"],
        "筆",
    )

    print(
        "☁️ 只在雲端：",
        report["only_cloud"],
        "筆",
    )

    print(
        "⚠️ 相同主鍵但內容不同：",
        report["changed"],
        "筆",
    )


def main():
    print("US Stock Strategy Lab v2.3")
    print("Telegram / Supabase 差異檢查")
    print("=" * 42)

    try:
        local_states, local_backtests = read_sqlite()
        print("✅ Telegram SQLite 讀取成功")

        cloud_states, cloud_backtests = read_supabase()
        print("✅ Supabase PostgreSQL 讀取成功")

        strategy_report = compare_rows(
            local_states,
            cloud_states,
            key="user_id",
        )

        backtest_report = compare_rows(
            local_backtests,
            cloud_backtests,
            key="id",
        )

        print_report(
            "📋 Telegram 策略狀態",
            strategy_report,
        )

        print_report(
            "📊 Telegram 歷史回測",
            backtest_report,
        )

        print()
        print("=" * 42)

        reports = (strategy_report, backtest_report)

        if all(
            item["only_local"] == 0
            and item["only_cloud"] == 0
            and item["changed"] == 0
            for item in reports
        ):
            print("✅ Telegram 與 Supabase 資料完全一致")

        else:
            print("⚠️ 發現尚未同步或版本不同的資料")
            print("目前沒有修改任何資料庫")

        print()
        print("✅ 唯讀檢查完成")

    except Exception as exc:
        print()
        print("❌ 差異檢查失敗")
        print("錯誤類型：", type(exc).__name__)

        # 不輸出可能包含密碼的連線錯誤內容


if __name__ == "__main__":
    main()
