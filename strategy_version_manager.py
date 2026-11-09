
"""策略版本管理：預覽、確認、取消與復原。"""

from copy import deepcopy
import secrets


MAX_HISTORY = 20


def make_pending_undo(state):
    """
    建立復原提案，但不刪除任何歷史版本。
    """

    if state.get("pending") is not None:
        raise ValueError(
            "目前有待確認策略。"
            "請先確認或取消，再使用 /undo。"
        )

    history = state.get("strategy_history") or []
    current = state.get("last_strategy")

    if not history:
        raise ValueError(
            "目前沒有可以復原的上一版策略。"
        )

    previous = deepcopy(history[-1])

    if previous == current:
        raise ValueError(
            "最近的歷史版本與目前策略相同。"
            "可能是舊版程式留下的待確認紀錄，"
            "請先檢查策略版本。"
        )

    pending = {
        "id": secrets.token_hex(4),
        "strategy": previous,
        "text": "恢復上一版策略",
        "kind": "undo",
        "expected_history_length": len(history),
    }

    # 只建立提案，完全不修改 history
    state["pending"] = pending

    return deepcopy(pending)


def make_pending_strategy(
    state,
    strategy,
    kind,
    text=""
):
    """
    建立新策略或修改提案。

    kind：
        new    建立全新策略
        modify 修改現有策略

    修改提案不會提前加入歷史紀錄。
    """

    if kind not in ("new", "modify"):
        raise ValueError("不支援的策略操作")

    if not isinstance(strategy, dict):
        raise ValueError("策略格式錯誤")

    existing = state.get("pending")
    confirmed = state.get("last_strategy")

    if kind == "modify":
        if existing and existing.get("kind") == "undo":
            raise ValueError(
                "請先取消復原提案，"
                "再修改策略。"
            )

        if existing and existing.get("kind") == "new":
            effective_kind = "new"
            base_strategy = None

        elif existing and existing.get("kind") == "modify":
            effective_kind = "modify"
            base_strategy = deepcopy(
                existing.get("base_strategy", confirmed)
            )

        else:
            effective_kind = "modify"
            base_strategy = deepcopy(confirmed)

        if base_strategy is None and effective_kind == "modify":
            raise ValueError(
                "沒有已確認策略可供修改"
            )
    else:
        effective_kind = "new"
        base_strategy = None

    pending = {
        "id": secrets.token_hex(4),
        "strategy": deepcopy(strategy),
        "text": text,
        "kind": effective_kind,
        "base_strategy": base_strategy,
    }

    state["pending"] = pending

    return deepcopy(pending)


def commit_pending(state, request_id):
    """
    在回測成功後呼叫。

    正式更新 last_strategy / history，
    並清除待確認策略。
    """

    pending = state.get("pending")

    if not isinstance(pending, dict):
        raise ValueError("沒有待確認的策略")

    if pending.get("id") != request_id:
        raise ValueError("確認的策略版本不一致")

    strategy = pending.get("strategy")

    if not isinstance(strategy, dict):
        raise ValueError("待確認策略格式錯誤")

    kind = pending.get("kind")

    # 相容舊版待確認的 undo
    if kind is None and pending.get("text") == "恢復上一版策略":
        kind = "undo"

    history = deepcopy(
        state.get("strategy_history") or []
    )
    confirmed = deepcopy(
        state.get("last_strategy")
    )
    new_strategy = deepcopy(strategy)

    if kind == "undo":
        if not history:
            raise ValueError(
                "歷史版本已不存在，無法復原"
            )

        if history[-1] != new_strategy:
            raise ValueError(
                "上一版策略已經改變，"
                "請重新提出復原"
            )

        expected_length = pending.get(
            "expected_history_length"
        )

        if (
            expected_length is not None
            and len(history) != expected_length
        ):
            raise ValueError(
                "歷史版本數量已改變，"
                "請重新提出復原"
            )

        # 成功確認時才移除一筆歷史版本
        history.pop()

    elif kind == "new":
        # 新策略是一條新的版本線
        history = []

    elif kind == "modify":
        if (
            confirmed is not None
            and confirmed != new_strategy
        ):
            # 避免舊版程式在「提案階段」
            # 已經放入的相同版本被重複追加
            if not history or history[-1] != confirmed:
                history.append(confirmed)

        history = history[-MAX_HISTORY:]

    elif kind is None:
        # 舊版程式可能沒有 kind 欄位。
        # 不直接猜測，以免破壞歷史版本。
        raise ValueError(
            "這是舊格式的待確認策略。"
            "請取消並重新建立修改提案。"
        )

    else:
        raise ValueError(
            f"不支援的版本操作：{kind}"
        )

    # 全部驗證成功後，才一次更新狀態
    state["strategy_history"] = history
    state["last_strategy"] = new_strategy
    state.pop("pending", None)

    return deepcopy(new_strategy)


def cancel_pending(state):
    """
    取消待確認提案。
    不影響已確認策略或歷史版本。
    """

    if state.get("pending") is None:
        return False

    state.pop("pending", None)
    return True
