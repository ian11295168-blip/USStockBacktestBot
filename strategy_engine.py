
import math
import pandas as pd

from indicator_engine import calculate_indicator


def get_indicator(df, indicator):
    name = indicator["name"].lower()
    period = indicator.get("period")

    # 基本股價與成交量
    if name in ("open", "high", "low", "close", "volume"):
        return df[name].astype(float)

    # 需要週期的指標
    period_indicators = {
        "ma", "volume_ma", "rsi",
        "down_days", "up_days", "volume_down_days",
        "ema", "bollinger", "stochastic"
    }

    if name in period_indicators:
        if (
            type(period) is not int
            or not 2 <= period <= 250
        ):
            raise ValueError(
                f"{name} 週期必須是2至250的整數"
            )

    # 簡單移動平均
    if name == "ma":
        return df["close"].rolling(period).mean()

    # 成交量移動平均
    if name == "volume_ma":
        return df["volume"].rolling(period).mean()

    # 連續下跌
    if name == "down_days":
        falling = df["close"].diff() < 0

        return (
            falling.rolling(period, min_periods=period)
            .sum()
            .eq(period)
            .astype(float)
        )

    # 連續上漲
    if name == "up_days":
        rising = df["close"].diff() > 0

        return (
            rising.rolling(period, min_periods=period)
            .sum()
            .eq(period)
            .astype(float)
        )

    # 成交量連續下降
    if name == "volume_down_days":
        falling = df["volume"].diff() < 0

        return (
            falling.rolling(period, min_periods=period)
            .sum()
            .eq(period)
            .astype(float)
        )

    # RSI（保留原本的計算方式）
    if name == "rsi":
        close = df["close"].astype(float)
        delta = close.diff()

        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)

        avg_gain = gain.ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period
        ).mean()

        avg_loss = loss.ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period
        ).mean()

        rs = avg_gain / avg_loss.replace(
            0, float("nan")
        )

        rsi = 100 - 100 / (1 + rs)

        rsi = rsi.mask(
            (avg_loss == 0) & (avg_gain > 0),
            100
        )

        rsi = rsi.mask(
            (avg_gain == 0) & (avg_loss > 0),
            0
        )

        return rsi

    # 通用技術指標
    if name in (
        "ema", "macd", "bollinger", "stochastic"
    ):
        allowed_params = {
            "ema": {
                "name", "period", "multiplier"
            },
            "macd": {
                "name", "fast", "slow", "signal",
                "output", "multiplier"
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

        extra = (
            set(indicator) - allowed_params[name]
        )

        if extra:
            raise ValueError(
                f"{name} 不支援參數：{sorted(extra)}"
            )

        params = {}

        if name == "macd":
            fast = indicator.get("fast", 12)
            slow = indicator.get("slow", 26)
            signal = indicator.get("signal", 9)
            output = indicator.get("output", "line")

            if not all(
                type(x) is int and 2 <= x <= 250
                for x in (fast, slow, signal)
            ):
                raise ValueError(
                    "MACD週期參數不合法"
                )

            if fast >= slow:
                raise ValueError(
                    "MACD快速週期必須小於慢速週期"
                )

            if output not in (
                "line", "signal", "histogram"
            ):
                raise ValueError(
                    "MACD輸出類型不合法"
                )

            params = {
                "fast": fast,
                "slow": slow,
                "signal": signal,
                "output": output
            }

        elif name == "bollinger":
            deviation = indicator.get(
                "deviation", 2
            )
            output = indicator.get(
                "output", "middle"
            )

            if (
                type(deviation) not in (int, float)
                or not math.isfinite(deviation)
                or not 0 < deviation <= 10
            ):
                raise ValueError(
                    "布林通道標準差不合法"
                )

            if output not in (
                "upper", "middle", "lower"
            ):
                raise ValueError(
                    "布林通道輸出類型不合法"
                )

            params = {
                "deviation": deviation,
                "output": output
            }

        elif name == "stochastic":
            smooth = indicator.get("smooth", 3)
            output = indicator.get("output", "k")

            if (
                type(smooth) is not int
                or not 2 <= smooth <= 250
            ):
                raise ValueError(
                    "KD平滑週期不合法"
                )

            if output not in ("k", "d"):
                raise ValueError(
                    "KD輸出類型不合法"
                )

            params = {
                "smooth": smooth,
                "output": output
            }

        return calculate_indicator(
            df,
            name,
            period=period if period is not None else 14,
            **params
        )

    raise ValueError(
        f"不支援的指標：{name}"
    )


def get_operand(df, value):
    # 時間序列與數學運算
    if (
        isinstance(value, dict)
        and "operation" in value
    ):
        from series_expression import evaluate_expression

        return evaluate_expression(df, value)

    # 技術指標
    if isinstance(value, dict):
        if "name" not in value:
            raise ValueError("指標缺少 name")

        result = get_indicator(df, value)
        multiplier = value.get(
            "multiplier", 1
        )

        if (
            type(multiplier) not in (int, float)
            or not math.isfinite(multiplier)
            or not 0 < multiplier <= 1000
        ):
            raise ValueError(
                "指標倍數必須大於0且不超過1000"
            )

        return result * multiplier

    # 固定數值
    if (
        type(value) in (int, float)
        and math.isfinite(value)
    ):
        return pd.Series(
            float(value),
            index=df.index
        )

    raise ValueError(
        "不支援的比較數值"
    )


def evaluate_condition(df, condition):
    if not isinstance(condition, dict):
        raise ValueError(
            "策略條件必須是物件"
        )

    operator = condition.get("operator")

    # 新增：任意條件連續N個交易日成立
    if operator == "consecutive":
        if set(condition) != {
            "operator", "period", "condition"
        }:
            raise ValueError(
                "連續條件格式錯誤"
            )

        period = condition["period"]

        if (
            type(period) is not int
            or not 2 <= period <= 250
        ):
            raise ValueError(
                "連續天數必須是2至250的整數"
            )

        child_signal = evaluate_condition(
            df,
            condition["condition"]
        )

        return (
            child_signal.astype(int)
            .rolling(
                period,
                min_periods=period
            )
            .sum()
            .eq(period)
            .fillna(False)
        )

    # AND / OR 條件
    if operator in ("and", "or"):
        conditions = condition.get(
            "conditions", []
        )

        if (
            not isinstance(conditions, list)
            or not conditions
        ):
            raise ValueError(
                "AND/OR 必須有至少一個條件"
            )

        results = [
            evaluate_condition(df, item)
            for item in conditions
        ]

        combined = results[0]

        for result in results[1:]:
            if operator == "and":
                combined = combined & result
            else:
                combined = combined | result

        return combined.fillna(False)

    # 比較運算子
    if operator not in (
        "gt", "gte", "lt", "lte",
        "cross_above", "cross_below"
    ):
        raise ValueError(
            f"不支援的運算子：{operator}"
        )

    left = get_operand(
        df, condition["left"]
    )
    right = get_operand(
        df, condition["right"]
    )

    valid = (
        left.notna()
        & right.notna()
    )

    if operator == "gt":
        signal = left > right

    elif operator == "gte":
        signal = left >= right

    elif operator == "lt":
        signal = left < right

    elif operator == "lte":
        signal = left <= right

    elif operator == "cross_above":
        signal = (
            (left > right)
            & (left.shift(1) <= right.shift(1))
        )

        valid = (
            valid
            & left.shift(1).notna()
            & right.shift(1).notna()
        )

    else:
        signal = (
            (left < right)
            & (left.shift(1) >= right.shift(1))
        )

        valid = (
            valid
            & left.shift(1).notna()
            & right.shift(1).notna()
        )

    return (
        signal & valid
    ).fillna(False)
