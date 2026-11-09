
"""US Stock Strategy Lab v1.5 — Supabase 寫入測試。

功能：
1. 連接 Supabase PostgreSQL
2. 在 web_state 建立一筆無敏感資訊的測試資料
3. 讀回並驗證
4. 刪除測試資料
5. 最後 ROLLBACK，不永久修改資料庫

不操作任何本機 SQLite。
"""

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

REQUIRED = [
    "SUPABASE_DB_HOST",
    "SUPABASE_DB_PORT",
    "SUPABASE_DB_NAME",
    "SUPABASE_DB_USER",
    "SUPABASE_DB_PASSWORD",
]


def get_connection():
    missing = [
        name for name in REQUIRED
        if not os.getenv(name)
    ]

    if missing:
        raise RuntimeError(
            "缺少環境變數：" + ", ".join(missing)
        )

    return psycopg.connect(
        host=os.environ["SUPABASE_DB_HOST"],
        port=int(os.environ["SUPABASE_DB_PORT"]),
        dbname=os.environ["SUPABASE_DB_NAME"],
        user=os.environ["SUPABASE_DB_USER"],
        password=os.environ["SUPABASE_DB_PASSWORD"],
        sslmode="require",
        connect_timeout=10,
        autocommit=False,
    )


def main():
    print("US Stock Strategy Lab v1.5")
    print("Supabase 寫入／讀取／刪除測試")
    print("=" * 45)

    # 隨機使用負數 ID，避開一般正式資料 ID
    test_id = -secrets.randbelow(2_000_000_000) - 1

    marker = secrets.token_hex(12)

    payload = {
        "test_only": True,
        "source": "v1.5_connection_test",
        "marker": marker,
    }

    now = datetime.now(
        timezone.utc
    ).isoformat()

    conn = None

    try:
        conn = get_connection()

        print("✅ PostgreSQL 連線成功")

        with conn.cursor() as cur:
            cur.execute(
                "SET LOCAL statement_timeout = '10000ms'"
            )

            # 1. 檢查測試 ID 沒有被使用
            cur.execute(
                """
                SELECT 1
                FROM strategy_lab.web_state
                WHERE id = %s
                """,
                (test_id,),
            )

            if cur.fetchone() is not None:
                raise RuntimeError(
                    "測試 ID 已存在，取消操作"
                )

            # 2. 在交易中寫入測試資料
            cur.execute(
                """
                INSERT INTO strategy_lab.web_state
                    (id, payload, updated_at)
                VALUES (%s, %s, %s)
                """,
                (
                    test_id,
                    Jsonb(payload),
                    now,
                ),
            )

            print("✅ 寫入測試資料成功")

            # 3. 從資料庫讀回資料
            cur.execute(
                """
                SELECT payload
                FROM strategy_lab.web_state
                WHERE id = %s
                """,
                (test_id,),
            )

            row = cur.fetchone()

            if row is None:
                raise RuntimeError(
                    "無法讀回測試資料"
                )

            saved = row[0]

            if isinstance(saved, str):
                saved = json.loads(saved)

            if saved != payload:
                raise RuntimeError(
                    "讀回資料與原始內容不同"
                )

            print("✅ 讀回測試資料成功")
            print("✅ JSONB 內容驗證成功")

            # 4. 刪除交易中的測試資料
            cur.execute(
                """
                DELETE FROM strategy_lab.web_state
                WHERE id = %s
                RETURNING id
                """,
                (test_id,),
            )

            deleted = cur.fetchone()

            if deleted is None:
                raise RuntimeError(
                    "刪除測試資料失敗"
                )

            print("✅ 刪除測試資料成功")

            # 5. 確認該筆測試資料不存在
            cur.execute(
                """
                SELECT COUNT(*)
                FROM strategy_lab.web_state
                WHERE id = %s
                """,
                (test_id,),
            )

            remaining = cur.fetchone()[0]

            if remaining != 0:
                raise RuntimeError(
                    "測試資料尚未清除"
                )

            print("✅ 測試資料清除驗證成功")

        # 6. 不提交任何變更
        conn.rollback()

        print("✅ ROLLBACK 完成")
        print()
        print("🎉 v1.5 測試全部通過！")
        print("沒有永久寫入任何測試資料。")

    except Exception as exc:
        print()
        print("❌ 測試未通過")
        print("錯誤類型：", type(exc).__name__)

        # 不輸出可能包含連線資訊的錯誤訊息
        if isinstance(exc, RuntimeError):
            print("原因：", str(exc))

    finally:
        if conn is not None:
            try:
                conn.rollback()
            finally:
                conn.close()


if __name__ == "__main__":
    main()
