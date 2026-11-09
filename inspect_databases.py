
"""v1.0 — 本機 SQLite 資料庫結構檢查。

只讀取資料庫結構與資料筆數。
不顯示私人策略、API 金鑰或交易內容。
不建立、不修改、不刪除資料庫。
"""

from pathlib import Path
from urllib.parse import quote
import sqlite3


ROOT = Path(__file__).resolve().parent

SKIP_DIRS = {
    ".git",
    "venv",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
}

DB_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
}


def find_databases():
    databases = []

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue

        relative = path.relative_to(ROOT)

        if any(
            part.lower() in SKIP_DIRS
            for part in relative.parts
        ):
            continue

        if path.suffix.lower() in DB_SUFFIXES:
            databases.append(path)

    return sorted(databases)


def inspect_database(path):
    """使用 SQLite 唯讀模式檢查結構。"""

    relative = path.relative_to(ROOT)

    print()
    print("=" * 48)
    print(f"📁 資料庫：{relative}")
    print("=" * 48)

    # 使用 URI 唯讀模式，避免建立新資料庫
    uri_path = quote(
        path.resolve().as_posix(),
        safe="/:",
    )

    uri = f"file:{uri_path}?mode=ro"

    try:
        with sqlite3.connect(
            uri,
            uri=True,
            timeout=3,
        ) as conn:

            conn.execute("PRAGMA query_only = ON")

            tables = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()

            print(f"資料表數量：{len(tables)}")

            for (table_name,) in tables:
                safe_name = (
                    '"' + table_name.replace(
                        '"', '""'
                    ) + '"'
                )

                print()
                print(f"  📋 資料表：{table_name}")

                columns = conn.execute(
                    f"PRAGMA table_info({safe_name})"
                ).fetchall()

                column_names = [
                    item[1]
                    for item in columns
                ]

                print(
                    "     欄位："
                    + ", ".join(column_names)
                )

                try:
                    count = conn.execute(
                        f"SELECT COUNT(*) FROM {safe_name}"
                    ).fetchone()[0]

                    print(f"     資料筆數：{count}")

                except sqlite3.Error:
                    print(
                        "     資料筆數：無法讀取"
                    )

    except sqlite3.Error as exc:
        print(f"⚠️ 無法讀取資料庫：{exc}")


def main():
    print("🔍 US Stock Strategy Lab")
    print("v1.0 SQLite 資料庫結構檢查")
    print()

    databases = find_databases()

    print(
        f"找到 SQLite 資料庫："
        f"{len(databases)} 個"
    )

    if not databases:
        print(
            "⚠️ 找不到 SQLite 資料庫。"
            "請確認目前的專案資料夾。"
        )
        return

    for path in databases:
        inspect_database(path)

    print()
    print("=" * 48)
    print("✅ 結構檢查完成")
    print("✅ 沒有輸出私人策略或交易內容")
    print("✅ 沒有執行資料庫寫入操作")
    print()
    print(
        "下一步：根據資料表結構，"
        "設計雲端資料保存方式。"
    )


if __name__ == "__main__":
    main()
