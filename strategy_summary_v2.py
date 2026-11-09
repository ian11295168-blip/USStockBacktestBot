
def format_number(value):
    if type(value) in (int, float):
        return f"{value:g}"
    return str(value)


def describe_expression(value):
    """將技術指標與運算式轉換成中文。"""

    if type(value) in (int, float):
        return format_number(value)

    if not isinstance(value, dict):
        return str(value)

    if "name" in value:
        name = value["name"]
        period = value.get("period")
        multiplier = value.get("multiplier", 1)

        labels = {
            "open": "開盤價",
            "high": "最高價",
            "low": "最低價",
            "close": "收盤價",
            "volume": "成交量",
            "ma": f"{period}日均線",
            "volume_ma": f"{period}日平均成交量",
            "ema": f"EMA{period}",
            "rsi": f"RSI{period}",
            "down_days": f"連跌{period}天成立訊號",
            "up_days": f"連漲{period}天成立訊號",
            "volume_down_days": f"連續量縮{period}天成立訊號"
        }

        if name == "macd":
            fast = value.get("fast", 12)
            slow = value.get("slow", 26)
            signal = value.get("signal", 9)
            output = value.get("output", "line")

            output_label = {
                "line": "DIF線",
                "signal": "訊號線",
                "histogram": "柱狀圖"
            }.get(output, output)

            label = (
                f"MACD({fast},{slow},{signal})"
                f"{output_label}"
            )

        elif name == "bollinger":
            deviation = value.get("deviation", 2)
            output = value.get("output", "middle")

            output_label = {
                "upper": "上軌",
                "middle": "中軌",
                "lower": "下軌"
            }.get(output, output)

            label = (
                f"布林通道({period}日,"
                f"{format_number(deviation)}倍標準差)"
                f"{output_label}"
            )

        elif name == "stochastic":
            smooth = value.get("smooth", 3)
            output = value.get("output", "k")

            label = (
                f"KD({period},{smooth})"
                f"{str(output).upper()}線"
            )

        else:
            label = labels.get(name, name)

        if multiplier != 1:
            label += f" × {format_number(multiplier)}"

        return label

    operation = value.get("operation")

    if operation == "lag":
        period = value["period"]
        source = value["source"]

        if (
            period == 1
            and isinstance(source, dict)
            and source.get("operation") in (
                "rolling_max", "rolling_min"
            )
        ):
            rolling_period = source["period"]
            inner_source = source["source"]

            if (
                source["operation"] == "rolling_max"
                and inner_source == {"name": "high"}
            ):
                return f"前{rolling_period}個交易日最高價"

            if (
                source["operation"] == "rolling_min"
                and inner_source == {"name": "low"}
            ):
                return f"前{rolling_period}個交易日最低價"

            inner = describe_expression(inner_source)

            if source["operation"] == "rolling_max":
                return (
                    f"前{rolling_period}個交易日"
                    f"{inner}最高值"
                )

            return (
                f"前{rolling_period}個交易日"
                f"{inner}最低值"
            )

        inner = describe_expression(source)

        if period == 1:
            return f"前一交易日的{inner}"

        return f"{period}個交易日前的{inner}"

    if operation in ("rolling_max", "rolling_min"):
        period = value["period"]
        inner = describe_expression(value["source"])

        if operation == "rolling_max":
            return f"近{period}日{inner}最高值（含當日）"

        return f"近{period}日{inner}最低值（含當日）"

    if operation in ("add", "sub", "mul", "div"):
        symbols = {
            "add": "+",
            "sub": "-",
            "mul": "×",
            "div": "÷"
        }

        left = describe_expression(value["left"])
        right = describe_expression(value["right"])

        return f"({left} {symbols[operation]} {right})"

    return f"未知運算式：{operation}"


