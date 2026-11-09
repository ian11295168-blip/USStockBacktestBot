
import math
import re

from position_rules import validate_position_rule


class StrategyValidationError(ValueError):
    pass


INDICATOR_PARAMS = {
    "open": {"name", "multiplier"},
    "high": {"name", "multiplier"},
    "low": {"name", "multiplier"},
    "close": {"name", "multiplier"},
    "volume": {"name", "multiplier"},
    "ma": {"name", "period", "multiplier"},
    "volume_ma": {"name", "period", "multiplier"},
    "rsi": {"name", "period", "multiplier"},
    "ema": {"name", "period", "multiplier"},
    "down_days": {"name", "period", "multiplier"},
    "up_days": {"name", "period", "multiplier"},
    "volume_down_days": {
        "name", "period", "multiplier"
    },
    "macd": {
        "name", "fast", "slow",
        "signal", "output", "multiplier"
    },
    "bollinger": {
        "name", "period", "deviation",
        "output", "multiplier"
    },
    "stochastic": {
        "name", "period", "smooth",
        "output", "multiplier"
    }
}

PERIOD_NAMES = {
    "ma", "volume_ma", "rsi", "ema",
    "down_days", "up_days", "volume_down_days",
    "bollinger", "stochastic"
}

COMPARE_OPS = {
    "gt", "gte", "lt", "lte",
    "cross_above", "cross_below"
}


def is_number(value):
    return (
        type(value) in (int, float)
        and math.isfinite(value)
    )


def validate_operand(value, depth=0):
    if depth > 8:
        raise StrategyValidationError(
            "運算式巢狀層數過深"
        )

    if is_number(value):
        return True

    if not isinstance(value, dict):
        raise StrategyValidationError(
            "比較對象必須是數字或運算式"
        )

    if "operation" in value:
        operation = value["operation"]

        if operation in (
            "lag", "rolling_max", "rolling_min"
        ):
            if set(value) != {
                "operation", "source", "period"
            }:
                raise StrategyValidationError(
                    "時間運算格式錯誤"
                )

            period = value["period"]

            if (
                type(period) is not int
                or not 1 <= period <= 250
            ):
                raise StrategyValidationError(
                    "時間運算週期必須是1至250"
                )

            validate_operand(
                value["source"], depth + 1
            )
            return True

        if operation in ("add", "sub", "mul", "div"):
            if set(value) != {
                "operation", "left", "right"
            }:
                raise StrategyValidationError(
                    "數學運算格式錯誤"
                )

            validate_operand(
                value["left"], depth + 1
            )
            validate_operand(
                value["right"], depth + 1
            )

            if (
                operation == "div"
                and is_number(value["right"])
                and value["right"] == 0
            ):
                raise StrategyValidationError(
                    "不可除以零"
                )

            return True

        raise StrategyValidationError(
            f"不支援的運算：{operation}"
        )

    name = value.get("name")

    if name not in INDICATOR_PARAMS:
        raise StrategyValidationError(
            f"不支援的指標：{name}"
        )

    extra = set(value) - INDICATOR_PARAMS[name]

    if extra:
        raise StrategyValidationError(
            f"{name}不支援參數：{sorted(extra)}"
        )

    multiplier = value.get("multiplier", 1)

    if (
        not is_number(multiplier)
        or not 0 < multiplier <= 1000
    ):
        raise StrategyValidationError(
            "指標倍數必須大於0且不超過1000"
        )

    if name in PERIOD_NAMES:
        period = value.get("period")

        if (
            type(period) is not int
            or not 2 <= period <= 250
        ):
            raise StrategyValidationError(
                f"{name}週期必須是2至250"
            )

    if name == "macd":
        fast = value.get("fast", 12)
        slow = value.get("slow", 26)
        signal = value.get("signal", 9)
        output = value.get("output", "line")

        if not all(
            type(x) is int and 2 <= x <= 250
            for x in (fast, slow, signal)
        ):
            raise StrategyValidationError(
                "MACD週期不合法"
            )

        if fast >= slow:
            raise StrategyValidationError(
                "MACD快速週期必須小於慢速週期"
            )

        if output not in (
            "line", "signal", "histogram"
        ):
            raise StrategyValidationError(
                "MACD輸出類型不合法"
            )

    if name == "bollinger":
        deviation = value.get("deviation", 2)
        output = value.get("output", "middle")

        if (
            not is_number(deviation)
            or not 0 < deviation <= 10
        ):
            raise StrategyValidationError(
                "布林通道標準差不合法"
            )

        if output not in (
            "upper", "middle", "lower"
        ):
            raise StrategyValidationError(
                "布林通道輸出類型不合法"
            )

    if name == "stochastic":
        smooth = value.get("smooth", 3)
        output = value.get("output", "k")

        if (
            type(smooth) is not int
            or not 2 <= smooth <= 250
        ):
            raise StrategyValidationError(
                "KD平滑週期不合法"
            )

        if output not in ("k", "d"):
            raise StrategyValidationError(
                "KD輸出類型不合法"
            )

    return True


