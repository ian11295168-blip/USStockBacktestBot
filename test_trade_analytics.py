
from trade_analytics import (
    analyze_trades,
    format_trade_analytics
)


trades = [
    {
        "return_pct": 10,
        "reason": "策略出場"
    },
    {
        "return_pct": -5,
        "reason": "停損"
    },
    {
        "return_pct": -4,
        "reason": "停損"
    },
    {
        "return_pct": 8,
        "reason": "追蹤停損"
    }
]


result = analyze_trades(
    trades,
    initial_capital=10000
)


# 測試一：基本交易數量
assert result["trade_count"] == 4
assert result["win_count"] == 2
assert result["loss_count"] == 2
assert result["win_rate"] == 50

print("✅ 交易數量與勝率正確")


# 測試二：最大連續虧損
assert result["max_consecutive_losses"] == 2

print("✅ 最大連續虧損計算正確")


# 測試三：依照出場原因分類
reasons = {
    item["reason"]: item
    for item in result["exit_reasons"]
}

assert reasons["停損"]["count"] == 2
assert reasons["策略出場"]["count"] == 1
assert reasons["追蹤停損"]["count"] == 1

print("✅ 出場原因分類正確")


# 測試四：停損的兩筆交易都虧損
assert reasons["停損"]["win_rate"] == 0

assert abs(
    reasons["停損"]["average_return"] + 4.5
) < 0.0001

print("✅ 各出場原因平均報酬正確")


# 測試五：實際美元損益
# 第1筆 +1000：資金變成11000
# 第2筆 -550：資金變成10450
# 第3筆 -418：資金變成10032
# 第4筆 +802.56：資金變成10834.56
assert abs(
    result["net_realized_pnl"] - 834.56
) < 0.01

print("✅ 複利實現損益計算正確")


# 測試六：空交易處理
empty = analyze_trades([])

assert empty["trade_count"] == 0
assert empty["win_rate"] is None

print("✅ 無交易資料正常處理")


# 測試七：報告文字
report = format_trade_analytics(
    result,
    symbol="NVDA"
)

assert "NVDA" in report
assert "最大連續虧損" in report
assert "出場原因分析" in report
assert "追蹤停損" in report

print("✅ Telegram交易分析報告格式正確")


# 測試八：不合法交易應拒絕
try:
    analyze_trades([
        {
            "return_pct": float("nan"),
            "reason": "停損"
        }
    ])
except ValueError:
    print("✅ 不合法交易資料已拒絕")
else:
    raise AssertionError(
        "未拒絕不合法交易資料"
    )


print("\n" + report)
print("\n✅ 交易品質分析測試全部通過")
