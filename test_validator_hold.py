
from strategy_validator import (
    validate_strategy,
    StrategyValidationError
)


strategy = {
    "symbol": "NVDA",
    "years": 5,
    "entry": {
        "operator": "consecutive",
        "period": 3,
        "condition": {
            "operator": "lt",
            "left": {
                "name": "rsi",
                "period": 14
            },
            "right": 30
        }
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
    "take_profit": None,
    "max_hold_days": 10
}

assert validate_strategy(strategy)
print("✅ 持有10天的策略通過驗證")

old_strategy = strategy.copy()
del old_strategy["max_hold_days"]

assert validate_strategy(old_strategy)
print("✅ 舊版策略仍然可以通過驗證")

bad_strategy = strategy.copy()
bad_strategy["max_hold_days"] = -1

try:
    validate_strategy(bad_strategy)
except StrategyValidationError:
    print("✅ 不合法持有天數已拒絕")
else:
    raise AssertionError("未拒絕不合法持有天數")

print("\n✅ 持有期限驗證測試全部通過")