def validate_condition(node, depth=0):
    if not isinstance(node, dict):
        raise StrategyValidationError(
            "策略條件必須是物件"
        )

    if depth > 8:
        raise StrategyValidationError(
            "條件巢狀層數過深"
        )

    operator = node.get("operator")

    if operator == "consecutive":
        if set(node) != {
            "operator", "period", "condition"
        }:
            raise StrategyValidationError(
                "連續條件格式錯誤"
            )

        period = node["period"]

        if (
            type(period) is not int
            or not 2 <= period <= 250
        ):
            raise StrategyValidationError(
                "連續天數必須是2至250"
            )

        validate_condition(
            node["condition"], depth + 1
        )
        return True

    if operator in ("and", "or"):
        if set(node) != {
            "operator", "conditions"
        }:
            raise StrategyValidationError(
                "AND/OR格式錯誤"
            )

        conditions = node["conditions"]

        if (
            not isinstance(conditions, list)
            or not 1 <= len(conditions) <= 20
        ):
            raise StrategyValidationError(
                "AND/OR子條件數量不合法"
            )

        for condition in conditions:
            validate_condition(
                condition, depth + 1
            )

        return True

    if operator not in COMPARE_OPS:
        raise StrategyValidationError(
            f"不支援的運算子：{operator}"
        )

    if set(node) != {
        "operator", "left", "right"
    }:
        raise StrategyValidationError(
            "比較條件格式錯誤"
        )

    validate_operand(node["left"])
    validate_operand(node["right"])

    return True


def validate_strategy(strategy):
    if not isinstance(strategy, dict):
        raise StrategyValidationError(
            "策略必須是JSON物件"
        )

    required = {
        "symbol", "years", "entry", "exit",
        "stop_loss", "take_profit"
    }

    optional = {
        "max_hold_days",
        "trailing_stop_pct",
        "position_exit"
    }

    missing = required - set(strategy)
    extra = set(strategy) - required - optional

    if missing:
        raise StrategyValidationError(
            f"缺少必要欄位：{sorted(missing)}"
        )

    if extra:
        raise StrategyValidationError(
            f"不支援的策略欄位：{sorted(extra)}"
        )

    symbol = strategy["symbol"]

    if (
        not isinstance(symbol, str)
        or not re.fullmatch(
            r"[A-Z]{1,5}(\.[A-Z])?",
            symbol
        )
    ):
        raise StrategyValidationError(
            "股票代號格式不正確"
        )

    years = strategy["years"]

    if (
        type(years) is not int
        or not 1 <= years <= 10
    ):
        raise StrategyValidationError(
            "回測年數必須是1至10"
        )

    validate_condition(strategy["entry"])
    validate_condition(strategy["exit"])

    for key in ("stop_loss", "take_profit"):
        value = strategy[key]

        if value is not None and (
            not is_number(value)
            or not 0 < value <= 100
        ):
            raise StrategyValidationError(
                f"{key}百分比不合法"
            )

    max_hold_days = strategy.get("max_hold_days")

    if max_hold_days is not None and (
        type(max_hold_days) is not int
        or not 1 <= max_hold_days <= 250
    ):
        raise StrategyValidationError(
            "最大持有期限必須是1至250"
        )

    trailing_stop = strategy.get(
        "trailing_stop_pct"
    )

    if trailing_stop is not None and (
        not is_number(trailing_stop)
        or not 0 < trailing_stop < 100
    ):
        raise StrategyValidationError(
            "追蹤停損必須大於0且小於100%"
        )

    # 新增：通用持倉條件驗證
    position_exit = strategy.get("position_exit")

    if position_exit is not None:
        try:
            validate_position_rule(position_exit)
        except ValueError as error:
            raise StrategyValidationError(
                f"持倉出場條件錯誤：{error}"
            ) from error

    return True
