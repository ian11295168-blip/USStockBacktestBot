
"""部署前安全準備：保護 API 金鑰與私人資料。"""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent
GITIGNORE = ROOT / ".gitignore"

PROTECTED_RULES = [
    ".env",
    ".env.*",
    "!.env.example",
    ".streamlit/secrets.toml",
    "*.db",
    "*.db-*",
    "*.sqlite",
    "*.sqlite3",
    "__pycache__/",
    "*.py[cod]",
    "venv/",
    ".venv/",
    ".pytest_cache/",
    ".idea/",
    ".vscode/",
]

SENSITIVE_NAMES = {
    ".env",
    "secrets.toml",
}

SENSITIVE_SUFFIXES = (
    ".db",
    ".sqlite",
    ".sqlite3",
)


def update_gitignore():
    """保留既有規則，只新增缺少的保護項目。"""

    old_text = (
        GITIGNORE.read_text(encoding="utf-8")
        if GITIGNORE.exists()
        else ""
    )

    existing = {
        line.strip()
        for line in old_text.splitlines()
    }

    missing = [
        rule for rule in PROTECTED_RULES
        if rule not in existing
    ]

    if not missing:
        print("✅ .gitignore 已有必要保護規則")
        return

    with GITIGNORE.open(
        "a",
        encoding="utf-8",
    ) as file:
        if old_text and not old_text.endswith("\n"):
            file.write("\n")

        file.write(
            "\n# Deployment privacy protection\n"
        )

        for rule in missing:
            file.write(rule + "\n")

    print("✅ 已新增私人資料保護規則")


def check_tracked_files():
    """
    檢查 Git 已追蹤的私人資料。

    注意：
    .gitignore 不會自動解除已追蹤檔案。
    """

    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )

    except FileNotFoundError:
        print(
            "ℹ️ 尚未安裝 Git，"
            "無法檢查已追蹤檔案。"
        )
        return False

    if result.returncode != 0:
        print(
            "ℹ️ 目前尚未建立 Git 儲存庫，"
            "暫時不需要上傳檢查。"
        )
        return False

    paths = result.stdout.decode(
        "utf-8",
        errors="replace",
    ).split("\0")

    risky = []

    for path in paths:
        if not path:
            continue

        name = Path(path).name.lower()
        normalized = path.replace("\\", "/").lower()

        if (
            name in SENSITIVE_NAMES
            or name.startswith(".env.")
            and name != ".env.example"
            or name.endswith(SENSITIVE_SUFFIXES)
            or name.startswith("web_backtest.db-")
            or normalized.endswith(
                ".streamlit/secrets.toml"
            )
        ):
            risky.append(path)

    if risky:
        print("❌ 以下私人檔案已被 Git 追蹤：")

        for path in risky:
            print("  -", path)

        print(
            "\n請勿推送到 GitHub。"
            "需要先解除追蹤並檢查 Git 歷史。"
        )
        return True

    print("✅ 沒有發現已追蹤的常見私人資料")
    return False


def main():
    print("🔐 US Stock Strategy Lab 安全檢查\n")

    update_gitignore()

    risky = check_tracked_files()

    print("\n📋 部署準備狀態")

    if risky:
        print("❌ 尚未通過 Git 私人檔案檢查")
    else:
        print("✅ 已設定基本私人檔案排除規則")

    print(
        "⚠️ 這不是完整的程式碼機密掃描，"
        "不能偵測所有寫死在原始碼中的金鑰。"
    )

    print(
        "⚠️ 目前網站尚無正式登入及使用者隔離，"
        "不要直接公開部署。"
    )

    print(
        "⚠️ 雲端與本機的 SQLite 不會自動同步。"
    )


if __name__ == "__main__":
    main()
