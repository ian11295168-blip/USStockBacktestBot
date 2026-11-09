
from copy import deepcopy

from strategy_summary_v2 import (
    format_strategy_summary,
    describe_position_condition
)

from strategy_diff import (
    compare_strategies,
    format_strategy_diff
)


original = {
    "symbol": "NVDA",
    "years": 5,
    "entry": {
        "operator": "lt",
        "left": {
            "name": "rsi",
            "period": 14
        },
        "right": 30
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
    "trailing_stop_pct": 8,
    "position_exit": {
        "operator": "and",
        "conditions": [
            {
                "operator": "gte",
                "metric": "holding_days",
                "value": 5
            },
            {
                "operator": "lt",
                "metric": "return_pct",
                "value": 3
            }
        ]
    }
}


# 測試一：中文摘要
summary = format_strategy_summary(original)

assert "持倉出場條件" in summary
assert "已持有交易日數 ≥ 5天" in summary
assert "目前持倉報酬率 < 3%" in summary
assert "下一交易日開盤出場" in summary
assert "追蹤停損" in summary
assert "8%" in summary

print("✅ 持倉條件在Telegram摘要中正常顯示")


# 測試二：修改持有天數
modified = deepcopy(original)

modified["position_exit"]["conditions"][0]["value"] = 7

changes = compare_strategies(original, modified)

assert len(changes) == 1
assert changes[0]["key"] == "position_exit"
assert "5天" in changes[0]["before"]
assert "7天" in changes[0]["after"]

diff_text = format_strategy_diff(original, modified)

assert "持倉出場條件" in diff_text

print("✅ 修改5天為7天，只顯示持倉條件差異")


# 測試三：取消持倉條件
cancelled = deepcopy(modified)
cancelled["position_exit"] = None

cancel_changes = compare_strategies(
    modified, cancelled
)

assert len(cancel_changes) == 1
assert cancel_changes[0]["key"] == "position_exit"
assert "未設定持倉出場條件" in (
    cancel_changes[0]["after"]
)

print("✅ 取消持倉條件正確顯示")


# 測試四：舊版策略沒有position_exit
old_strategy = deepcopy(original)
del old_strategy["position_exit"]

old_summary = format_strategy_summary(old_strategy)

assert "持倉出場條件" in old_summary
assert "未設定" in old_summary

print("✅ 舊版策略仍能正常顯示")


# 測試五：最高收盤報酬與回落條件
pullback_rule = {
    "operator": "and",
    "conditions": [
        {
            "operator": "gte",
            "metric": "peak_return_pct",
            "value": 10
        },
        {
            "operator": "gte",
            "metric": "pullback_pct",
            "value": 5
        }
    ]
}

description = describe_position_condition(
    pullback_rule
)

assert "持倉最高收盤報酬率 ≥ 10%" in description
assert "從最高收盤價回落 ≥ 5%" in description

print("✅ 最高收盤報酬與回落條件正常顯示")


# 測試六：追蹤停損差異仍正常
trailing_modified = deepcopy(original)
trailing_modified["trailing_stop_pct"] = 6

trailing_changes = compare_strategies(
    original, trailing_modified
)

assert len(trailing_changes) == 1
assert trailing_changes[0]["key"] == "trailing_stop_pct"

print("✅ 原本追蹤停損差異功能保留")


print("\n✅ 持倉條件顯示測試全部通過")
