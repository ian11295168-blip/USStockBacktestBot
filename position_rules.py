
import math


SUPPORTED_METRICS = {
    "holding_days",
    "return_pct",
    "peak_return_pct",
    "pullback_pct"
}

COMPARISON_OPERATORS = {
    "gt", "gte", "lt", "lte", "eq"
}


def finite_number(value):
    return (
        type(value) in (int, float)
        and math.isfinite(value)
    )


class PositionState:
    """
    記錄一筆多頭持倉的收盤狀態。

    買進當天為第1個交易日。
    所有條件在當日收盤後才評估，
    不在當日收盤前提前使用資訊。
    """

    def __init__(self, entry_price):
        if (
            not finite_number(entry_price)
            or entry_price <= 0
        ):
            raise ValueError(
                "買進價格必須是大於0的有效數字"
            )

        self.entry_price = float(entry_price)
        self.holding_days = 0
        self.highest_close = None
        self.latest_close = None

    def update_close(self, close_price):
        """每個持有交易日收盤後呼叫一次。"""

        if (
            not finite_number(close_price)
            or close_price <= 0
        ):
            raise ValueError(
                "收盤價格必須是大於0的有效數字"
            )

        close_price = float(close_price)

        self.holding_days += 1
        self.latest_close = close_price

        if self.highest_close is None:
            self.highest_close = close_price
        else:
            self.highest_close = max(
                self.highest_close,
                close_price
            )

    def metrics(self):
        """取得目前收盤已知的持倉資訊。"""

        if self.latest_close is None:
            raise ValueError(
                "尚未更新第一個持有日收盤價"
            )

        current_return = (
            self.latest_close / self.entry_price - 1
        ) * 100

        peak_return = (
            self.highest_close / self.entry_price - 1
        ) * 100

        pullback = (
            1 - self.latest_close / self.highest_close
        ) * 100

        return {
            "holding_days": self.holding_days,
            "return_pct": current_return,
            "peak_return_pct": peak_return,
            "pullback_pct": pullback
        }


def validate_position_rule(rule, depth=0):
    """驗證通用持倉條件格式。"""

    if depth > 8:
        raise ValueError("持倉條件巢狀層數過深")

    if not isinstance(rule, dict):
        raise ValueError("持倉條件必須是物件")

    operator = rule.get("operator")

    if operator in ("and", "or"):
        if set(rule) != {"operator", "conditions"}:
            raise ValueError("持倉AND/OR格式錯誤")

        children = rule["conditions"]

        if (
            not isinstance(children, list)
            or not 2 <= len(children) <= 20
        ):
            raise ValueError(
                "持倉AND/OR必須包含2至20個條件"
            )

        for child in children:
            validate_position_rule(
                child, depth + 1
            )

        return True

    if operator not in COMPARISON_OPERATORS:
        raise ValueError(
            f"不支援的持倉運算子：{operator}"
        )

    if set(rule) != {
        "operator", "metric", "value"
    }:
        raise ValueError("持倉比較條件格式錯誤")

    metric = rule["metric"]
    value = rule["value"]

    if metric not in SUPPORTED_METRICS:
        raise ValueError(
            f"不支援的持倉資訊：{metric}"
        )

    if not finite_number(value):
        raise ValueError(
            "持倉比較值必須是有效數字"
        )

    if metric == "holding_days":
        if type(value) is not int or not 1 <= value <= 250:
            raise ValueError(
                "持有天數必須是1至250的整數"
            )

    return True


def evaluate_position_rule(rule, state):
    """用目前持倉狀態判斷出場條件。"""

    validate_position_rule(rule)

    if not isinstance(state, PositionState):
        raise ValueError(
            "必須提供PositionState物件"
        )

    values = state.metrics()

    def evaluate(node):
        operator = node["operator"]

        if operator == "and":
            return all(
                evaluate(child)
                for child in node["conditions"]
            )

        if operator == "or":
            return any(
                evaluate(child)
                for child in node["conditions"]
            )

        current = values[node["metric"]]
        target = node["value"]

        if operator == "gt":
            return current > target

        if operator == "gte":
            return current >= target

        if operator == "lt":
            return current < target

        if operator == "lte":
            return current <= target

        return math.isclose(
            current,
            target,
            rel_tol=1e-9,
            abs_tol=1e-9
        )

    return evaluate(rule)
