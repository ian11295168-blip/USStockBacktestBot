
from copy import deepcopy

from universal_ai_parser import (
    parse_universal_strategy
)


text = (
    "NVDA的RSI14低於30買進，"
    "RSI14高於70賣出，"
    "持有滿5個交易日且報酬低於3%"
    "就賣出，回測5年。"
)

strategy = parse_universal_strategy(text)

rule = strategy["position_exit"]

assert rule["operator"] == "and"

conditions = rule["conditions"]

assert any(
    item["metric"] == "holding_days"
    and item["operator"] == "gte"
    and item["value"] == 5
    for item in conditions
)

assert any(
    item["metric"] == "return_pct"
    and item["operator"] == "lt"
    and item["value"] == 3
    for item in conditions
)

print("✅ AI正確理解持有5天且報酬不足3%")


modified = parse_universal_strategy(
    "把持有滿5天改成7天，其他全部不變。",
    deepcopy(strategy)
)

conditions = modified[
    "position_exit"
]["conditions"]

assert any(
    item["metric"] == "holding_days"
    and item["value"] == 7
    for item in conditions
)

assert any(
    item["metric"] == "return_pct"
    and item["value"] == 3
    for item in conditions
)

for key in (
    "symbol", "years",
    "entry", "exit",
    "stop_loss", "take_profit",
    "max_hold_days",
    "trailing_stop_pct"
):
    assert modified[key] == strategy[key], (
        f"不應改動：{key}"
    )

print("✅ AI只修改持有天數5天為7天")


cancelled = parse_universal_strategy(
    "取消持倉條件，其他全部不變。",
    deepcopy(modified)
)

assert cancelled["position_exit"] is None

for key in (
    "symbol", "years",
    "entry", "exit",
    "stop_loss", "take_profit",
    "max_hold_days",
    "trailing_stop_pct"
):
    assert cancelled[key] == modified[key], (
        f"取消時不應改動：{key}"
    )

print("✅ AI正確取消持倉條件")
print("✅ 其他策略欄位保留不變")

print("\n✅ AI通用持倉條件測試全部通過")
