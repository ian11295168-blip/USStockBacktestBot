
"""網頁版 SQLite 保存與恢復測試。"""

import tempfile
from pathlib import Path

import pandas as pd

from web_storage import (
    load_web_state,
    save_web_state,
)


def strategy(stop):
    return {
        "symbol": "NVDA",
        "years": 5,
        "stop_loss": stop,
    }


with tempfile.TemporaryDirectory() as folder:
    db = Path(folder) / "test_web.db"

    assert load_web_state(db) is None
    print("✅ 新資料庫初始為空")

    old_strategy = strategy(5)
    current_strategy = strategy(6)

    df = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2025-01-02",
            "2025-01-03",
            "2025-01-06",
        ], utc=True),
        "close": [100.0, 102.0, 105.0],
        "equity": [10000.0, 10100.0, 10300.0],
    })

    result = {
        "strategy": current_strategy,
        "df": df,
        "trades": [
            {
                "buy_date": "2025-01-02",
                "sell_date": "2025-01-06",
                "return_pct": 3.0,
                "reason": "策略出場",
            }
        ],
        "stats": {
            "total_return": 3.0,
            "final_equity": 10300.0,
        },
    }

    save_web_state(
        current_strategy,
        old_strategy,
        result,
        db_path=db,
    )

    assert db.exists()
    print("✅ SQLite 資料庫建立成功")

    loaded = load_web_state(db)

    assert loaded["confirmed_strategy"]["stop_loss"] == 6
    assert (
        loaded["previous_confirmed_strategy"]["stop_loss"]
        == 5
    )
    print("✅ 目前策略及上一版策略恢復成功")

    loaded_result = loaded["last_result"]

    assert loaded_result["stats"]["total_return"] == 3.0
    assert len(loaded_result["trades"]) == 1
    assert len(loaded_result["df"]) == 3

    print("✅ 績效、交易紀錄與資產曲線恢復成功")

    assert (
        pd.to_datetime(
            loaded_result["df"]["timestamp"],
            utc=True,
        ).iloc[0]
        == pd.Timestamp("2025-01-02", tz="UTC")
    )

    print("✅ 回測日期恢復成功")

    newer_strategy = strategy(8)

    save_web_state(
        newer_strategy,
        current_strategy,
        result,
        db_path=db,
    )

    updated = load_web_state(db)

    assert updated["confirmed_strategy"]["stop_loss"] == 8
    assert (
        updated["previous_confirmed_strategy"]["stop_loss"]
        == 6
    )

    print("✅ 再次保存可正確更新版本")

print("\n✅ 網頁版資料保存測試全部通過")
