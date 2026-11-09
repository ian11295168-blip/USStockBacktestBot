
"""A/B策略對照回測測試。"""

from copy import deepcopy
from unittest.mock import patch

import pandas as pd

import universal_backtest as backtest
import strategy_ab_comparison as ab


# 模擬同一檔股票的歷史股價
dates = pd.date_range(
    end=pd.Timestamp.now(tz="UTC").normalize(),
    periods=6,
    freq="B",
    name="timestamp"
)

data = pd.DataFrame(
    [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (110.5, 117, 108, 115),
        (120, 122, 118, 120),
        (105, 107, 103, 105),
        (90, 92, 88, 90),
    ],
    columns=[
        "open", "high", "low", "close"
    ],
    index=dates
)

data["volume"] = 100000


# 策略A：沒有停利
strategy_a = {
    "symbol": "NVDA",
    "years": 1,
    "entry": {
        "operator": "gt",
        "left": {"name": "close"},
        "right": 0
    },
    "exit": {
        "operator": "lt",
        "left": {"name": "close"},
        "right": 0
    },
    "stop_loss": None,
    "take_profit": None,
    "max_hold_days": None,
    "trailing_stop_pct": None,
    "position_exit": None,
}

# 策略B：加入10%固定停利
strategy_b = deepcopy(strategy_a)
strategy_b["take_profit"] = 10


download_count = 0


def fake_download(symbol, years):
    global download_count

    download_count += 1

    assert symbol == "NVDA"
    assert years == 1

    return data.copy(deep=True)


def fake_condition(df, condition):
    # 僅第一天產生買進訊號；
    # 一般賣出訊號全程不成立
    if condition == strategy_a["entry"]:
        return pd.Series(
            [True] + [False] * (len(df) - 1),
            index=df.index
        )

    return pd.Series(
        [False] * len(df),
        index=df.index
    )


with patch.object(
    ab,
    "get_stock_data",
    side_effect=fake_download
), patch.object(
    backtest,
    "evaluate_condition",
    side_effect=fake_condition
):
    result = ab.compare_strategies(
        strategy_a,
        strategy_b
    )


# 測試一：歷史資料只下載一次
assert download_count == 1

print("✅ A/B使用同一份歷史資料")


# 測試二：兩個策略使用相同交易日期
assert result["df_a"]["timestamp"].equals(
    result["df_b"]["timestamp"]
)

print("✅ A/B回測日期一致")


# 測試三：A沒有完成交易，B觸發固定停利
assert result["stats_a"]["trade_count"] == 0
assert result["stats_b"]["trade_count"] == 1

assert result["trades_b"][0]["reason"] in (
    "停利",
    "跳空停利"
)

print("✅ 不同停利設定產生不同交易結果")


# 測試四：B在這組模擬資料中績效較佳
assert (
    result["stats_b"]["total_return"]
    > result["stats_a"]["total_return"]
)

assert result["differences"]["total_return"] > 0

print("✅ 策略總報酬差異計算正確")


# 測試五：買進持有的比較基準一致
assert (
    result["stats_a"]["buy_hold_return"]
    == result["stats_b"]["buy_hold_return"]
)

print("✅ Buy & Hold基準一致")


# 測試六：原始策略沒有被修改
assert strategy_a["take_profit"] is None
assert strategy_b["take_profit"] == 10

print("✅ 原始策略設定保持不變")


# 測試七：報告正常顯示
report = ab.format_ab_report(result)

assert "策略A/B比較" in report
assert "策略 A" in report
assert "策略 B" in report
assert "Sharpe" in report
assert "最大回撤" in report

print("✅ A/B中文績效報告產生成功")


# 測試八：不同股票不得比較
invalid = deepcopy(strategy_b)
invalid["symbol"] = "AAPL"

try:
    ab.compare_strategies(
        strategy_a,
        invalid
    )
except ValueError:
    print("✅ 不同股票的比較已拒絕")
else:
    raise AssertionError(
        "未拒絕不同股票的比較"
    )


# 測試九：不同回測年數不得比較
invalid = deepcopy(strategy_b)
invalid["years"] = 2

try:
    ab.compare_strategies(
        strategy_a,
        invalid
    )
except ValueError:
    print("✅ 不同回測年數的比較已拒絕")
else:
    raise AssertionError(
        "未拒絕不同回測年數"
    )


print("\n" + report)
print("\n✅ A/B策略對照測試全部通過")
