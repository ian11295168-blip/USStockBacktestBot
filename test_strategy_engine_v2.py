
import numpy as np
import pandas as pd

from strategy_engine import (
    get_indicator,
    evaluate_condition
)

# 建立測試股價資料
np.random.seed(42)

close = pd.Series(
    100 + np.cumsum(np.random.randn(150))
)

df = pd.DataFrame({
    "close": close,
    "high": close + 2,
    "low": close - 2,
    "volume": np.random.randint(
        100000, 1000000, 150
    )
})

# 測試原本指標與新增指標
indicators = [
    {"name": "ma", "period": 20},
    {"name": "rsi", "period": 14},
    {"name": "down_days", "period": 3},
    {"name": "ema", "period": 20},
    {"name": "macd", "output": "line"},
    {"name": "macd", "output": "signal"},
    {"name": "macd", "output": "histogram"},
    {
        "name": "bollinger",
        "period": 20,
        "output": "upper"
    },
    {
        "name": "stochastic",
        "period": 14,
        "output": "k"
    }
]

for indicator in indicators:
    result = get_indicator(df, indicator)

    assert len(result) == len(df)
    assert result.notna().any()

    print("✅ 指標正常：", indicator)

# 測試 MACD 黃金交叉且股價高於 MA20
strategy_condition = {
    "operator": "and",
    "conditions": [
        {
            "operator": "cross_above",
            "left": {
                "name": "macd",
                "output": "line"
            },
            "right": {
                "name": "macd",
                "output": "signal"
            }
        },
        {
            "operator": "gt",
            "left": {"name": "close"},
            "right": {
                "name": "ma",
                "period": 20
            }
        }
    ]
}

signal = evaluate_condition(
    df,
    strategy_condition
)

assert len(signal) == len(df)
assert signal.dtype == bool

print("✅ MACD黃金交叉 + MA20 策略正常")
print("買進訊號次數：", int(signal.sum()))

# 不合法參數必須拒絕
try:
    get_indicator(
        df,
        {"name": "macd", "fast": 30, "slow": 12}
    )
except ValueError:
    print("✅ 不合法MACD參數已拒絕")
else:
    raise AssertionError("未拒絕不合法MACD參數")

print("\n✅ 策略引擎整合測試完成")
