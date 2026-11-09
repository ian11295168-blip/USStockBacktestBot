
import pandas as pd

from out_of_sample import (
    analyze_out_of_sample,
    format_oos_report
)


dates = pd.date_range(
    "2025-01-02",
    periods=10,
    freq="B",
    tz="UTC"
)

data = pd.DataFrame({
    "timestamp": dates,
    "equity": [
        10000,
        10100,
        10200,
        10400,
        10600,
        10800,
        11000,
        9900,
        10100,
        10500
    ],
    "close": [
        100,
        101,
        102,
        104,
        106,
        108,
        110,
        105,
        107,
        115
    ]
})


result = analyze_out_of_sample(
    data,
    train_ratio=0.70,
    initial_capital=10000
)

train = result["train"]
test = result["test"]


# 測試一：70/30時間切分
assert train["trading_days"] == 7
assert test["trading_days"] == 3

assert train["end_date"] < test["start_date"]

print("✅ 70/30時間切分正確")


# 測試二：訓練期10000變11000
assert abs(
    train["strategy_return"] - 10
) < 0.0001

print("✅ 樣本內報酬計算正確")


# 測試三：測試期以11000作為起點
expected_test_return = (
    10500 / 11000 - 1
) * 100

assert abs(
    test["strategy_return"]
    - expected_test_return
) < 0.0001

assert test["starting_equity"] == 11000

print("✅ 測試期資產基準正確")


# 測試四：測試期買進持有以110作基準
expected_buy_hold = (
    115 / 110 - 1
) * 100

assert abs(
    test["buy_hold_return"]
    - expected_buy_hold
) < 0.0001

print("✅ 樣本外買進持有基準正確")


# 測試五：測試期最大回撤10%
assert abs(
    test["max_drawdown"] + 10
) < 0.0001

print("✅ 樣本外最大回撤正確")


# 測試六：原始資料未被修改
assert data.iloc[0]["equity"] == 10000
assert data.iloc[-1]["equity"] == 10500

print("✅ 不會改動原始回測資料")


# 測試七：不合法比例應拒絕
try:
    analyze_out_of_sample(
        data,
        train_ratio=0.95
    )
except ValueError:
    print("✅ 不合法切分比例已拒絕")
else:
    raise AssertionError(
        "未拒絕不合法切分比例"
    )


# 測試八：中文報告
report = format_oos_report(
    result,
    symbol="NVDA"
)

assert "NVDA" in report
assert "樣本內" in report
assert "樣本外" in report
assert "最大回撤" in report

print("✅ 中文分段績效報告正確")


print("\n" + report)
print("\n✅ 樣本內／外分析測試全部通過")
