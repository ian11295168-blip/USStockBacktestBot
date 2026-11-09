
from position_rules import (
    PositionState,
    evaluate_position_rule,
    validate_position_rule
)


# 情境一：
# 買進後持有滿5天，報酬仍低於3%就出場
rule_timeout = {
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

state = PositionState(entry_price=100)

closes = [100, 101, 102, 101, 102]

for i, price in enumerate(closes, 1):
    state.update_close(price)

    triggered = evaluate_position_rule(
        rule_timeout, state
    )

    if i < 5:
        assert triggered is False
    else:
        assert triggered is True

assert state.metrics()["holding_days"] == 5

print("✅ 持有5天且報酬低於3%正確觸發")


# 情境二：
# 獲利曾達10%，從最高收盤價回落5%出場
rule_pullback = {
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

state = PositionState(entry_price=100)

for price in [100, 105, 112, 110]:
    state.update_close(price)

assert evaluate_position_rule(
    rule_pullback, state
) is False

state.update_close(105)

assert evaluate_position_rule(
    rule_pullback, state
) is True

print("✅ 獲利曾達10%後回落5%正確觸發")


# 情境三：兩類規則可以使用OR組合
combined_rule = {
    "operator": "or",
    "conditions": [
        rule_timeout,
        rule_pullback
    ]
}

assert validate_position_rule(combined_rule)

assert evaluate_position_rule(
    combined_rule, state
) is True

print("✅ AND／OR通用持倉條件可組合")


# 情境四：未知持倉資訊必須拒絕
bad_rule = {
    "operator": "gt",
    "metric": "unknown_metric",
    "value": 10
}

try:
    validate_position_rule(bad_rule)
except ValueError:
    print("✅ 未知持倉條件已拒絕")
else:
    raise AssertionError(
        "未拒絕未知持倉條件"
    )


# 情境五：每筆新交易必須重新計算持倉狀態
new_state = PositionState(entry_price=200)
new_state.update_close(200)

assert new_state.metrics()["holding_days"] == 1
assert new_state.metrics()["return_pct"] == 0
assert new_state.metrics()["pullback_pct"] == 0

print("✅ 新交易持倉狀態正確重設")


# 情境六：不合法買進價格必須拒絕
try:
    PositionState(entry_price=-100)
except ValueError:
    print("✅ 不合法買進價格已拒絕")
else:
    raise AssertionError(
        "未拒絕不合法買進價格"
    )


print("\n✅ 通用持倉條件測試全部通過")
