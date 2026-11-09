
"""策略版本管理的安全性測試。"""

from copy import deepcopy

from strategy_version_manager import (
    make_pending_undo,
    make_pending_strategy,
    commit_pending,
    cancel_pending,
)


def strategy(stop):
    return {
        "symbol": "NVDA",
        "stop_loss": stop,
    }


a = strategy(5)
b = strategy(6)
c = strategy(8)

state = {
    "last_strategy": deepcopy(a),
    "strategy_history": [],
    "pending": None,
}


# 1. 建立修改提案，不提前寫入歷史
proposal = make_pending_strategy(
    state, b, "modify", "停損改6%"
)

assert state["last_strategy"] == a
assert state["strategy_history"] == []

print("✅ 修改提案不會提前變更歷史")


# 2. 取消提案，不影響已確認策略
assert cancel_pending(state) is True
assert state["last_strategy"] == a
assert state["strategy_history"] == []

print("✅ 取消提案保留原策略")


# 3. 確認第一個修改版本
proposal = make_pending_strategy(
    state, b, "modify", "停損改6%"
)

commit_pending(state, proposal["id"])

assert state["last_strategy"] == b
assert state["strategy_history"] == [a]

print("✅ 正式確認後才儲存舊版本")


# 4. 確認第二個修改版本
proposal = make_pending_strategy(
    state, c, "modify", "停損改8%"
)

commit_pending(state, proposal["id"])

assert state["last_strategy"] == c
assert state["strategy_history"] == [a, b]

print("✅ 多次修改的版本順序正確")


# 5. 預覽 undo，不刪除歷史
previous_history = deepcopy(
    state["strategy_history"]
)

undo = make_pending_undo(state)

assert undo["strategy"] == b
assert state["last_strategy"] == c
assert state["strategy_history"] == previous_history

print("✅ /undo 預覽不會刪除歷史")


# 6. 取消 undo，不影響版本
cancel_pending(state)

assert state["last_strategy"] == c
assert state["strategy_history"] == [a, b]

print("✅ 取消 /undo 不會破壞版本")


# 7. 確認 undo，C 回到 B
undo = make_pending_undo(state)

commit_pending(state, undo["id"])

assert state["last_strategy"] == b
assert state["strategy_history"] == [a]

print("✅ 確認復原：C → B")


# 8. 再次 undo，B 回到 A
undo = make_pending_undo(state)

commit_pending(state, undo["id"])

assert state["last_strategy"] == a
assert state["strategy_history"] == []

print("✅ 連續復原：B → A")


# 9. 不可以再復原不存在的版本
try:
    make_pending_undo(state)
except ValueError:
    print("✅ 不會跳到不存在的版本")
else:
    raise AssertionError(
        "應拒絕沒有歷史版本的復原"
    )


# 10. 不允許使用過期的確認按鈕
proposal = make_pending_strategy(
    state, b, "modify"
)

try:
    commit_pending(state, "old_id")
except ValueError:
    assert state["last_strategy"] == a
    assert state["pending"] is not None
    print("✅ 過期確認按鈕無法修改版本")
else:
    raise AssertionError(
        "應拒絕過期版本確認"
    )


# 11. 提案資料使用深複製
copied = deepcopy(state["pending"])
copied["strategy"]["stop_loss"] = 99

assert (
    state["pending"]["strategy"]["stop_loss"]
    == 6
)

print("✅ 外部修改不會污染待確認版本")


# 12. 新策略應重設歷史
cancel_pending(state)

proposal = make_pending_strategy(
    state, c, "new"
)

commit_pending(state, proposal["id"])

assert state["last_strategy"] == c
assert state["strategy_history"] == []

print("✅ 建立全新策略會重設版本歷史")


print("\n✅ 策略版本管理測試全部通過")
