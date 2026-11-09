
"""US Stock Strategy Lab v1.6
SQLite -> Supabase PostgreSQL 安全遷移。

使用方式：
    python migrate_to_supabase.py
        預設唯讀檢查，不寫入雲端。

    python migrate_to_supabase.py --apply
        要求再次確認後，才正式遷移。

安全規則：
- 不修改本機 SQLite。
- 不刪除或覆蓋既有雲端資料。
- 目的地三張資料表必須全部為空。
- 三張資料表在同一個 PostgreSQL 交易中寫入。
- 驗證失敗會 ROLLBACK。
- 不輸出私人策略內容與連線密碼。
"""

import argparse
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb


ROOT = Path(__file__).resolve().parent

load_dotenv(ROOT / ".env")

REQUIRED_ENV = [
    "SUPABASE_DB_HOST",
    "SUPABASE_DB_PORT",
    "SUPABASE_DB_NAME",
    "SUPABASE_DB_USER",
    "SUPABASE_DB_PASSWORD",
]

TABLE_NAMES = [
    "telegram_strategy_state",
    "telegram_backtest_results",
    "web_state",
]


def read_json(value, field_name):
    """驗證 SQLite JSON，轉成 PostgreSQL JSONB 資料。"""

    if value is None:
        return None

    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")

    try:
        parsed = json.loads(value)

        # 避免把不符合標準的 NaN/Infinity 寫入 JSONB
        json.dumps(
            parsed,
            allow_nan=False,
        )

        return parsed

    except (TypeError, ValueError, UnicodeError):
        raise ValueError(
            f"欄位 {field_name} 包含無效 JSON"
        ) from None


def read_table(filename, table, columns):
    """開啟 SQLite 唯讀交易並取出指定欄位。"""

    path = ROOT / filename

    if not path.is_file():
        raise FileNotFoundError(
            f"找不到 {filename}"
        )

    uri = path.resolve().as_uri() + "?mode=ro"

    with closing(
        sqlite3.connect(
            uri,
            uri=True,
            timeout=15,
        )
    ) as conn:

        conn.row_factory = sqlite3.Row

        names = ", ".join(
            f'"{name}"' for name in columns
        )

        query = (
            f'SELECT {names} FROM "{table}"'
        )

        rows = conn.execute(query).fetchall()

        return [
            dict(row)
            for row in rows
        ]


def load_local_data():
    """一次整理三張資料表的遷移資料。"""

    strategy_rows = read_table(
        "strategies.db",
        "strategy_state",
        [
            "user_id",
            "last_strategy",
            "pending_strategy",
            "incomplete_strategy",
            "strategy_history",
            "updated_at",
        ],
    )

    backtest_rows = read_table(
        "strategies.db",
        "backtest_results",
        [
            "id",
            "user_id",
            "symbol",
            "strategy_json",
            "stats_json",
            "trades_json",
            "created_at",
        ],
    )

    web_rows = read_table(
        "web_backtest.db",
        "web_state",
        [
            "id",
            "payload",
            "updated_at",
        ],
    )

    for row in strategy_rows:
        row["user_id"] = str(
            row["user_id"]
        )

        for field in [
            "last_strategy",
            "pending_strategy",
            "incomplete_strategy",
            "strategy_history",
        ]:
            row[field] = read_json(
                row[field],
                field,
            )

    for row in backtest_rows:
        row["user_id"] = str(
            row["user_id"]
        )

        for field in [
            "strategy_json",
            "stats_json",
            "trades_json",
        ]:
            row[field] = read_json(
                row[field],
                field,
            )

    for row in web_rows:
        row["payload"] = read_json(
            row["payload"],
            "payload",
        )

    return {
        "telegram_strategy_state": strategy_rows,
        "telegram_backtest_results": backtest_rows,
        "web_state": web_rows,
    }


def connect_postgres():
    missing = [
        name for name in REQUIRED_ENV
        if not os.getenv(name)
    ]

    if missing:
        raise RuntimeError(
            "缺少 Supabase 環境變數："
            + ", ".join(missing)
        )

    return psycopg.connect(
        host=os.environ["SUPABASE_DB_HOST"],
        port=int(
            os.environ["SUPABASE_DB_PORT"]
        ),
        dbname=os.environ["SUPABASE_DB_NAME"],
        user=os.environ["SUPABASE_DB_USER"],
        password=os.environ["SUPABASE_DB_PASSWORD"],
        sslmode="require",
        connect_timeout=15,
        autocommit=False,
    )


def cloud_counts(cursor):
    """只讀取預先固定的三張資料表筆數。"""

    counts = {}

    for table in TABLE_NAMES:
        cursor.execute(
            f'SELECT COUNT(*) '
            f'FROM strategy_lab."{table}"'
        )

        counts[table] = cursor.fetchone()[0]

    return counts


def validate_empty_cloud(cursor):
    """避免重複遷移或覆蓋已存在的資料。"""

    counts = cloud_counts(cursor)

    for table, count in counts.items():
        if count != 0:
            raise RuntimeError(
                f"雲端資料表 {table} 已有 "
                f"{count} 筆，禁止自動遷移"
            )

    return counts


def insert_strategies(cursor, rows):
    sql = """
        INSERT INTO strategy_lab.telegram_strategy_state
        (
            user_id,
            last_strategy,
            pending_strategy,
            incomplete_strategy,
            strategy_history,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s)
    """

    for row in rows:
        cursor.execute(
            sql,
            (
                row["user_id"],
                Jsonb(row["last_strategy"]),
                Jsonb(row["pending_strategy"]),
                Jsonb(row["incomplete_strategy"]),
                Jsonb(row["strategy_history"]),
                row["updated_at"],
            ),
        )


