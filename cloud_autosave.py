
"""US Stock Strategy Lab v2.2
Supabase 安全自動同步核心。

功能：
- 記錄最後一次成功同步的資料版本
- 偵測雲端資料是否被其他來源修改
- 同步前備份雲端舊資料
- 使用 PostgreSQL 交易與條件更新
- 寫入後驗證資料
- 同步失敗時保留本機 SQLite

使用：
    python cloud_autosave.py --init
        初始化同步基準，要求本機與雲端一致。

    python cloud_autosave.py --sync
        嘗試將目前本機網頁狀態同步到雲端。

正式整合時：
    from cloud_autosave import sync_local_to_cloud
    sync_local_to_cloud()

只處理 web_state，不修改 Telegram 資料表。
"""

import argparse
import hashlib
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
load_dotenv(ROOT / ".env")

LOCAL_DB = ROOT / "web_backtest.db"

PRIVATE_DIR = ROOT / "local_db_backups"
SNAPSHOT_DIR = PRIVATE_DIR / "cloud_web_snapshots"
STATUS_FILE = PRIVATE_DIR / "cloud_sync_status.json"

REQUIRED_ENV = (
    "SUPABASE_DB_HOST",
    "SUPABASE_DB_PORT",
    "SUPABASE_DB_NAME",
    "SUPABASE_DB_USER",
    "SUPABASE_DB_PASSWORD",
)


class CloudSyncError(Exception):
    pass


class CloudConflictError(CloudSyncError):
    pass


