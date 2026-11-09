
"""v1.1：安全備份 Telegram 與網頁 SQLite 資料庫。"""

from datetime import datetime
from pathlib import Path
from contextlib import closing
import sqlite3


ROOT = Path(__file__).resolve().parent

BACKUP_DIR = ROOT / "local_db_backups"

DATABASES = [
    "strategies.db",
    "web_backtest.db",
]


def backup_database(source_path, destination_path):
    # 以唯讀方式開啟原始資料庫
    uri = source_path.resolve().as_uri() + "?mode=ro"

    with closing(
        sqlite3.connect(uri, uri=True, timeout=15)
    ) as source:

        # 由 SQLite 官方備份 API 產生一致性快照
        with closing(
            sqlite3.connect(
                destination_path,
                timeout=15,
            )
        ) as target:

            source.backup(target)

        # 確保備份資料庫可以正常讀取
        with closing(
            sqlite3.connect(
                destination_path
            )
        ) as check:

            result = check.execute(
                "PRAGMA integrity_check"
            ).fetchone()

            if result is None or result[0] != "ok":
                raise RuntimeError(
                    "備份資料完整性檢查失敗"
                )

            tables = check.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()

    return len(tables)


def main():
    print("US Stock Strategy Lab v1.1")
    print("SQLite 安全備份")
    print("=" * 40)

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    backup_folder = BACKUP_DIR / stamp

    backup_folder.mkdir(
        parents=True,
        exist_ok=False,
    )

    success = 0

    for filename in DATABASES:

        source = ROOT / filename

        if not source.is_file():
            print(f"❌ 找不到資料庫：{filename}")
            continue

        destination = backup_folder / filename

        try:
            table_count = backup_database(
                source,
                destination,
            )

            print(f"✅ {filename} 備份成功")
            print(f"   資料表：{table_count} 個")
            print(
                f"   檔案大小："
                f"{destination.stat().st_size:,} bytes"
            )

            success += 1

        except Exception as exc:
            print(f"❌ {filename} 備份失敗：{exc}")

            if destination.exists():
                destination.unlink()

    print()
    print(f"成功備份：{success}/{len(DATABASES)}")

    if success == len(DATABASES):
        print("✅ 兩個資料庫均已完整備份")
    else:
        print("⚠️ 尚未全部備份，先不要遷移")

    print("備份位置：", backup_folder)
    print("注意：備份檔案包含私人資料，不要上傳 GitHub")


if __name__ == "__main__":
    main()
