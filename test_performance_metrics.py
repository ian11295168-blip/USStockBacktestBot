
import pandas as pd

from performance_metrics import (
    calculate_performance_metrics,
    format_performance_report
)


# 測試一：資產由10000增加到11000
dates = pd.to_datetime([
    "2025-01-02",
    "2025-04-02",
    "2025-07-02",
    "2025-10-02",
    "2026-01-02"
], utc=True)

df = pd.DataFrame({
    "timestamp": dates,
    "equity": [
        10000, 10200, 10500, 10700, 11000
    ]
})

trades = [
    {"return_pct": 5, "realized_pnl": 500},
    {"return_pct": -2, "realized_pnl": -200},
    {"return_pct": 8, "realized_pnl": 800}
]

metrics = calculate_performance_metrics(
    df, trades
)

assert abs(metrics["total_return"] - 10) < 0.0001
assert 9 < metrics["cagr"] < 11
assert metrics["sharpe_ratio"] is not None
assert metrics["annual_volatility"] > 0
assert abs(metrics["profit_factor"] - 6.5) < 0.0001
assert abs(metrics["win_rate"] - 66.6667) < 0.01

print("✅ CAGR、Sharpe與Profit Factor計算正常")


# 測試二：沒有美元損益，不捏造Profit Factor
trades_without_pnl = [
    {"return_pct": 5},
    {"return_pct": -2}
]

metrics_no_pnl = calculate_performance_metrics(
    df, trades_without_pnl
)

assert metrics_no_pnl["profit_factor"] is None

print("✅ 缺少實現損益時，不產生虛假的Profit Factor")


# 測試三：資產不變時Sharpe未定義
flat_df = pd.DataFrame({
    "timestamp": pd.date_range(
        "2025-01-01", periods=5, freq="B"
    ),
    "equity": [10000] * 5
})

flat = calculate_performance_metrics(flat_df)

assert flat["total_return"] == 0
assert flat["annual_volatility"] == 0
assert flat["sharpe_ratio"] is None

print("✅ 零波動情境正確處理")


# 測試四：資產下降會產生最大回撤
drawdown_df = pd.DataFrame({
    "timestamp": pd.date_range(
        "2025-01-01", periods=4, freq="B"
    ),
    "equity": [10000, 12000, 9000, 11000]
})

down = calculate_performance_metrics(drawdown_df)

assert abs(down["max_drawdown"] + 25) < 0.0001

print("✅ 最大回撤計算正確")


# 測試五：無效資產資料必須拒絕
bad_df = pd.DataFrame({
    "timestamp": pd.date_range(
        "2025-01-01", periods=2, freq="B"
    ),
    "equity": [10000, -100]
})

try:
    calculate_performance_metrics(bad_df)
except ValueError:
    print("✅ 無效資產資料已拒絕")
else:
    raise AssertionError(
        "未拒絕不合法的資產資料"
    )


# 測試六：中文報告
report = format_performance_report(metrics)

assert "CAGR" in report
assert "Sharpe Ratio" in report
assert "Profit Factor" in report

print("✅ 中文績效報告格式正常")


print("\n" + report)
print("\n✅ 進階績效模組測試全部通過")
