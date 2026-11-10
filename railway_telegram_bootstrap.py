"""v5.3 Telegram: safely initialize Railway volume from Supabase.

Never changes Supabase. Never overwrites an existing local database.
Refuses to start if local DB and cloud have diverged unless a valid
synchronization baseline already exists.
"""
import argparse
import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import database
import telegram_cloud_sync as cloud


class BootstrapError(RuntimeError):
    pass


def assert_volume():
    if "RAILWAY_PROJECT_ID" not in os.environ:
        return
    mounted = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "")
    data_dir = os.getenv("TELEGRAM_DATA_DIR", "")
    if not mounted or not data_dir:
        raise BootstrapError("Railway 尚未設定持久化 Volume / TELEGRAM_DATA_DIR")
    if Path(mounted).resolve() != Path(data_dir).resolve():
        raise BootstrapError("TELEGRAM_DATA_DIR 與 Railway Volume 掛載路徑不同")
    if not Path(mounted).is_dir():
        raise BootstrapError("Volume 掛載目錄不存在")
    if not os.access(mounted, os.W_OK):
        raise BootstrapError("Volume 不可寫入")


def cloud_snapshot():
    with closing(cloud.connect()) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = '30000ms'")
            states, tests = cloud.read_cloud(cur)
        conn.rollback()
    if not states or not tests:
        raise BootstrapError("Supabase Telegram 資料為空，拒絕啟動或還原")
    return states, tests


def indexed_equal(local, remote):
    a, b = local
    c, d = remote
    return (cloud.index_rows(a, "user_id") == cloud.index_rows(c, "user_id")
        and cloud.index_rows(b, "id") == cloud.index_rows(d, "id"))


def put_snapshot(path, states, tests):
    """Create a complete temp SQLite DB and validate it before rename."""
    if path.exists():
        raise BootstrapError("暫存檔已存在，拒絕覆寫：" + path.name)
    try:
        with closing(sqlite3.connect(str(path))) as conn:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""CREATE TABLE strategy_state (
                user_id INTEGER PRIMARY KEY,
                last_strategy TEXT, pending_strategy TEXT,
                incomplete_strategy TEXT,
                strategy_history TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL, symbol TEXT NOT NULL,
                strategy_json TEXT NOT NULL, stats_json TEXT NOT NULL,
                trades_json TEXT NOT NULL, created_at TEXT NOT NULL)""")
            for row in states:
                conn.execute("""INSERT INTO strategy_state
                    (user_id,last_strategy,pending_strategy,incomplete_strategy,
                     strategy_history,updated_at) VALUES (?,?,?,?,?,?)""",
                    (int(row["user_id"]),
                     json.dumps(row["last_strategy"], ensure_ascii=False),
                     json.dumps(row["pending_strategy"], ensure_ascii=False),
                     json.dumps(row["incomplete_strategy"], ensure_ascii=False),
                     json.dumps(row["strategy_history"], ensure_ascii=False),
                     row["updated_at"]))
            for row in tests:
                conn.execute("""INSERT INTO backtest_results
                    (id,user_id,symbol,strategy_json,stats_json,trades_json,created_at)
                    VALUES (?,?,?,?,?,?,?)""",
                    (int(row["id"]), int(row["user_id"]), row["symbol"],
                     json.dumps(row["strategy_json"], ensure_ascii=False),
                     json.dumps(row["stats_json"], ensure_ascii=False),
                     json.dumps(row["trades_json"], ensure_ascii=False),
                     row["created_at"]))
            conn.commit()
        # read via the same normalization as the deployed sync script
        # before moving temp into the canonical name.
        old = cloud.LOCAL_DB
        try:
            cloud.LOCAL_DB = path
            restored = cloud.read_local()
        finally:
            cloud.LOCAL_DB = old
        if not indexed_equal(restored, (states, tests)):
            raise BootstrapError("還原後的 SQLite 與 Supabase 快照不一致")
    except Exception:
        path.unlink(missing_ok=True)
        raise


def ensure_ready():
    """Runs before Bot startup; fail closed on unexpected state."""
    assert_volume()
    path = database.DB_PATH
    if path != cloud.LOCAL_DB:
        raise BootstrapError("Bot 與同步程式使用了不同 SQLite 路徑")
    path.parent.mkdir(parents=True, exist_ok=True)
    states, tests = cloud_snapshot()
    baseline_path = cloud.STATUS_FILE

    if path.exists():
        local = cloud.read_local()
        if baseline_path.exists():
            # A changed cloud version can be handled by normal sync's
            # conflict checks; do not auto-replace local data.
            baseline = cloud.read_baseline()
            remote = cloud.index_rows(states, "user_id")
            for uid, old_hash in baseline.items():
                if uid in remote and old_hash != cloud.fingerprint(remote[uid]):
                    # If local also agrees with cloud, a stale baseline can
                    # safely be refreshed only when FULL DB matches.
                    if indexed_equal(local, (states, tests)):
                        cloud.write_baseline(states)
                        break
                    raise BootstrapError("本機及雲端策略版本不同，拒絕自動啟動")
            print("✅ 現有 SQLite 與同步基準存在；保留本機資料")
        else:
            if not indexed_equal(local, (states, tests)):
                raise BootstrapError("SQLite 與雲端不同且無同步基準，拒絕啟動")
            cloud.write_baseline(states)
            print("✅ 既有 SQLite 與雲端一致，已建立同步基準")
        return

    if baseline_path.exists():
        raise BootstrapError("找不到 SQLite，但存在舊同步基準；拒絕覆寫")
    temp = path.with_suffix(".bootstrap.tmp")
    print("🔐 空 Volume：從 Supabase 還原 Telegram 歷史資料")
    put_snapshot(temp, states, tests)
    # Confirm remote has not changed before final activation.
    latest = cloud_snapshot()
    if not indexed_equal((states, tests), latest):
        temp.unlink(missing_ok=True)
        raise BootstrapError("還原期間 Supabase 資料變更，請重試")
    temp.replace(path)
    cloud.write_baseline(states)
    print(f"✅ 已還原：{len(states)} 筆策略、{len(tests)} 筆回測")
    print("✅ 同步基準已建立；允許 Telegram Bot 啟動")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="read-only cloud info")
    parser.add_argument("--initialize", action="store_true", help="restore/verify safely")
    args = parser.parse_args()
    if not (args.check or args.initialize):
        parser.print_help(); return
    try:
        assert_volume()
        if args.check:
            states, tests = cloud_snapshot()
            print(f"✅ Supabase：{len(states)} 筆策略、{len(tests)} 筆回測")
            print("✅ Bot DB 路徑與同步路徑一致" if database.DB_PATH == cloud.LOCAL_DB
                  else "❌ DB 路徑不一致")
        else:
            ensure_ready()
    except Exception as e:
        print("❌ 初始化/檢查失敗：", type(e).__name__)
        sys.exit(1)

if __name__ == "__main__":
    main()
