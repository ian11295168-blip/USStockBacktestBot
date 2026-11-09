
"""US Stock Strategy Lab v2.0
本機網頁 SQLite -> Supabase 手動安全同步。

用法：
    python sync_web_to_cloud.py
        唯讀比較，不更新。

    python sync_web_to_cloud.py --apply
        備份雲端舊狀態，確認後正式更新。

不修改本機 SQLite。
不修改 Telegram 資料表。
不輸出 API Key 或私人策略內容。
"""

import argparse
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb


ROOT = Path(__file__).resolve().parent

LOCAL_DB = ROOT / "web_backtest.db"
BACKUP_ROOT = ROOT / "local_db_backups"
BACKUP_DIR = BACKUP_ROOT / "cloud_web_snapshots"

load_dotenv(ROOT / ".env")

REQUIRED_ENV = (
    "SUPABASE_DB_HOST",
    "SUPABASE_DB_PORT",
    "SUPABASE_DB_NAME",
    "SUPABASE_DB_USER",
    "SUPABASE_DB_PASSWORD",
)


def load_local():
    """唯讀取得 SQLite 的網頁狀態。"""

    if not LOCAL_DB.is_file():
        raise RuntimeError(
            "找不到 web_backtest.db"
        )

    uri = LOCAL_DB.resolve().as_uri() + "?mode=ro"

    with closing(
        sqlite3.connect(
            uri,
            uri=True,
            timeout=15,
        )
    ) as conn:

        row = conn.execute(
            """
            SELECT id, payload, updated_at
            FROM web_state
            WHERE id = 1
            """
        ).fetchone()

    if row is None:
        raise RuntimeError(
            "本機 web_state 沒有 id=1 的資料"
        )

    payload = json.loads(row[1])

    if not isinstance(payload, dict):
        raise RuntimeError(
            "本機網頁 payload 格式錯誤"
        )

    # PostgreSQL JSONB 不接受 NaN / Infinity
    json.dumps(
        payload,
        allow_nan=False,
    )

    return {
        "id": row[0],
        "payload": payload,
        "updated_at": row[2],
    }


def get_connection():
    missing = [
        name for name in REQUIRED_ENV
        if not os.getenv(name)
    ]

    if missing:
        raise RuntimeError(
            "Supabase 連線設定不完整"
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


def read_cloud(cursor, lock=False):
    sql = """
        SELECT id, payload, updated_at
        FROM strategy_lab.web_state
        WHERE id = 1
    """

    if lock:
        sql += " FOR UPDATE"

    cursor.execute(sql)
    row = cursor.fetchone()

    if row is None:
        raise RuntimeError(
            "雲端 web_state 沒有 id=1 的資料，"
            "為安全起見停止同步"
        )

    if not isinstance(row[1], dict):
        raise RuntimeError(
            "雲端 payload 不是 JSON 物件"
        )

    return {
        "id": row[0],
        "payload": row[1],
        "updated_at": row[2],
    }


def same_payload(local, cloud):
    """比較策略、回測曲線及交易明細的 JSON。"""

    return local["payload"] == cloud["payload"]


def prepare_backup_folder():
    """
    保護私人雲端備份檔案：
    確保整個 local_db_backups 不會被 Git 追蹤。
    """

    gitignore = ROOT / ".gitignore"

    existing = (
        gitignore.read_text(encoding="utf-8")
        if gitignore.exists()
        else ""
    )

    if "local_db_backups/" not in {
        line.strip()
        for line in existing.splitlines()
    }:
        with gitignore.open(
            "a",
            encoding="utf-8",
        ) as file:
            if existing and not existing.endswith("\n"):
                file.write("\n")

            file.write(
                "\n# Private database snapshots\n"
                "local_db_backups/\n"
            )

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def backup_cloud(cloud):
    """先保存被更新前的雲端資料。"""

    prepare_backup_folder()

    stamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d_%H%M%S_%f")

    destination = (
        BACKUP_DIR / f"web_state_{stamp}.json"
    )

    content = json.dumps(
        cloud,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )

    with destination.open(
        "x",
        encoding="utf-8",
    ) as file:
        file.write(content)

    return destination


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--apply",
        action="store_true",
        help="正式同步本機網頁狀態到 Supabase",
    )

    args = parser.parse_args()

    print("US Stock Strategy Lab v2.0")
    print("網頁 SQLite / Supabase 資料同步")
    print("=" * 45)

    try:
        local = load_local()
    except Exception as exc:
        print("❌ 本機網頁資料讀取失敗")
        print("錯誤類型：", type(exc).__name__)
        return

    print("✅ 本機網頁資料讀取成功")
    print("✅ 本機 JSON 格式正常")

    if args.apply:
        print()
        print("即將以本機保存狀態更新 Supabase。")
        print("原本雲端狀態會先備份至本機。")

        answer = input(
            "輸入 SYNC WEB 確認："
        ).strip()

        if answer != "SYNC WEB":
            print("已取消，沒有修改雲端資料")
            return

    conn = None
    committed = False

    try:
        conn = get_connection()

        with conn.cursor() as cursor:
            cursor.execute(
                "SET LOCAL statement_timeout = '30000ms'"
            )

            if not args.apply:
                cursor.execute(
                    "SET TRANSACTION READ ONLY"
                )

            cloud = read_cloud(
                cursor,
                lock=args.apply,
            )

            print("✅ Supabase 雲端資料讀取成功")

            if same_payload(local, cloud):
                print("✅ 本機與雲端 payload 完全一致")
                print("不需要同步")
                return

            print("⚠️ 本機與雲端保存內容不同")

            if not args.apply:
                print()
                print("✅ 唯讀比較完成")
                print("沒有修改任何資料")
                print(
                    "若本機是你要保留的最新版本，"
                    "可使用 --apply 同步"
                )
                return

            # 必須先成功備份，才允許雲端更新
            destination = backup_cloud(cloud)

            print("✅ 雲端舊狀態已備份")
            print("備份位置：", destination)

            cursor.execute(
                """
                UPDATE strategy_lab.web_state
                SET payload = %s,
                    updated_at = %s,
                    migrated_at = now()
                WHERE id = 1
                """,
                (
                    Jsonb(local["payload"]),
                    local["updated_at"],
                ),
            )

            if cursor.rowcount != 1:
                raise RuntimeError(
                    "雲端更新筆數不正確"
                )

            updated = read_cloud(cursor)

            if (
                updated["payload"] != local["payload"]
                or updated["updated_at"] != local["updated_at"]
            ):
                raise RuntimeError(
                    "雲端資料驗證失敗"
                )

            print("✅ 雲端 JSON 內容驗證成功")
            print("✅ 更新時間驗證成功")

        conn.commit()
        committed = True

        print()
        print("🎉 v2.0 網頁雲端同步成功！")
        print("✅ 本機 SQLite 保持不變")
        print("✅ Telegram 資料保持不變")

    except Exception as exc:
        print()
        print("❌ 同步未完成")
        print("錯誤類型：", type(exc).__name__)

        if isinstance(exc, RuntimeError):
            print("原因：", str(exc))

        if conn is not None and not committed:
            conn.rollback()
            print("✅ 雲端交易已回復")

    finally:
        if conn is not None:
            if not committed:
                conn.rollback()
            conn.close()


if __name__ == "__main__":
    main()
