
from copy import deepcopy

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
    "max_hold_days": 10,
    "trailing_stop_pct": 8
}


# 測試一：合法追蹤停損
assert validate_strategy(strategy)

print("✅ 追蹤停損8%通過驗證")


# 測試二：固定停損與追蹤停損共存
assert strategy["stop_loss"] == 5
assert strategy["trailing_stop_pct"] == 8
assert validate_strategy(strategy)

print("✅ 固定停損與追蹤停損可以共存")


# 測試三：不設定追蹤停損
without_trailing = deepcopy(strategy)
without_trailing["trailing_stop_pct"] = None

assert validate_strategy(without_trailing)

print("✅ 不設定追蹤停損可以通過")


# 測試四：舊策略沒有追蹤停損欄位
old_strategy = deepcopy(strategy)
del old_strategy["trailing_stop_pct"]

assert validate_strategy(old_strategy)

print("✅ 舊版策略仍然相容")


# 測試五：負數追蹤停損
bad = deepcopy(strategy)
bad["trailing_stop_pct"] = -8

try:
    validate_strategy(bad)
except StrategyValidationError:
    print("✅ 負數追蹤停損已拒絕")
else:
    raise AssertionError("未拒絕負數追蹤停損")


# 測試六：100%追蹤停損
bad = deepcopy(strategy)
bad["trailing_stop_pct"] = 100

try:
    validate_strategy(bad)
except StrategyValidationError:
    print("✅ 100%追蹤停損已拒絕")
else:
    raise AssertionError("未拒絕100%追蹤停損")


# 測試七：無效的數值
for invalid in (True, "8", float("nan")):
    bad = deepcopy(strategy)
    bad["trailing_stop_pct"] = invalid

    try:
        validate_strategy(bad)
    except StrategyValidationError:
        continue

    raise AssertionError(
        f"未拒絕不合法數值：{invalid!r}"
    )

print("✅ 不合法追蹤停損數值已拒絕")

print("\n✅ 追蹤停損驗證測試全部通過")
