
from copy import deepcopy

from universal_ai_parser import parse_universal_strategy


original = {
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
    "take_profit": None,
    "max_hold_days": 10,
    "trailing_stop_pct": 8
}


modified = parse_universal_strategy(
    "把追蹤停損改成6%，其他全部不變。",
    deepcopy(original)
)

assert modified["trailing_stop_pct"] == 6

for key in (
    "symbol", "years",
    "entry", "exit",
    "stop_loss", "take_profit",
    "max_hold_days"
):
    assert modified[key] == original[key], (
        f"AI意外修改了：{key}"
    )

print("✅ 追蹤停損8%修改成6%")
print("✅ 其他策略欄位保持不變")


cancelled = parse_universal_strategy(
    "取消追蹤停損，其他全部不變。",
    deepcopy(modified)
)

assert cancelled["trailing_stop_pct"] is None

for key in (
    "symbol", "years",
    "entry", "exit",
    "stop_loss", "take_profit",
    "max_hold_days"
):
    assert cancelled[key] == modified[key], (
        f"取消追蹤停損時意外修改了：{key}"
    )

print("✅ 取消追蹤停損成功")
print("✅ 原本固定停損及持有期限不變")

print("\n✅ AI追蹤停損修改測試全部通過")
