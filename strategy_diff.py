
import json

from strategy_summary_v2 import (
    describe_condition_v2,
    describe_position_condition,
    format_number
)


FIELDS = [
    ("symbol", "股票"),
    ("years", "回測年數"),
    ("entry", "買進條件"),
    ("exit", "一般賣出條件"),
    ("position_exit", "持倉出場條件"),
    ("stop_loss", "固定停損"),
    ("take_profit", "停利"),
    ("max_hold_days", "最大持有期限"),
    ("trailing_stop_pct", "追蹤停損")
]


def normalize(value):
    """比較JSON結構，不受字典欄位順序影響。"""

    if isinstance(value, dict):
        return {
            key: normalize(item)
            for key, item in sorted(value.items())
        }

    if isinstance(value, list):
        return [
            normalize(item)
            for item in value
        ]

    return value


def readable(value):
    if value is None:
        return "未設定"

    if isinstance(value, (dict, list)):
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":")
        )

    return str(value)


def format_field(key, value):
    """將修改前後的設定格式化為中文。"""

    if key in ("entry", "exit"):
        if value is None:
            return "未設定"

        try:
            return describe_condition_v2(value)
        except (KeyError, TypeError, ValueError):
            return readable(value)

    if key == "position_exit":
        if value is None:
            return "未設定持倉出場條件"

        try:
            return (
                describe_position_condition(value)
                + "（收盤確認，隔日開盤出場）"
            )
        except (KeyError, TypeError, ValueError):
            return readable(value)

    if key == "max_hold_days":
        if value is None:
            return "不限制持有天數"

        return f"最多持有{value}個交易日"

    if key == "trailing_stop_pct":
        if value is None:
            return "未設定追蹤停損"

        return (
            f"最高價回落"
            f"{format_number(value)}%出場"
        )

    if key in ("stop_loss", "take_profit"):
        if value is None:
            return "未設定"

        return f"{format_number(value)}%"

    if key == "years":
        if value is None:
            return "未設定"

        return f"{value}年"

    return readable(value)


def compare_strategies(old, new):
    """找出策略之間所有已知欄位的變化。"""

    if not isinstance(old, dict):
        raise ValueError("舊策略必須是JSON物件")

    if not isinstance(new, dict):
        raise ValueError("新策略必須是JSON物件")

    changes = []

    for key, label in FIELDS:
        before = old.get(key)
        after = new.get(key)

        if normalize(before) == normalize(after):
            continue

        changes.append({
            "key": key,
            "field": label,
            "before": format_field(key, before),
            "after": format_field(key, after)
        })

    return changes


def format_strategy_diff(old, new):
    """Telegram顯示的策略修改比較。"""

    changes = compare_strategies(old, new)

    if not changes:
        return "🔎 策略比較：沒有發現設定變化。"

    lines = [
        "🔎 AI策略修改比較",
        ""
    ]

    for item in changes:
        lines.extend([
            f"📝 {item['field']}",
            f"原本：{item['before']}",
            f"修改：{item['after']}",
            ""
        ])

    lines.append(
        "⚠️ 請確認以上修改符合你的要求。"
    )

    return "\n".join(lines)


if __name__ == "__main__":
    original = {
        "symbol": "NVDA",
        "years": 5,
        "entry": {
            "operator": "lt",
            "left": {"name": "rsi", "period": 14},
            "right": 30
        },
        "exit": {
            "operator": "gt",
            "left": {"name": "rsi", "period": 14},
            "right": 70
        },
        "stop_loss": 5,
        "take_profit": None,
        "max_hold_days": None,
        "trailing_stop_pct": 8,
        "position_exit": {
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
    }

    modified = {
        **original,
        "position_exit": {
            "operator": "and",
            "conditions": [
                {
                    "operator": "gte",
                    "metric": "holding_days",
                    "value": 7
                },
                {
                    "operator": "lt",
                    "metric": "return_pct",
                    "value": 3
                }
            ]
        }
    }

    print(
        format_strategy_diff(
            original,
            modified
        )
    )
