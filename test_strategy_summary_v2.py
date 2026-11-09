
from strategy_summary_v2 import (
    format_strategy_summary
)

strategy = {
    "symbol": "NVDA",
    "years": 5,
    "entry": {
        "operator": "and",
        "conditions": [
            {
                "operator": "gt",
                "left": {"name": "close"},
                "right": {
                    "operation": "lag",
                    "period": 1,
                    "source": {
                        "operation": "rolling_max",
                        "period": 20,
                        "source": {"name": "high"}
                    }
                }
            },
            {
                "operator": "gt",
                "left": {"name": "volume"},
                "right": {
                    "name": "volume_ma",
                    "period": 20,
                    "multiplier": 1.5
                }
            }
        ]
    },
    "exit": {
        "operator": "lt",
        "left": {"name": "close"},
        "right": {"name": "ma", "period": 10}
    },
    "stop_loss": 5,
    "take_profit": None
}

summary = format_strategy_summary(strategy)

print(summary)

assert "前20個交易日" in summary
assert "20日平均成交量 × 1.5" in summary
assert "10日均線" in summary
assert "停損：5%" in summary

print("\n✅ 中文策略摘要測試成功")
