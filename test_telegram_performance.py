
import pandas as pd

from telegram_performance import (
    add_realized_pnl,
    build_telegram_performance_report
)


# 建立測試用的每日資產資料
dates = pd.date_range(
    start="2025-01-02",
    periods=252,
    freq="B",
    tz="UTC"
)

equity = [
    10000 + i * 4
    for i in range(252)
]

df = pd.DataFrame({
    "timestamp": dates,
    "equity": equity
})


# 模擬三筆已完成的交易
trades = [
    {"return_pct": 10},
    {"return_pct": -5},
    {"return_pct": 8}
]

stats = {
    "symbol": "NVDA",
    "buy_hold_return": 25.0
}


# 測試一：還原美元損益
completed = add_realized_pnl(trades)

assert abs(
    completed[0]["realized_pnl"] - 1000
) < 0.01

assert abs(
    completed[1]["realized_pnl"] + 550
) < 0.01

assert abs(
    completed[2]["realized_pnl"] - 836
) < 0.01

print("✅ 每筆交易美元損益計算正確")


# 測試二：原始交易紀錄不會被修改
assert "realized_pnl" not in trades[0]

print("✅ 不會破壞原本交易紀錄")


# 測試三：進階績效報告
report, metrics, completed = (
    build_telegram_performance_report(
        df, trades, stats
    )
)

assert "NVDA" in report
assert "CAGR" in report
assert "Sharpe Ratio" in report
assert "Profit Factor" in report
assert "買進持有" in report

print("✅ Telegram進階報告產生成功")


# 測試四：Profit Factor
# 總獲利=1000+836，總虧損=550
expected_pf = 1836 / 550

assert abs(
    metrics["profit_factor"] - expected_pf
) < 0.0001

print("✅ Profit Factor計算正確")


# 測試五：空交易也可以產生報告
empty_report, empty_metrics, _ = (
    build_telegram_performance_report(
        df, [], stats
    )
)

assert empty_metrics["trade_count"] == 0
assert empty_metrics["profit_factor"] is None

print("✅ 沒有交易時仍可產生報告")


print("\n" + report)
print("\n✅ Telegram績效整合測試全部通過")
