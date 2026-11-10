"""English-only rendering of existing strategy schema for the Streamlit web UI.

This module does NOT parse, validate, execute, or persist strategies.
The original strategy_summary_v2.py remains unchanged for Telegram.
"""


def format_number(value):
    if type(value) in (int, float):
        return f"{value:g}"
    return str(value)


def describe_expression(value):
    """Render an indicator or arithmetic expression in English."""
    if type(value) in (int, float):
        return format_number(value)
    if not isinstance(value, dict):
        return str(value)

    if "name" in value:
        name = value["name"]
        period = value.get("period")
        multiplier = value.get("multiplier", 1)
        labels = {
            "open": "Open Price",
            "high": "High Price",
            "low": "Low Price",
            "close": "Close Price",
            "volume": "Volume",
            "ma": f"SMA({period})",
            "volume_ma": f"Volume SMA({period})",
            "ema": f"EMA({period})",
            "rsi": f"RSI({period})",
            "down_days": f"{period} Consecutive Down Days Signal",
            "up_days": f"{period} Consecutive Up Days Signal",
            "volume_down_days": f"{period} Consecutive Declining-Volume Days Signal",
        }
        if name == "macd":
            fast = value.get("fast", 12)
            slow = value.get("slow", 26)
            signal = value.get("signal", 9)
            output = value.get("output", "line")
            output_label = {
                "line": "MACD Line (DIF)",
                "signal": "Signal Line",
                "histogram": "Histogram",
            }.get(output, output)
            label = f"MACD({fast},{slow},{signal}) {output_label}"
        elif name == "bollinger":
            deviation = value.get("deviation", 2)
            output = value.get("output", "middle")
            output_label = {
                "upper": "Upper Band",
                "middle": "Middle Band",
                "lower": "Lower Band",
            }.get(output, output)
            label = f"Bollinger Bands({period}, {format_number(deviation)} SD) {output_label}"
        elif name == "stochastic":
            smooth = value.get("smooth", 3)
            output = value.get("output", "k")
            label = f"Stochastic ({period},{smooth}) {str(output).upper()} Line"
        else:
            label = labels.get(name, str(name))
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
            and source.get("operation") in ("rolling_max", "rolling_min")
        ):
            rolling_period = source["period"]
            inner_source = source["source"]
            if source["operation"] == "rolling_max" and inner_source == {"name": "high"}:
                return f"Highest High Over Previous {rolling_period} Trading Days"
            if source["operation"] == "rolling_min" and inner_source == {"name": "low"}:
                return f"Lowest Low Over Previous {rolling_period} Trading Days"
            inner = describe_expression(inner_source)
            extreme = "Maximum" if source["operation"] == "rolling_max" else "Minimum"
            return f"{extreme} of {inner} Over Previous {rolling_period} Trading Days"
        inner = describe_expression(source)
        if period == 1:
            return f"{inner} on Previous Trading Day"
        return f"{inner} {period} Trading Days Ago"

    if operation in ("rolling_max", "rolling_min"):
        period = value["period"]
        inner = describe_expression(value["source"])
        extreme = "Maximum" if operation == "rolling_max" else "Minimum"
        return f"{extreme} of {inner} Over Last {period} Trading Days (Including Today)"

    if operation in ("add", "sub", "mul", "div"):
        symbols = {"add": "+", "sub": "-", "mul": "×", "div": "÷"}
        left = describe_expression(value["left"])
        right = describe_expression(value["right"])
        return f"({left} {symbols[operation]} {right})"

    return f"Unknown Expression: {operation}"


def describe_condition_v2(node):
    """Render entry and regular-exit condition trees."""
    operator = node["operator"]
    if operator == "consecutive":
        period = node["period"]
        inner = describe_condition_v2(node["condition"])
        return f"For {period} Consecutive Trading Days ({inner})"
    if operator in ("and", "or"):
        separator = " AND " if operator == "and" else " OR "
        return "(" + separator.join(describe_condition_v2(c) for c in node["conditions"]) + ")"
    operators = {
        "gt": ">", "gte": "≥", "lt": "<", "lte": "≤",
        "cross_above": "Crosses Above", "cross_below": "Crosses Below",
    }
    left = describe_expression(node["left"])
    right = describe_expression(node["right"])
    return f"{left} {operators.get(operator, operator)} {right}"


def describe_position_condition(node):
    """Render position-specific exit conditions."""
    if node is None:
        return "Not Set"
    if not isinstance(node, dict):
        raise ValueError("Invalid position-exit condition format")
    operator = node["operator"]
    if operator in ("and", "or"):
        separator = " AND " if operator == "and" else " OR "
        return "(" + separator.join(describe_position_condition(c) for c in node["conditions"]) + ")"
    operators = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤", "eq": "="}
    metrics = {
        "holding_days": ("Trading Days Held", " days"),
        "return_pct": ("Current Position Return", "%"),
        "peak_return_pct": ("Peak Close-Based Position Return", "%"),
        "pullback_pct": ("Pullback from Highest Close", "%"),
    }
    if operator not in operators:
        raise ValueError(f"Unsupported position operator: {operator}")
    metric = node["metric"]
    if metric not in metrics:
        raise ValueError(f"Unsupported position metric: {metric}")
    label, unit = metrics[metric]
    value = format_number(node["value"])
    return f"{label} {operators[operator]} {value}{unit}"


def format_strategy_summary(strategy):
    """Render a complete English-language strategy confirmation message."""
    symbol = strategy.get("symbol", "Unknown")
    years = strategy.get("years", "Unknown")
    entry = describe_condition_v2(strategy["entry"])
    exit_rule = describe_condition_v2(strategy["exit"])
    stop_loss = strategy.get("stop_loss")
    take_profit = strategy.get("take_profit")
    max_hold_days = strategy.get("max_hold_days")
    trailing_stop_pct = strategy.get("trailing_stop_pct")
    position_exit = strategy.get("position_exit")

    stop_text = "Not Set" if stop_loss is None else f"{format_number(stop_loss)}%"
    profit_text = "Not Set" if take_profit is None else f"{format_number(take_profit)}%"
    hold_text = (
        "No Limit" if max_hold_days is None
        else f"Up to {max_hold_days} Trading Days"
    )
    trailing_text = (
        "Not Set" if trailing_stop_pct is None
        else f"Exit after a {format_number(trailing_stop_pct)}% pullback from the highest known price since entry"
    )
    position_text = describe_position_condition(position_exit)
    if position_exit is not None:
        position_text += "\n(Confirmed at market close; executed at next trading day's open)"

    return (
        f"📋 {symbol} Strategy Confirmation\n\n"
        f"📈 Entry Conditions\n{entry}\n\n"
        f"📉 Regular Exit Conditions\n{exit_rule}\n\n"
        f"🧩 Position Exit Conditions\n{position_text}\n\n"
        f"🗓 Backtest Period: {years} Years\n"
        f"⏳ Maximum Holding Period: {hold_text}\n"
        f"🛑 Fixed Stop Loss: {stop_text}\n"
        f"📉 Trailing Stop: {trailing_text}\n"
        f"🎯 Take Profit: {profit_text}\n\n"
        "⚠️ Regular strategy signals and position-exit signals are confirmed at market close "
        "and executed at the next trading day's open.\n"
        "Fixed stop-loss and take-profit levels are simulated using daily high/low prices; "
        "if both are reached on the same day, the stop loss takes priority.\n"
        "A new intraday high affects the trailing-stop level starting on the following trading day.\n\n"
        "Please confirm that these conditions match your intended strategy."
    )
