
import pandas as pd

from yearly_performance import (
    calculate_yearly_performance,
    format_yearly_report
)


# 模擬跨越2024、2025年的回測資料
data = pd.DataFrame({
    "timestamp": pd.to_datetime([
        "2024-01-02",
        "2024-06-03",
        "2024-12-31",
        "2025-01-02",
        "2025-06-02",
        "2025-12-31"
    ], utc=True),

    "equity": [
        10000,
        11000,
        12000,
        12000,
        13000,
        10800
    ],

    "close": [
        100,
        110,
        120,
        125,
        130,
        150
    ]
})


results = calculate_yearly_performance(
    data,
    initial_capital=10000
)

assert len(results) == 2

year2024 = results[0]
year2025 = results[1]


# 測試一：2024策略報酬20%
assert abs(
    year2024["strategy_return"] - 20
) < 0.0001

print("✅ 2024年策略報酬計算正確")


# 測試二：2025策略從12000跌至10800
assert abs(
    year2025["strategy_return"] + 10
) < 0.0001

print("✅ 2025年虧損計算正確")


# 測試三：2025買進持有從120漲到150
assert abs(
    year2025["buy_hold_return"] - 25
) < 0.0001

assert abs(
    year2025["excess_return"] + 35
) < 0.0001

print("✅ 與買進持有的報酬差距正確")


# 測試四：2025年最大回撤
# 13000回落至10800
expected_drawdown = (
    10800 / 13000 - 1
) * 100

assert abs(
    year2025["max_drawdown"]
    - expected_drawdown
) < 0.0001

print("✅ 年度最大回撤計算正確")


# 測試五：不允許負數資產
bad_data = data.copy()
bad_data.loc[0, "equity"] = -100

try:
    calculate_yearly_performance(bad_data)
except ValueError:
    print("✅ 無效資產資料已拒絕")
else:
    raise AssertionError(
        "系統未拒絕負數資產"
    )


# 測試六：Telegram報告
report = format_yearly_report(
    results,
    symbol="NVDA"
)

assert "NVDA" in report
assert "2024年" in report
assert "2025年" in report
assert "報酬差距" in report
assert "年度最大回撤" in report

print("✅ Telegram年度報告格式正常")

print("\n" + report)
print("\n✅ 年度績效分析測試全部通過")