def prepare_private_dir():
    """確保私人同步檔案不會被 Git 追蹤。"""

    gitignore = ROOT / ".gitignore"

    text = (
        gitignore.read_text(encoding="utf-8")
        if gitignore.exists()
        else ""
    )

    rules = {
        line.strip()
        for line in text.splitlines()
    }

    if "local_db_backups/" not in rules:
        with gitignore.open(
            "a",
            encoding="utf-8",
        ) as file:
            if text and not text.endswith("\n"):
                file.write("\n")

            file.write(
                "\n# Private cloud synchronization data\n"
                "local_db_backups/\n"
            )

    PRIVATE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SNAPSHOT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def fingerprint(payload):
    """為 JSON 內容計算穩定的 SHA-256。"""

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def read_local():
    """唯讀取得本機 web_state。"""

    if not LOCAL_DB.is_file():
        raise CloudSyncError(
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
        raise CloudSyncError(
            "本機 web_state 沒有 id=1"
        )

    payload = json.loads(row[1])

    if not isinstance(payload, dict):
        raise CloudSyncError(
            "本機 payload 格式不正確"
        )

    fingerprint(payload)

    return {
        "id": row[0],
        "payload": payload,
        "updated_at": row[2],
    }


def connect():
    missing = [
        key for key in REQUIRED_ENV
        if not os.getenv(key)
    ]

    if missing:
        raise CloudSyncError(
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
        raise CloudSyncError(
            "雲端 web_state 沒有 id=1"
        )

    if not isinstance(row[1], dict):
        raise CloudSyncError(
            "雲端 payload 格式不正確"
        )

    return {
        "id": row[0],
        "payload": row[1],
        "updated_at": row[2],
    }


def read_status():
    if not STATUS_FILE.exists():
        return None

    data = json.loads(
        STATUS_FILE.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(data, dict):
        raise CloudSyncError(
            "同步狀態檔格式錯誤"
        )

    value = data.get("last_synced_hash")

    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise CloudSyncError(
            "同步基準無效，停止同步"
        )

    return data


def write_status(payload_hash):
    """以原子替換方式保存同步基準。"""

    prepare_private_dir()

    data = {
        "last_synced_hash": payload_hash,
        "synced_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    temp = STATUS_FILE.with_name(
        STATUS_FILE.name + ".tmp"
    )

    try:
        temp.write_text(
            json.dumps(
                data,
                indent=2,
            ),
            encoding="utf-8",
        )

        os.replace(temp, STATUS_FILE)
    finally:
        if temp.exists():
            temp.unlink()


def backup_cloud(cloud):
    """覆蓋雲端資料前先備份原始內容。"""

    prepare_private_dir()

    stamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d_%H%M%S_%f")

    destination = (
        SNAPSHOT_DIR
        / f"web_state_auto_{stamp}.json"
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

        file.flush()
        os.fsync(file.fileno())

    return destination


def initialize_sync():
    """只有本機和雲端完全一致才能初始化。"""

    local = read_local()
    local_hash = fingerprint(local["payload"])

    with closing(connect()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SET TRANSACTION READ ONLY"
            )
            cursor.execute(
                "SET LOCAL statement_timeout = '15000ms'"
            )

            cloud = read_cloud(cursor)
            cloud_hash = fingerprint(cloud["payload"])

        conn.rollback()

    if local_hash != cloud_hash:
        raise CloudConflictError(
            "本機與雲端內容不同，不能初始化。"
            "請先確認要保留哪個版本。"
        )

    write_status(local_hash)

    return {
        "status": "synced",
        "message": "同步基準建立成功",
    }


def get_local_sync_status():
    """只檢查本機狀態，不連線到 Supabase。"""

    status = read_status()

    if status is None:
        return {
            "status": "uninitialized",
            "message": "尚未初始化雲端同步",
        }

    try:
        local = read_local()

        if fingerprint(local["payload"]) == (
            status["last_synced_hash"]
        ):
            return {
                "status": "synced",
                "message": "本機資料與上次同步版本一致",
            }

        return {
            "status": "pending",
            "message": "本機有尚未同步的變更",
        }

    except Exception:
        return {
            "status": "error",
            "message": "無法檢查本機同步狀態",
        }


def sync_local_to_cloud():
    """將本機已保存狀態安全同步至 Supabase。"""

    status = read_status()

    if status is None:
        raise CloudSyncError(
            "尚未初始化同步基準。"
            "請先執行 python cloud_autosave.py --init"
        )

    local = read_local()
    local_hash = fingerprint(local["payload"])
    baseline_hash = status["last_synced_hash"]

    with closing(connect()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SET LOCAL statement_timeout = '30000ms'"
                )

                cloud = read_cloud(
                    cursor,
                    lock=True,
                )

                cloud_hash = fingerprint(
                    cloud["payload"]
                )

                # 雲端已經是本機版本：
                # 可能是前次提交成功，但狀態檔更新失敗。
                if cloud_hash == local_hash:
                    conn.rollback()
                    write_status(local_hash)

                    return {
                        "status": "synced",
                        "message": "雲端已是最新版本",
                    }

                # 雲端被其他來源修改過時，禁止覆蓋。
                if cloud_hash != baseline_hash:
                    raise CloudConflictError(
                        "偵測到雲端版本衝突。"
                        "雲端資料已與上次同步版本不同，"
                        "停止覆蓋。"
                    )

                # 不論是自動或手動重試，
                # 更新雲端前都先備份原有內容。
                backup_path = backup_cloud(cloud)

                cursor.execute(
                    """
                    UPDATE strategy_lab.web_state
                    SET payload = %s,
                        updated_at = %s,
                        migrated_at = now()
                    WHERE id = 1
                      AND payload = %s
                    RETURNING id
                    """,
                    (
                        Jsonb(local["payload"]),
                        local["updated_at"],
                        Jsonb(cloud["payload"]),
                    ),
                )

                if cursor.fetchone() is None:
                    raise CloudConflictError(
                        "雲端資料已變更，更新已取消"
                    )

                updated = read_cloud(cursor)

                if (
                    fingerprint(updated["payload"])
                    != local_hash
                ):
                    raise CloudSyncError(
                        "雲端寫入後內容驗證失敗"
                    )

                if (
                    updated["updated_at"]
                    != local["updated_at"]
                ):
                    raise CloudSyncError(
                        "雲端更新時間驗證失敗"
                    )

            conn.commit()

        except Exception:
            conn.rollback()
            raise

    # PostgreSQL 提交完成後再更新本機同步基準。
    write_status(local_hash)

    # 若保存期間又有新的本機變更，保留待同步狀態。
    latest = read_local()

    if fingerprint(latest["payload"]) != local_hash:
        return {
            "status": "pending",
            "message": "雲端已保存，但本機又有較新的變更",
        }

    return {
        "status": "synced",
        "message": "本機與 Supabase 同步成功",
        "backup": str(backup_path),
    }


def main():
    parser = argparse.ArgumentParser()

    group = parser.add_mutually_exclusive_group(
        required=True
    )

    group.add_argument(
        "--init",
        action="store_true",
        help="初始化同步基準",
    )

    group.add_argument(
        "--sync",
        action="store_true",
        help="執行雲端同步",
    )

    args = parser.parse_args()

    print("US Stock Strategy Lab v2.2")
    print("Supabase 安全同步核心")
    print("=" * 42)

    try:
        if args.init:
            result = initialize_sync()
        else:
            result = sync_local_to_cloud()

        print("✅", result["message"])

        if result.get("backup"):
            print(
                "✅ 雲端舊版本已備份到：",
                result["backup"],
            )

        if result["status"] == "pending":
            print("⚠️ 仍有尚未同步的本機變更")

    except CloudConflictError as exc:
        print("⚠️ 雲端版本衝突")
        print(str(exc))
        print("沒有覆蓋雲端資料")

    except Exception as exc:
        print("❌ 同步失敗")
        print("錯誤類型：", type(exc).__name__)

        if isinstance(exc, CloudSyncError):
            print("原因：", str(exc))

        print("本機 SQLite 保持不變")


if __name__ == "__main__":
    main()
