
import pandas as pd

from series_expression import evaluate_expression


df = pd.DataFrame({
    "open": [9, 10, 11, 12, 13, 14],
    "high": [10, 12, 15, 14, 17, 20],
    "low": [8, 9, 10, 11, 12, 13],
    "close": [9, 11, 14, 13, 16, 19],
    "volume": [100, 120, 150, 130, 180, 200]
})

# 昨天最高價
yesterday_high = {
    "operation": "lag",
    "source": {"name": "high"},
    "period": 1
}

result = evaluate_expression(df, yesterday_high)

assert pd.isna(result.iloc[0])
assert result.iloc[1] == 10
assert result.iloc[2] == 12

print("✅ 昨天最高價計算正確")


# 前3個交易日最高價（不包含今天）
previous_3day_high = {
    "operation": "lag",
    "source": {
        "operation": "rolling_max",
        "source": {"name": "high"},
        "period": 3
    },
    "period": 1
}

result = evaluate_expression(
    df,
    previous_3day_high
)

assert pd.isna(result.iloc[2])
assert result.iloc[3] == 15
assert result.iloc[4] == 15
assert result.iloc[5] == 17

print("✅ 前3日最高價計算正確")


# 計算收盤價是否突破前3日最高價
close = evaluate_expression(
    df,
    {"name": "close"}
)

breakout = close > result

assert breakout.tolist() == [
    False, False, False,
    False, True, True
]

print("✅ 突破前3日最高價訊號正確")


# 收盤價乘以1.5
multiplied = {
    "operation": "mul",
    "left": {"name": "close"},
    "right": 1.5
}

result = evaluate_expression(df, multiplied)

assert result.iloc[0] == 13.5
assert result.iloc[5] == 28.5

print("✅ 數學運算正確")


print("\n✅ 時間序列運算測試全部完成")
