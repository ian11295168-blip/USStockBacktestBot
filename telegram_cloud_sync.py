
"""US Stock Strategy Lab v2.4
Telegram SQLite -> Supabase 安全同步。

指令：
    python telegram_cloud_sync.py --init
    python telegram_cloud_sync.py --check
    python telegram_cloud_sync.py --sync

安全設計：
- 本機 SQLite 唯讀。
- 不修改 web_state。
- 歷史回測只允許新增，不覆蓋。
- 策略狀態使用同步基準防止版本衝突。
- 雲端更新前先備份。
- 全部 PostgreSQL 寫入使用同一筆交易。
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

DATA_DIR = Path(os.environ.get("TELEGRAM_DATA_DIR") or ROOT).resolve()
LOCAL_DB = DATA_DIR / "strategies.db"
PRIVATE_DIR = DATA_DIR / "local_db_backups"
BACKUP_DIR = PRIVATE_DIR / "telegram_cloud_snapshots"
STATUS_FILE = PRIVATE_DIR / "telegram_sync_status.json"

STATE_FIELDS = [
    "user_id",
    "last_strategy",
    "pending_strategy",
    "incomplete_strategy",
    "strategy_history",
    "updated_at",
]

BACKTEST_FIELDS = [
    "id",
    "user_id",
    "symbol",
    "strategy_json",
    "stats_json",
    "trades_json",
    "created_at",
]

STATE_JSON = [
    "last_strategy",
    "pending_strategy",
    "incomplete_strategy",
    "strategy_history",
]

BACKTEST_JSON = [
    "strategy_json",
    "stats_json",
    "trades_json",
]

ENV_KEYS = [
    "SUPABASE_DB_HOST",
    "SUPABASE_DB_PORT",
    "SUPABASE_DB_NAME",
    "SUPABASE_DB_USER",
    "SUPABASE_DB_PASSWORD",
]


class SyncError(Exception):
    pass


class ConflictError(SyncError):
    pass


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def fingerprint(value):
    return hashlib.sha256(
        canonical(value).encode("utf-8")
    ).hexdigest()


def parse_json(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        value = json.loads(value)
    canonical(value)
    return value


def normalize(row, json_fields):
    row = dict(row)
    if "user_id" in row:
        row["user_id"] = str(row["user_id"])

    for field in json_fields:
        row[field] = parse_json(row[field])

    return row


def read_local():
    if not LOCAL_DB.is_file():
        raise SyncError("找不到 strategies.db")

    uri = LOCAL_DB.resolve().as_uri() + "?mode=ro"

    with closing(
        sqlite3.connect(uri, uri=True, timeout=15)
    ) as conn:
        conn.row_factory = sqlite3.Row

        # 兩個 SELECT 取自同一個讀取快照。
        conn.execute("BEGIN")

        states = [
            normalize(row, STATE_JSON)
            for row in conn.execute(
                """
                SELECT user_id, last_strategy,
                       pending_strategy,
                       incomplete_strategy,
                       strategy_history, updated_at
                FROM strategy_state
                """
            )
        ]

        backtests = [
            normalize(row, BACKTEST_JSON)
            for row in conn.execute(
                """
                SELECT id, user_id, symbol,
                       strategy_json, stats_json,
                       trades_json, created_at
                FROM backtest_results
                """
            )
        ]

        conn.rollback()

    return states, backtests


def connect():
    missing = [
        key for key in ENV_KEYS if not os.getenv(key)
    ]

    if missing:
        raise SyncError("Supabase 連線設定不完整")

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


def read_cloud(cur, lock=False):
    suffix = " FOR UPDATE" if lock else ""

    cur.execute(
        """
        SELECT user_id, last_strategy,
               pending_strategy,
               incomplete_strategy,
               strategy_history, updated_at
        FROM strategy_lab.telegram_strategy_state
        """ + suffix
    )

    state_names = [col.name for col in cur.description]

    states = [
        normalize(dict(zip(state_names, row)), STATE_JSON)
        for row in cur.fetchall()
    ]

    cur.execute(
        """
        SELECT id, user_id, symbol,
               strategy_json, stats_json,
               trades_json, created_at
        FROM strategy_lab.telegram_backtest_results
        """ + suffix
    )

    backtest_names = [
        col.name for col in cur.description
    ]

    backtests = [
        normalize(
            dict(zip(backtest_names, row)),
            BACKTEST_JSON,
        )
        for row in cur.fetchall()
    ]

    return states, backtests


def index_rows(rows, key):
    indexed = {}

    for row in rows:
        value = str(row[key])

        if value in indexed:
            raise SyncError("資料中出現重複主鍵")

        indexed[value] = row

    return indexed


def prepare_private_dir():
    gitignore = ROOT / ".gitignore"

    content = (
        gitignore.read_text(encoding="utf-8")
        if gitignore.exists()
        else ""
    )

    rules = {
        line.strip()
        for line in content.splitlines()
    }

    if DATA_DIR == ROOT and "local_db_backups/" not in rules:
        with gitignore.open(
            "a", encoding="utf-8"
        ) as file:
            if content and not content.endswith("\n"):
                file.write("\n")
            file.write("\nlocal_db_backups/\n")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def save_json_file(path, data):
    temporary = path.with_name(path.name + ".tmp")

    try:
        with temporary.open(
            "w", encoding="utf-8"
        ) as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary, path)

    finally:
        if temporary.exists():
            temporary.unlink()


def write_baseline(states):
    prepare_private_dir()

    hashes = {
        str(row["user_id"]): fingerprint(row)
        for row in states
    }

    data = {
        "strategy_hashes": hashes,
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    save_json_file(STATUS_FILE, data)


def read_baseline():
    if not STATUS_FILE.is_file():
        raise SyncError(
            "尚未初始化，請先執行 --init"
        )

    data = json.loads(
        STATUS_FILE.read_text(encoding="utf-8")
    )

    hashes = data.get("strategy_hashes")

    if not isinstance(hashes, dict):
        raise SyncError("同步基準格式錯誤")

    if any(
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef"
               for c in value)
        for value in hashes.values()
    ):
        raise SyncError("同步基準內容無效")

    return hashes


def compare(local_rows, cloud_rows, key):
    local = index_rows(local_rows, key)
    cloud = index_rows(cloud_rows, key)

    local_keys = set(local)
    cloud_keys = set(cloud)

    common = local_keys & cloud_keys

    changed = sum(
        local[item] != cloud[item]
        for item in common
    )

    return {
        "local": len(local),
        "cloud": len(cloud),
        "new": len(local_keys - cloud_keys),
        "cloud_only": len(cloud_keys - local_keys),
        "changed": changed,
    }


def print_comparison(
    local_states, local_backtests,
    cloud_states, cloud_backtests,
):
    for title, local, cloud, key in [
        (
            "Telegram 策略狀態",
            local_states, cloud_states, "user_id",
        ),
        (
            "Telegram 回測紀錄",
            local_backtests, cloud_backtests, "id",
        ),
    ]:
        result = compare(local, cloud, key)

        print()
        print(title)
        print("  本機：", result["local"])
        print("  雲端：", result["cloud"])
        print("  只在本機：", result["new"])
        print("  只在雲端：", result["cloud_only"])
        print("  相同主鍵但內容不同：", result["changed"])


def initialize():
    local_states, local_backtests = read_local()

    with closing(connect()) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cloud_states, cloud_backtests = read_cloud(cur)
        conn.rollback()

    if (
        index_rows(local_states, "user_id")
        != index_rows(cloud_states, "user_id")
        or
        index_rows(local_backtests, "id")
        != index_rows(cloud_backtests, "id")
    ):
        raise ConflictError(
            "兩邊資料不同，不能初始化同步基準"
        )

    if STATUS_FILE.exists():
        old = read_baseline()

        new = {
            str(row["user_id"]): fingerprint(row)
            for row in cloud_states
        }

        if old != new:
            raise ConflictError(
                "已存在不同的同步基準，"
                "為避免覆蓋，停止重新初始化"
            )

    else:
        write_baseline(cloud_states)

    print("✅ Telegram 同步基準建立成功")
    print("✅ 本機與雲端資料完全一致")


def check():
    local_states, local_backtests = read_local()

    with closing(connect()) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cloud_states, cloud_backtests = read_cloud(cur)
        conn.rollback()

    print("✅ 兩邊資料讀取成功")

    print_comparison(
        local_states,
        local_backtests,
        cloud_states,
        cloud_backtests,
    )

    if (
        index_rows(local_states, "user_id")
        == index_rows(cloud_states, "user_id")
        and
        index_rows(local_backtests, "id")
        == index_rows(cloud_backtests, "id")
    ):
        print("\n✅ Telegram 雲端資料一致")
    else:
        print("\n⚠️ 有待同步或衝突的資料")


def backup_cloud(states, backtests):
    prepare_private_dir()

    stamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d_%H%M%S_%f")

    path = BACKUP_DIR / f"before_sync_{stamp}.json"

    # 含私人資料，僅儲存於已排除 Git 的資料夾。
    save_json_file(
        path,
        {
            "states": states,
            "backtests": backtests,
        },
    )

    return path


def synchronize():
    baseline = read_baseline()
    local_states, local_backtests = read_local()

    conn = None
    committed = False

    try:
        conn = connect()

        with conn.cursor() as cur:
            cur.execute(
                "SET LOCAL statement_timeout = '30000ms'"
            )

            cloud_states, cloud_backtests = (
                read_cloud(cur, lock=True)
            )

            ls = index_rows(local_states, "user_id")
            cs = index_rows(cloud_states, "user_id")
            lb = index_rows(local_backtests, "id")
            cb = index_rows(cloud_backtests, "id")

            # 雲端存在本機沒有的策略時，保守停止。
            if set(cs) - set(ls):
                raise ConflictError(
                    "雲端存在本機沒有的策略狀態"
                )

            # 已存在的回測紀錄絕不可被覆蓋。
            for key in set(lb) & set(cb):
                if lb[key] != cb[key]:
                    raise ConflictError(
                        "歷史回測出現同 ID 不同內容"
                    )

            # 只有雲端與同步基準相同時，
            # 才允許更新不同的策略狀態。
            for key, local_row in ls.items():
                cloud_row = cs.get(key)

                if cloud_row == local_row:
                    continue

                if cloud_row is None:
                    if key in baseline:
                        raise ConflictError(
                            "已同步的策略在雲端消失"
                        )
                    continue

                expected = baseline.get(key)

                if (
                    expected is None
                    or fingerprint(cloud_row) != expected
                ):
                    raise ConflictError(
                        "雲端策略版本發生衝突"
                    )

            changed_states = [
                row for key, row in ls.items()
                if cs.get(key) != row
            ]

            new_backtests = [
                row for key, row in lb.items()
                if key not in cb
            ]

            if not changed_states and not new_backtests:
                conn.rollback()
                write_baseline(cloud_states)
                print("✅ 雲端已是最新版本")
                return

            backup_path = backup_cloud(
                cloud_states, cloud_backtests
            )

            for row in changed_states:
                values = [
                    row[field] for field in STATE_FIELDS
                ]

                for i in (1, 2, 3, 4):
                    values[i] = Jsonb(values[i])

                if str(row["user_id"]) in cs:
                    cur.execute(
                        """
                        UPDATE strategy_lab.telegram_strategy_state
                        SET last_strategy = %s,
                            pending_strategy = %s,
                            incomplete_strategy = %s,
                            strategy_history = %s,
                            updated_at = %s
                        WHERE user_id = %s
                        """,
                        (
                            Jsonb(row["last_strategy"]),
                            Jsonb(row["pending_strategy"]),
                            Jsonb(row["incomplete_strategy"]),
                            Jsonb(row["strategy_history"]),
                            row["updated_at"],
                            row["user_id"],
                        ),
                    )
                    if cur.rowcount != 1:
                        raise SyncError(
                            "策略狀態更新筆數不正確"
                        )
                else:
                    cur.execute(
                        """
                        INSERT INTO
                        strategy_lab.telegram_strategy_state
                        (
                            user_id, last_strategy,
                            pending_strategy,
                            incomplete_strategy,
                            strategy_history, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        tuple(values),
                    )

            for row in new_backtests:
                cur.execute(
                    """
                    INSERT INTO
                    strategy_lab.telegram_backtest_results
                    (
                        id, user_id, symbol,
                        strategy_json, stats_json,
                        trades_json, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
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

            verify_states, verify_backtests = (
                read_cloud(cur)
            )

            if (
                index_rows(verify_states, "user_id")
                != ls
            ):
                raise SyncError(
                    "策略狀態驗證失敗"
                )

            verified = index_rows(
                verify_backtests, "id"
            )

            if any(
                verified.get(key) != row
                for key, row in lb.items()
            ):
                raise SyncError(
                    "歷史回測驗證失敗"
                )

        conn.commit()
        committed = True

        # 雲端提交後更新本機同步基準。
        write_baseline(verify_states)

        print("✅ Telegram 策略狀態同步成功")
        print(
            f"✅ 新增歷史回測："
            f"{len(new_backtests)} 筆"
        )
        print("✅ 雲端資料驗證成功")
        print("✅ 舊雲端版本已備份")
        print("備份位置：", backup_path)
        print("🎉 Telegram 雲端同步成功")

    except Exception:
        if conn is not None and not committed:
            conn.rollback()
        raise

    finally:
        if conn is not None:
            conn.close()


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(
        required=True
    )

    mode.add_argument("--init", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--sync", action="store_true")

    args = parser.parse_args()

    print("US Stock Strategy Lab v2.4")
    print("Telegram / Supabase 安全同步")
    print("=" * 44)

    try:
        if args.init:
            initialize()
        elif args.check:
            check()
        else:
            synchronize()

    except ConflictError as exc:
        print("⚠️ 偵測到資料版本衝突")
        print(str(exc))
        print("沒有覆蓋雲端資料")

    except Exception as exc:
        print("❌ 執行失敗")
        print("錯誤類型：", type(exc).__name__)
        if isinstance(exc, SyncError):
            print("原因：", str(exc))

    print("本機 SQLite 不會被修改")


if __name__ == "__main__":
    main()
