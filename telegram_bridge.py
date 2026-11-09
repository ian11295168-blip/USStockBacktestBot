
"""Telegram 與 Streamlit 的唯讀資料橋接。

只讀取 Telegram 現有 SQLite 紀錄。
不呼叫 save_state 或 save_backtest。
"""

import os
from copy import deepcopy
from pathlib import Path

from dotenv import load_dotenv

from database import (
    load_state,
    get_latest_backtest,
)


PROJECT_DIR = Path(__file__).resolve().parent


def read_telegram_snapshot():
    """取得 Telegram 已確認策略及歷史紀錄。"""

    load_dotenv(
        dotenv_path=PROJECT_DIR / ".env"
    )

    owner_id = os.getenv("TELEGRAM_OWNER_ID")

    if not owner_id:
        raise ValueError(
            ".env 尚未設定 TELEGRAM_OWNER_ID"
        )

    try:
        user_id = int(owner_id)
    except ValueError as exc:
        raise ValueError(
            "TELEGRAM_OWNER_ID 必須是數字"
        ) from exc

    if user_id <= 0:
        raise ValueError(
            "TELEGRAM_OWNER_ID 必須大於0"
        )

    # 呼叫既有的 SQLite 讀取函式
    state = load_state(user_id) or {}

    if not isinstance(state, dict):
        raise ValueError(
            "Telegram 策略記憶格式錯誤"
        )

    latest = get_latest_backtest(user_id)

    # 對既有資料進行深複製，避免網頁修改物件
    confirmed = deepcopy(
        state.get("last_strategy")
    )

    history = deepcopy(
        state.get("strategy_history") or []
    )

    pending = deepcopy(
        state.get("pending")
    )

    if confirmed is not None and not isinstance(
        confirmed, dict
    ):
        raise ValueError(
            "Telegram 已確認策略格式錯誤"
        )

    if not isinstance(history, list):
        raise ValueError(
            "Telegram 歷史版本格式錯誤"
        )

    if latest is not None:
        if not isinstance(latest, dict):
            raise ValueError(
                "Telegram 回測紀錄格式錯誤"
            )

        latest = deepcopy(latest)

    return {
        "confirmed_strategy": confirmed,
        "strategy_history": history,
        "pending": pending,
        "latest_backtest": latest,
    }


if __name__ == "__main__":
    snapshot = read_telegram_snapshot()

    strategy = snapshot["confirmed_strategy"]
    history = snapshot["strategy_history"]
    record = snapshot["latest_backtest"]

    print("✅ Telegram 資料庫讀取成功")

    print(
        "已確認股票：",
        strategy.get("symbol", "未知")
        if strategy else "無"
    )

    print(
        "固定停損：",
        strategy.get("stop_loss")
        if strategy else "無"
    )

    print(
        "歷史版本數量：",
        len(history)
    )

    print(
        "最近回測：",
        record.get("symbol", "未知")
        if record else "無"
    )
