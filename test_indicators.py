
import pandas as pd
import numpy as np

from indicator_engine import calculate_indicator

np.random.seed(42)

df = pd.DataFrame({
    "close": 100 + np.cumsum(np.random.randn(100)),
    "high": 102 + np.cumsum(np.random.randn(100)),
    "low": 98 + np.cumsum(np.random.randn(100)),
    "volume": np.random.randint(
        100000, 1000000, 100
    )
})

indicators = [
    ("ma", {"period": 20}),
    ("ema", {"period": 20}),
    ("rsi", {"period": 14}),
    ("macd", {"output": "line"}),
    ("macd", {"output": "signal"}),
    ("macd", {"output": "histogram"}),
    ("bollinger", {"period": 20, "output": "upper"}),
    ("bollinger", {"period": 20, "output": "lower"}),
    ("stochastic", {"period": 14, "output": "k"})
]

for name, params in indicators:
    result = calculate_indicator(
        df, name, **params
    )

    assert len(result) == len(df)
    assert result.notna().any()

    print(f"✅ {name} {params}：正常")

print("\n通用指標測試完成")