def insert_backtests(cursor, rows):
    sql = """
        INSERT INTO strategy_lab.telegram_backtest_results
        (
            id,
            user_id,
            symbol,
            strategy_json,
            stats_json,
            trades_json,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    for row in rows:
        cursor.execute(
            sql,
            (
                row["id"],
                row["user_id"],
                row["symbol"],
                Jsonb(row["strategy_json"]),
                Jsonb(row["stats_json"]),
                Jsonb(row["trades_json"]),
                row["created_at"],
            ),
        )


def insert_web_state(cursor, rows):
    sql = """
        INSERT INTO strategy_lab.web_state
        (
            id,
            payload,
            updated_at
        )
        VALUES (%s, %s, %s)
    """

    for row in rows:
        cursor.execute(
            sql,
            (
                row["id"],
                Jsonb(row["payload"]),
                row["updated_at"],
            ),
        )


def verify_records(cursor, local_data):
    """驗證雲端筆數、主鍵與 JSON 欄位內容。"""

    json_columns = {
        "telegram_strategy_state": [
            "last_strategy",
            "pending_strategy",
            "incomplete_strategy",
            "strategy_history",
        ],
        "telegram_backtest_results": [
            "strategy_json",
            "stats_json",
            "trades_json",
        ],
        "web_state": ["payload"],
    }

    primary_keys = {
        "telegram_strategy_state": "user_id",
        "telegram_backtest_results": "id",
        "web_state": "id",
    }

    counts = cloud_counts(cursor)

    for table, rows in local_data.items():
        if counts[table] != len(rows):
            raise RuntimeError(
                f"{table} 筆數驗證失敗"
            )

        key = primary_keys[table]

        cursor.execute(
            f'SELECT * FROM strategy_lab."{table}"'
        )

        names = [
            column.name
            for column in cursor.description
        ]

        cloud_rows = [
            dict(zip(names, values))
            for values in cursor.fetchall()
        ]

        indexed = {
            str(row[key]): row
            for row in cloud_rows
        }

        if len(indexed) != len(rows):
            raise RuntimeError(
                f"{table} 主鍵數量不符"
            )

        for local in rows:
            cloud = indexed.get(
                str(local[key])
            )

            if cloud is None:
                raise RuntimeError(
                    f"{table} 找不到對應主鍵"
                )

            # 比對原始欄位，略過雲端新增的 migrated_at。
            for field, local_value in local.items():
                cloud_value = cloud[field]

                if field in json_columns[table]:
                    if cloud_value != local_value:
                        raise RuntimeError(
                            f"{table}.{field} "
                            "JSON 內容驗證失敗"
                        )

                elif str(cloud_value) != str(local_value):
                    raise RuntimeError(
                        f"{table}.{field} "
                        "欄位驗證失敗"
                    )

    return counts


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--apply",
        action="store_true",
        help="確認後正式寫入 Supabase",
    )

    args = parser.parse_args()

    mode = (
        "正式遷移"
        if args.apply
        else "唯讀模擬檢查"
    )

    print("US Stock Strategy Lab v1.6")
    print("SQLite → Supabase", mode)
    print("=" * 48)

    try:
        local_data = load_local_data()

    except Exception as exc:
        print("❌ SQLite 讀取或 JSON 檢查失敗")
        print("錯誤類型：", type(exc).__name__)
        return

    print()
    print("📁 本機資料")

    total = 0

    for table, rows in local_data.items():
        count = len(rows)
        total += count
        print(f"  {table}：{count} 筆")

    print(f"本機資料合計：{total} 筆")

    if total == 0:
        print("❌ 沒有可遷移的資料")
        return

    if args.apply:
        print()
        print("⚠️ 即將正式寫入雲端資料庫")
        print("⚠️ 本機資料庫不會修改")

        phrase = f"MIGRATE {total}"

        typed = input(
            f"輸入 {phrase} 確認遷移："
        ).strip()

        if typed != phrase:
            print("已取消，沒有寫入資料")
            return

    conn = None
    committed = False

    try:
        conn = connect_postgres()

        with conn.cursor() as cursor:
            cursor.execute(
                "SET LOCAL statement_timeout = '30000ms'"
            )

            validate_empty_cloud(cursor)

            print()
            print("✅ Supabase 三張目的地資料表皆為空")

            if not args.apply:
                print("✅ SQLite JSON 格式檢查通過")
                print("✅ 本機資料已完成讀取")
                print()
                print("🎉 模擬遷移檢查通過")
                print("尚未寫入任何雲端資料")
                return

            insert_strategies(
                cursor,
                local_data["telegram_strategy_state"],
            )

            insert_backtests(
                cursor,
                local_data["telegram_backtest_results"],
            )

            insert_web_state(
                cursor,
                local_data["web_state"],
            )

            counts = verify_records(
                cursor,
                local_data,
            )

            print()
            print("📋 雲端資料驗證")

            for table, count in counts.items():
                print(f"✅ {table}：{count} 筆")

            conn.commit()
            committed = True

            print()
            print("🎉 正式資料遷移成功！")
            print("✅ 三張表已提交 PostgreSQL")
            print("✅ 本機 SQLite 保持不變")

    except Exception as exc:
        print()
        print("❌ 遷移未完成")
        print("錯誤類型：", type(exc).__name__)

        if isinstance(exc, RuntimeError):
            print("原因：", str(exc))

        if conn is not None and not committed:
            conn.rollback()
            print("✅ PostgreSQL 已回復交易")

    finally:
        if conn is not None:
            if not committed:
                conn.rollback()
            conn.close()


if __name__ == "__main__":
    main()
