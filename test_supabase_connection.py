
"""v1.4 Supabase PostgreSQL 唯讀連線測試。

只檢查連線、資料表與筆數。
不修改雲端資料或本機 SQLite。
"""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent

load_dotenv(ROOT / ".env")

TABLES = [
    "telegram_strategy_state",
    "telegram_backtest_results",
    "web_state",
]


def main():
    print("US Stock Strategy Lab v1.4")
    print("Supabase PostgreSQL 連線測試")
    print("=" * 45)

    required = [
        "SUPABASE_DB_HOST",
        "SUPABASE_DB_PORT",
        "SUPABASE_DB_NAME",
        "SUPABASE_DB_USER",
        "SUPABASE_DB_PASSWORD",
    ]

    missing = [
        key for key in required
        if not os.getenv(key)
    ]

    if missing:
        print("❌ 缺少環境變數：")
        for key in missing:
            print(" -", key)
        return

    try:
        # 使用唯讀交易，避免修改資料
        with psycopg.connect(
            host=os.environ["SUPABASE_DB_HOST"],
            port=int(os.environ["SUPABASE_DB_PORT"]),
            dbname=os.environ["SUPABASE_DB_NAME"],
            user=os.environ["SUPABASE_DB_USER"],
            password=os.environ["SUPABASE_DB_PASSWORD"],
            sslmode="require",
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
        ) as conn:

            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()

                if result[0] != 1:
                    raise RuntimeError(
                        "資料庫回應不正確"
                    )

                print("✅ PostgreSQL 連線成功")
                print("✅ SSL 加密連線已啟用")
                print("✅ 唯讀交易模式已啟用")

                cur.execute(
                    """
                    SELECT tablename, rowsecurity
                    FROM pg_tables
                    WHERE schemaname = 'strategy_lab'
                    ORDER BY tablename
                    """
                )

                existing = dict(cur.fetchall())

                print()
                print("📋 雲端資料表檢查")

                all_ok = True

                for table in TABLES:

                    if table not in existing:
                        print(f"❌ 找不到：{table}")
                        all_ok = False
                        continue

                    if not existing[table]:
                        print(f"❌ RLS 未啟用：{table}")
                        all_ok = False
                        continue

                    # 表名來自程式內固定白名單，
                    # 不接受外部輸入。
                    cur.execute(
                        f'SELECT COUNT(*) '
                        f'FROM strategy_lab."{table}"'
                    )

                    count = cur.fetchone()[0]

                    print(
                        f"✅ {table}："
                        f"{count} 筆，RLS 已啟用"
                    )

                print()

                if all_ok:
                    print("🎉 v1.4 唯讀連線測試通過！")
                else:
                    print("⚠️ 部分資料表檢查未通過")

    except psycopg.Error as exc:
        print("❌ PostgreSQL 連線或查詢失敗")
        print("錯誤類型：", type(exc).__name__)
        print(
            "請檢查 Host、User、Port、"
            "資料庫密碼與網路連線。"
        )
        print(
            "為保護連線資訊，"
            "不顯示完整錯誤訊息。"
        )

    except Exception as exc:
        print("❌ 測試失敗")
        print("錯誤類型：", type(exc).__name__)


if __name__ == "__main__":
    main()
