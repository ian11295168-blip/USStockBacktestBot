
import pandas as pd

from strategy_engine import evaluate_condition


# 建立容易人工核對的測試資料
df = pd.DataFrame({
    "open": [9, 10, 11, 12, 13, 14],
    "high": [10, 12, 15, 14, 17, 20],
    "low": [8, 9, 10, 11, 12, 13],
    "close": [9, 11, 14, 13, 16, 19],
    "volume": [100, 120, 150, 130, 180, 200]
})


# 條件一：收盤價高於前3個交易日最高價
breakout_condition = {
    "operator": "gt",
    "left": {"name": "close"},
    "right": {
        "operation": "lag",
        "source": {
            "operation": "rolling_max",
            "source": {"name": "high"},
            "period": 3
        },
        "period": 1
    }
}

breakout_signal = evaluate_condition(
    df, breakout_condition
)

assert breakout_signal.tolist() == [
    False, False, False,
    False, True, True
]

print("✅ 突破前3日最高價條件正確")


# 條件二：成交量大於3日均量1.1倍
volume_condition = {
    "operator": "gt",
    "left": {"name": "volume"},
    "right": {
        "operation": "mul",
        "left": {
            "name": "volume_ma",
            "period": 3
        },
        "right": 1.1
    }
}

volume_signal = evaluate_condition(
    df, volume_condition
)

assert volume_signal.tolist() == [
    False, False, True,
    False, True, True
]

print("✅ 成交量條件正確")


# 條件三：兩個條件同時成立才買進
entry_condition = {
    "operator": "and",
    "conditions": [
        breakout_condition,
        volume_condition
    ]
}

entry_signal = evaluate_condition(
    df, entry_condition
)

assert entry_signal.tolist() == [
    False, False, False,
    False, True, True
]

print("✅ AND組合買進條件正確")


# 額外檢查：不能使用未來資料
previous_close_condition = {
    "operator": "gt",
    "left": {"name": "close"},
    "right": {
        "operation": "lag",
        "source": {"name": "close"},
        "period": 1
    }
}

result = evaluate_condition(
    df, previous_close_condition
)

assert result.tolist() == [
    False, True, True,
    False, True, True
]

print("✅ 昨日收盤價比較正確")


print("\n✅ 通用時間條件整合測試全部通過")
