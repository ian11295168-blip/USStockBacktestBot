from strategy_summary_v2 import format_strategy_summary

strategy = {
    "symbol": "NVDA",
    "years": 5,
    "entry": {
        "operator": "consecutive",
        "period": 3,
        "condition": {
            "operator": "lt",
            "left": {"name": "rsi", "period": 14},
            "right": 30
        }
    },
    "exit": {
        "operator": "gt",
        "left": {"name": "rsi", "period": 14},
        "right": 70
    },
    "stop_loss": 5,
    "take_profit": None,
    "max_hold_days": 10
}

summary = format_strategy_summary(strategy)

print(summary)

assert "最多持有10個交易日" in summary
assert "RSI14 > 70" in summary
assert "連續3個交易日" in summary

print("\n✅ 持有期限摘要測試通過")