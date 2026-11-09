
import math
import pandas as pd

from strategy_engine import get_indicator


def evaluate_expression(df, expression, depth=0):
    """
    將策略運算式轉為時間序列。

    支援：
    1. 固定數值
    2. 原本的技術指標
    3. lag：取得前N個交易日的數值
    4. rolling_max：過去N個交易日最高值
    5. rolling_min：過去N個交易日最低值
    6. add/sub/mul/div：數學運算
    """

    if depth > 10:
        raise ValueError("運算式巢狀層數過深")

    if type(expression) in (int, float):
        if not math.isfinite(expression):
            raise ValueError("數值不可為無限大或NaN")

        return pd.Series(
            float(expression),
            index=df.index
        )

    if not isinstance(expression, dict):
        raise ValueError("運算式格式錯誤")

    # 原本的技術指標
    if "name" in expression:
        result = get_indicator(df, expression)
        multiplier = expression.get("multiplier", 1)
        return result * multiplier
        return get_indicator(df, expression)

    operation = expression.get("operation")

    if operation in ("lag", "rolling_max", "rolling_min"):
        if set(expression) != {
            "operation", "source", "period"
        }:
            raise ValueError("時間運算式欄位錯誤")

        period = expression["period"]

        if (
            type(period) is not int
            or not 1 <= period <= 250
        ):
            raise ValueError("週期必須是1至250的整數")

        source = evaluate_expression(
            df,
            expression["source"],
            depth + 1
        )

        if operation == "lag":
            return source.shift(period)

        if operation == "rolling_max":
            return source.rolling(
                period,
                min_periods=period
            ).max()

        if operation == "rolling_min":
            return source.rolling(
                period,
                min_periods=period
            ).min()

    if operation in ("add", "sub", "mul", "div"):
        if set(expression) != {
            "operation", "left", "right"
        }:
            raise ValueError("數學運算式欄位錯誤")

        left = evaluate_expression(
            df,
            expression["left"],
            depth + 1
        )

        right = evaluate_expression(
            df,
            expression["right"],
            depth + 1
        )

        if operation == "add":
            return left + right

        if operation == "sub":
            return left - right

        if operation == "mul":
            return left * right

        if operation == "div":
            return left.div(
                right.replace(0, float("nan"))
            )

    raise ValueError(
        f"不支援的運算式：{operation}"
    )
