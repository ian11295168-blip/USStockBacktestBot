
import pandas as pd

from strategy_engine import evaluate_condition
from strategy_validator import validate_strategy
from strategy_summary_v2 import format_strategy_summary


df = pd.DataFrame({
    "open": [10, 11, 12, 13, 14, 15, 16, 17],
    "high": [11, 12, 13, 14, 15, 16, 17, 18],
    "low": [9, 10, 11, 12, 13, 14, 15, 16],
    "close": [10, 11, 12, 13, 14, 15, 16, 17],
    "volume": [100, 200, 300, 400, 300, 200, 100, 200]
})

# 測試成交量連續3天大於150
condition = {
    "operator": "consecutive",
    "period": 3,
    "condition": {
        "operator": "gt",
        "left": {"name": "volume"},
        "right": 150
    }
}

result = evaluate_condition(df, condition)

assert result.tolist() == [
    False, False, False, True,
    True, True, False, False
]

print("✅ 連續3天條件判斷正確")

strategy = {
    "symbol": "NVDA",
    "years": 5,
    "entry": condition,
    "exit": {
        "operator": "gt",
        "left": {"name": "rsi", "period": 14},
        "right": 70
    },
    "stop_loss": 5,
    "take_profit": None
}

assert validate_strategy(strategy)

print("✅ 策略驗證器支援連續條件")

summary = format_strategy_summary(strategy)

assert "連續3個交易日" in summary

print("✅ Telegram中文摘要支援連續條件")

print("\n✅ 通用連續條件測試全部通過")
