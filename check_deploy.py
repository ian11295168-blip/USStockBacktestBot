
"""US Stock Strategy Lab v0.9 — 雲端套件需求檢查。

掃描專案 Python 匯入項目，產生套件候選清單。
不讀取 .env 或 secrets.toml。
不更動資料庫、策略及回測結果。
"""

import ast
import importlib.metadata as metadata
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent

SKIP_DIRS = {
    "venv", ".venv", "__pycache__",
    "backup", ".git", ".pytest_cache",
}

SKIP_FILES = {
    "check_deploy.py",
    "prepare_deploy.py",
    "setup_login.py",
}

ALIASES = {
    "dotenv": "python-dotenv",
    "telegram": "python-telegram-bot",
    "alpaca": "alpaca-py",
    "sklearn": "scikit-learn",
    "PIL": "Pillow",
    "yaml": "PyYAML",
    "cv2": "opencv-python",
    "bs4": "beautifulsoup4",
    "dateutil": "python-dateutil",
}

STANDARD = set(
    getattr(sys, "stdlib_module_names", ())
)

PACKAGE_MAP = metadata.packages_distributions()


def source_files():
    found = []

    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT)

        if any(
            part in SKIP_DIRS
            for part in relative.parts[:-1]
        ):
            continue

        if path.name.startswith("test_"):
            continue

        if path.name in SKIP_FILES:
            continue

        found.append(path)

    return found


def scan_imports(path):
    text = path.read_text(
        encoding="utf-8-sig"
    )

    tree = ast.parse(
        text,
        filename=str(path),
    )

    names = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(
                    alias.name.split(".")[0]
                )

        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(
                    node.module.split(".")[0]
                )

    return names


def main():
    print("📦 v0.9 Python 套件檢查")
    print("=" * 38)

    files = source_files()

    local_modules = {
        path.stem
        for path in ROOT.glob("*.py")
    }

    local_modules.update({
        path.name
        for path in ROOT.iterdir()
        if path.is_dir()
        and (path / "__init__.py").exists()
    })

    imports = set()
    errors = []

    for path in files:
        try:
            imports.update(
                scan_imports(path)
            )
        except Exception as exc:
            errors.append(
                f"{path.name}: {exc}"
            )

    external = sorted(
        name
        for name in imports
        if name not in STANDARD
        and name not in local_modules
        and name != "__future__"
    )

    requirements = {}
    unresolved = []

    for name in external:
        choices = PACKAGE_MAP.get(name, [])

        preferred = ALIASES.get(name)

        if preferred:
            package = preferred
        elif len(choices) == 1:
            package = choices[0]
        else:
            unresolved.append(name)
            continue

        try:
            version = metadata.version(package)
            requirements[package] = version
        except metadata.PackageNotFoundError:
            unresolved.append(name)

    destination = (
        ROOT / "requirements_candidate.txt"
    )

    lines = [
        f"{name}=={version}"
        for name, version in sorted(
            requirements.items(),
            key=lambda item: item[0].lower(),
        )
    ]

    destination.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print(
        f"掃描 Python 檔案：{len(files)} 個"
    )

    print(
        f"辨識外部套件：{len(requirements)} 個"
    )

    print()
    print("📋 已辨識套件：")

    for line in lines:
        print("  ", line)

    if unresolved:
        print()
        print("⚠️ 尚未辨識或未安裝：")

        for name in unresolved:
            print("  ", name)

    if errors:
        print()
        print("⚠️ 部分原始碼無法解析：")

        for error in errors:
            print("  ", error)

    print()
    print(
        "✅ 已產生 requirements_candidate.txt"
    )
    print(
        "注意：這只是候選清單，"
        "還不能直接視為部署完成。"
    )
    print(
        "正式部署前需要檢查動態匯入、"
        "跨平台相容性和 Python 版本。"
    )


if __name__ == "__main__":
    main()
