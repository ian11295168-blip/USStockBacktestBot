
from copy import deepcopy

from strategy_validator import (
    validate_strategy,
    StrategyValidationError
)


strategy = {
    "symbol": "NVDA",
    "years": 5,
    "entry": {
        "operator": "and",
        "conditions": [
            {
                "operator": "gt",
                "left": {
                    "name": "down_days",
                    "period": 3
                },
                "right": 0.5
            },
            {
                "operator": "lt",
                "left": {
                    "name": "rsi",
                    "period": 14
                },
                "right": 35
            }
        ]
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
    "take_profit": 10
}


def run_test(name, candidate, should_pass):
    try:
        validate_strategy(candidate)
        passed = True
        detail = "驗證通過"
    except StrategyValidationError as error:
        passed = False
        detail = str(error)

    if passed == should_pass:
        print(f"✅ {name}：符合預期")
    else:
        print(f"❌ {name}：結果不符合預期")

    print("   ", detail)


run_test(
    "正常策略",
    strategy,
    True
)

bad_indicator = deepcopy(strategy)
bad_indicator["exit"]["left"]["name"] = "macd"

run_test(
    "不支援MACD",
    bad_indicator,
    False
)

bad_period = deepcopy(strategy)
bad_period["exit"]["left"]["period"] = -14

run_test(
    "RSI負數週期",
    bad_period,
    False
)

bad_operator = deepcopy(strategy)
bad_operator["exit"]["operator"] = "unknown"

run_test(
    "不存在的運算子",
    bad_operator,
    False
)

bad_stop_loss = deepcopy(strategy)
bad_stop_loss["stop_loss"] = -5

run_test(
    "負數停損",
    bad_stop_loss,
    False
)

print("\n測試完成")
