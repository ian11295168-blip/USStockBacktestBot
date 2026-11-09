
from copy import deepcopy

from strategy_validator import (
    validate_strategy,
    StrategyValidationError
)


# 原本的RSI策略
old_strategy = {
    "symbol": "NVDA",
    "years": 5,
    "entry": {
        "operator": "lt",
        "left": {"name": "rsi", "period": 14},
        "right": 30
    },
    "exit": {
        "operator": "gt",
        "left": {"name": "rsi", "period": 14},
        "right": 70
    },
    "stop_loss": 5,
    "take_profit": None
}


# 新增的MACD策略
macd_strategy = {
    "symbol": "NVDA",
    "years": 5,
    "entry": {
        "operator": "and",
        "conditions": [
            {
                "operator": "cross_above",
                "left": {
                    "name": "macd",
                    "output": "line"
                },
                "right": {
                    "name": "macd",
                    "output": "signal"
                }
            },
            {
                "operator": "gt",
                "left": {"name": "close"},
                "right": {"name": "ma", "period": 20}
            }
        ]
    },
    "exit": {
        "operator": "cross_below",
        "left": {
            "name": "macd",
            "output": "line"
        },
        "right": {
            "name": "macd",
            "output": "signal"
        }
    },
    "stop_loss": 5,
    "take_profit": None
}


def check(name, strategy, expected):
    try:
        validate_strategy(strategy)
        actual = True
    except StrategyValidationError as error:
        actual = False
        print("拒絕原因：", error)

    assert actual == expected, f"{name}測試失敗"
    print("✅", name)


check("原本RSI策略", old_strategy, True)
check("新增MACD策略", macd_strategy, True)

bad = deepcopy(macd_strategy)
bad["entry"]["conditions"][0]["left"]["fast"] = 30
bad["entry"]["conditions"][0]["left"]["slow"] = 12

check("拒絕不合法MACD", bad, False)

bad = deepcopy(old_strategy)
bad["entry"]["left"]["name"] = "unknown"

check("拒絕未知指標", bad, False)

print("\n✅ 新舊策略驗證全部通過")
