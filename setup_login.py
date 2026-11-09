
"""建立本機 Streamlit 登入憑證。

執行：python setup_login.py
不修改策略、回測結果或 Telegram 資料庫。
"""

import getpass
import hashlib
import secrets
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SECRETS_DIR = ROOT / ".streamlit"
SECRETS_FILE = SECRETS_DIR / "secrets.toml"

ITERATIONS = 600_000


def main():
    print("US Stock Strategy Lab — 設定登入密碼")
    print("=" * 42)

    if SECRETS_FILE.exists():
        print(
            "secrets.toml 已存在。"
            "為避免覆蓋其他金鑰，本程式不會修改它。"
        )
        return

    password = getpass.getpass("請設定登入密碼：")
    repeat = getpass.getpass("請再次輸入密碼：")

    if password != repeat:
        print("兩次密碼不一致，沒有建立任何檔案。")
        return

    if len(password) < 12:
        print("密碼至少需要 12 個字元。")
        return

    salt = secrets.token_bytes(32)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        ITERATIONS,
    )

    SECRETS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    content = (
        "[local_login]\n"
        f'salt = "{salt.hex()}"\n'
        f'password_hash = "{digest.hex()}"\n'
        f"iterations = {ITERATIONS}\n"
    )

    # 使用獨佔建立，避免覆蓋既有檔案
    try:
        with SECRETS_FILE.open(
            "x",
            encoding="utf-8",
        ) as file:
            file.write(content)
    except FileExistsError:
        print("設定檔已存在，操作取消。")
        return

    print()
    print("✅ 登入密碼設定成功")
    print("✅ 已產生 .streamlit/secrets.toml")
    print("🔒 檔案不可上傳 GitHub")
    print("請妥善保管你設定的密碼。")


if __name__ == "__main__":
    main()