def describe_condition_v2(node):
    """描述原本的買進與賣出條件。"""

    operator = node["operator"]

    if operator == "consecutive":
        period = node["period"]
        inner = describe_condition_v2(node["condition"])

        return f"連續{period}個交易日（{inner}）"

    if operator in ("and", "or"):
        separator = " 且 " if operator == "and" else " 或 "

        children = [
            describe_condition_v2(child)
            for child in node["conditions"]
        ]

        return "(" + separator.join(children) + ")"

    operators = {
        "gt": ">",
        "gte": "≥",
        "lt": "<",
        "lte": "≤",
        "cross_above": "向上穿越",
        "cross_below": "向下穿越"
    }

    left = describe_expression(node["left"])
    right = describe_expression(node["right"])

    return (
        f"{left} "
        f"{operators.get(operator, operator)} "
        f"{right}"
    )


def describe_position_condition(node):
    """
    新增：將position_exit轉換成中文。
    支援比較條件以及AND/OR組合。
    """

    if node is None:
        return "未設定"

    if not isinstance(node, dict):
        raise ValueError("持倉條件格式錯誤")

    operator = node["operator"]

    if operator in ("and", "or"):
        separator = (
            " 且 " if operator == "and" else " 或 "
        )

        children = [
            describe_position_condition(child)
            for child in node["conditions"]
        ]

        return "(" + separator.join(children) + ")"

    operators = {
        "gt": ">",
        "gte": "≥",
        "lt": "<",
        "lte": "≤",
        "eq": "="
    }

    metrics = {
        "holding_days": ("已持有交易日數", "天"),
        "return_pct": ("目前持倉報酬率", "%"),
        "peak_return_pct": ("持倉最高收盤報酬率", "%"),
        "pullback_pct": ("從最高收盤價回落", "%")
    }

    if operator not in operators:
        raise ValueError(
            f"不支援的持倉運算子：{operator}"
        )

    metric = node["metric"]

    if metric not in metrics:
        raise ValueError(
            f"不支援的持倉資訊：{metric}"
        )

    label, unit = metrics[metric]
    value = format_number(node["value"])

    return f"{label} {operators[operator]} {value}{unit}"


def format_strategy_summary(strategy):
    """產生Telegram完整策略確認畫面。"""

    symbol = strategy.get("symbol", "未知")
    years = strategy.get("years", "未知")

    entry = describe_condition_v2(
        strategy["entry"]
    )

    exit_rule = describe_condition_v2(
        strategy["exit"]
    )

    stop_loss = strategy.get("stop_loss")
    take_profit = strategy.get("take_profit")
    max_hold_days = strategy.get("max_hold_days")
    trailing_stop_pct = strategy.get("trailing_stop_pct")
    position_exit = strategy.get("position_exit")

    stop_text = (
        "未設定" if stop_loss is None
        else f"{format_number(stop_loss)}%"
    )

    profit_text = (
        "未設定" if take_profit is None
        else f"{format_number(take_profit)}%"
    )

    hold_text = (
        "不限制" if max_hold_days is None
        else f"最多持有{max_hold_days}個交易日"
    )

    trailing_text = (
        "未設定" if trailing_stop_pct is None
        else (
            "從進場後已知最高價回落"
            f"{format_number(trailing_stop_pct)}%出場"
        )
    )

    position_text = describe_position_condition(
        position_exit
    )

    if position_exit is not None:
        position_text += (
            "\n（收盤後確認，"
            "下一交易日開盤出場）"
        )

    return (
        f"📋 {symbol} 策略確認\n\n"
        f"📈 買進條件\n{entry}\n\n"
        f"📉 一般賣出條件\n{exit_rule}\n\n"
        f"🧩 持倉出場條件\n{position_text}\n\n"
        f"🗓 回測期間：{years}年\n"
        f"⏳ 持有期限：{hold_text}\n"
        f"🛑 固定停損：{stop_text}\n"
        f"📉 追蹤停損：{trailing_text}\n"
        f"🎯 停利：{profit_text}\n\n"
        "⚠️ 一般策略與持倉出場訊號"
        "都在收盤確認、隔日開盤執行。\n"
        "固定停損與停利使用日K高低價模擬，"
        "同日同時觸及時採停損優先。\n"
        "追蹤停損的當日新高，"
        "從下一交易日才影響停損線。\n\n"
        "請確認以上條件是否符合你的原意。"
    )
