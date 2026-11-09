
from database import (
    init_db,
    save_state,
    load_state,
    save_backtest,
    get_latest_backtest
)

# 使用測試專用ID，不影響正式Telegram帳號
TEST_USER_ID = 999999999

strategy = {
    "symbol": "NVDA",
    "years": 5,
    "entry": {
        "operator": "gt",
        "left": {
            "name": "down_days",
            "period": 3
        },
        "right": 0.5
    },
    "exit": {
        "operator": "gt",
        "left": {
            "name": "rsi",
            "period": 14
        },
        "right": 70
    },
    "stop_loss": 5,
    "take_profit": None
}

init_db()

# 儲存策略
save_state(TEST_USER_ID, {
    "last_strategy": strategy,
    "pending": None,
    "incomplete_strategy": None,
    "strategy_history": []
})

# 重新讀取
loaded = load_state(TEST_USER_ID)

print("策略儲存成功：", loaded["last_strategy"] == strategy)
print("股票：", loaded["last_strategy"]["symbol"])
print("停損：", loaded["last_strategy"]["stop_loss"])
print("回測年數：", loaded["last_strategy"]["years"])

# 儲存示範績效
save_backtest(
    TEST_USER_ID,
    strategy,
    {
        "total_return": 12.5,
        "trade_count": 5
    },
    []
)

result = get_latest_backtest(TEST_USER_ID)

print("回測資料儲存成功：", result is not None)
print("儲存的報酬：", result["stats"]["total_return"])

print("測試完成")
