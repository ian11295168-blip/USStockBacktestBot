
from copy import deepcopy

from strategy_diff import (
    compare_strategies,
    format_strategy_diff
)


original = {
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


# 測試一：只修改最大持有期限
modified = deepcopy(original)
modified["max_hold_days"] = 15

changes = compare_strategies(original, modified)

assert len(changes) == 1
assert changes[0]["key"] == "max_hold_days"

text = format_strategy_diff(original, modified)

assert "最多持有10個交易日" in text
assert "最多持有15個交易日" in text

print("✅ 10天修改成15天正確")


# 測試二：取消最大持有期限
modified = deepcopy(original)
modified["max_hold_days"] = None

text = format_strategy_diff(original, modified)

assert "不限制持有天數" in text

print("✅ 取消最大持有期限正確")


# 測試三：AI意外修改賣出條件
modified = deepcopy(original)
modified["max_hold_days"] = 15
modified["exit"]["right"] = 80

changes = compare_strategies(original, modified)

changed_fields = {
    item["key"]
    for item in changes
}

assert changed_fields == {
    "max_hold_days",
    "exit"
}

print("✅ 能偵測AI意外修改賣出條件")


# 測試四：舊策略沒有max_hold_days
old_strategy = deepcopy(original)
del old_strategy["max_hold_days"]

new_strategy = deepcopy(original)
new_strategy["max_hold_days"] = None

changes = compare_strategies(
    old_strategy,
    new_strategy
)

assert changes == []

print("✅ 相容舊版策略")


# 測試五：沒有修改任何條件
same = deepcopy(original)

text = format_strategy_diff(original, same)

assert "沒有發現設定變化" in text

print("✅ 未修改策略正確辨識")


print("\n✅ 策略差異檢查全部通過")
