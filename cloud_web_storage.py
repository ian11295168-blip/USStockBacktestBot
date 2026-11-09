
"""US Stock Strategy Lab v3.9
Supabase 網頁資料直接讀寫模組。

功能：
- 讀取雲端 web_state
- 使用 PostgreSQL 交易安全更新
- 使用預期版本防止覆蓋其他修改
- 更新後驗證 JSONB
- dry_run 模式自動 ROLLBACK
- 不依賴本機 SQLite

正式部署前仍需完成帳號權限與憑證安全設定。
"""

import argparse
import json
import os

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from dotenv import load_dotenv
from psycopg.types.json import Jsonb


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

REQUIRED_ENV = (
    "SUPABASE_DB_HOST",
    "SUPABASE_DB_PORT",
    "SUPABASE_DB_NAME",
    "SUPABASE_DB_USER",
    "SUPABASE_DB_PASSWORD",
)


class CloudStorageError(Exception):
    pass


class CloudConflictError(CloudStorageError):
    pass


def validate_payload(payload):
    """驗證可安全保存為 PostgreSQL JSONB。"""

    if not isinstance(payload, dict):
        raise CloudStorageError(
            "payload 必須是 JSON 物件"
        )

    try:
        json.dumps(
            payload,
            allow_nan=False,
        )

    except (TypeError, ValueError, OverflowError):
        raise CloudStorageError(
            "payload 包含無法保存的 JSON 資料"
        ) from None


def get_connection():
    """建立伺服器端 PostgreSQL 連線。"""

    missing = [
        key
        for key in REQUIRED_ENV
        if not os.getenv(key)
    ]

    if missing:
        raise CloudStorageError(
            "缺少 Supabase 連線設定："
            + ", ".join(missing)
        )

    return psycopg.connect(
        host=os.environ["SUPABASE_DB_HOST"],
        port=int(os.environ["SUPABASE_DB_PORT"]),
        dbname=os.environ["SUPABASE_DB_NAME"],
        user=os.environ["SUPABASE_DB_USER"],
        password=os.environ["SUPABASE_DB_PASSWORD"],
        sslmode="require",
        connect_timeout=15,
        autocommit=False,
    )


def _read_record(cursor, lock=False):
    query = """
        SELECT id, payload, updated_at
        FROM strategy_lab.web_state
        WHERE id = 1
    """

    if lock:
        query += " FOR UPDATE"

    cursor.execute(query)

    row = cursor.fetchone()

    if row is None:
        return None

    if not isinstance(row[1], dict):
        raise CloudStorageError(
            "雲端 payload 格式錯誤"
        )

    return {
        "id": row[0],
        "payload": row[1],
        "updated_at": row[2],
    }


def load_cloud_web_state():
    """從 Supabase 唯讀取得網頁狀態。"""

    with closing(get_connection()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SET TRANSACTION READ ONLY"
                )

                cursor.execute(
                    "SET LOCAL statement_timeout = '15000ms'"
                )

                record = _read_record(cursor)

            conn.rollback()
            return record

        except Exception:
            conn.rollback()
            raise


def save_cloud_web_state(
    payload,
    expected_payload,
    dry_run=False,
):
    """以樂觀鎖定方式更新 Supabase web_state。

    payload:
        準備寫入的新 JSON 資料。

    expected_payload:
        修改前讀取的雲端 JSON 資料。
        必須由呼叫端保留，不能更新前重新抓取
        來繞過衝突檢查。

    dry_run:
        True：測試更新後 ROLLBACK。
        False：驗證通過後 COMMIT。

    回傳：
        status: saved / unchanged / dry_run
    """

    validate_payload(payload)
    validate_payload(expected_payload)

    with closing(get_connection()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SET LOCAL statement_timeout = '30000ms'"
                )

                current = _read_record(
                    cursor,
                    lock=True,
                )

                if current is None:
                    raise CloudStorageError(
                        "找不到雲端 web_state id=1"
                    )

                # 重要：
                # 若雲端已不是先前讀取的版本，
                # 立即停止，不能覆蓋其他人的修改。
                if current["payload"] != expected_payload:
                    raise CloudConflictError(
                        "雲端資料版本已改變，禁止覆蓋"
                    )

                # 沒有內容變更就不更新。
                if current["payload"] == payload:
                    conn.rollback()

                    return {
                        "status": "unchanged",
                        "message": "雲端資料已是相同版本",
                    }

                now = datetime.now(
                    timezone.utc
                ).isoformat()

                # WHERE 再次檢查原版本。
                cursor.execute(
                    """
                    UPDATE strategy_lab.web_state
                    SET
                        payload = %s,
                        updated_at = %s,
                        migrated_at = now()
                    WHERE id = 1
                      AND payload = %s
                    RETURNING id
                    """,
                    (
                        Jsonb(payload),
                        now,
                        Jsonb(expected_payload),
                    ),
                )

                if cursor.fetchone() is None:
                    raise CloudConflictError(
                        "雲端資料已被修改，更新取消"
                    )

                updated = _read_record(cursor)

                if updated is None:
                    raise CloudStorageError(
                        "更新後找不到資料"
                    )

                if updated["payload"] != payload:
                    raise CloudStorageError(
                        "寫入後 JSONB 內容驗證失敗"
                    )

                if updated["updated_at"] != now:
                    raise CloudStorageError(
                        "雲端更新時間驗證失敗"
                    )

            if dry_run:
                conn.rollback()

                return {
                    "status": "dry_run",
                    "message": (
                        "模擬更新成功，"
                        "已執行 ROLLBACK"
                    ),
                }

            conn.commit()

            return {
                "status": "saved",
                "message": (
                    "Supabase 已成功保存並提交"
                ),
            }

        except Exception:
            conn.rollback()
            raise


def check_cloud_data():
    """唯讀檢查，不顯示私人策略。"""

    print("US Stock Strategy Lab v3.9")
    print("Supabase 網頁資料讀取檢查")
    print("=" * 45)

    record = load_cloud_web_state()

    if record is None:
        raise CloudStorageError(
            "雲端不存在 web_state id=1"
        )

    payload = record["payload"]

    print("✅ PostgreSQL 連線成功")
    print("✅ 雲端 web_state 讀取成功")
    print("✅ JSONB 格式正常")

    if isinstance(
        payload.get("confirmed_strategy"),
        dict,
    ):
        print("✅ 已確認策略存在")
    else:
        print("⚠️ 已確認策略不存在")

    if isinstance(
        payload.get("last_result"),
        dict,
    ):
        print("✅ 最近回測紀錄存在")
    else:
        print("⚠️ 最近回測紀錄不存在")

    print("✅ 沒有使用本機 SQLite")
    print("✅ 沒有修改 Supabase")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--check",
        action="store_true",
        help="只讀取雲端資料",
    )

    args = parser.parse_args()

    if not args.check:
        parser.print_help()
        return

    try:
        check_cloud_data()

    except Exception as exc:
        print("❌ 雲端檢查失敗")
        print("錯誤類型：", type(exc).__name__)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
