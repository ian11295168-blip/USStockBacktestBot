
import pandas as pd
from unittest.mock import patch

import universal_backtest as ub


def run_test(
    prices,
    buy_days,
    sell_days=None,
    max_hold_days=None,
    stop_loss=None
):
    if sell_days is None:
        sell_days = [False] * len(prices)

    dates = pd.date_range(
        end=pd.Timestamp.now(tz="UTC").normalize(),
        periods=len(prices),
        freq="B",
        name="timestamp"
    )

    df = pd.DataFrame(
        prices,
        columns=["open", "high", "low", "close"],
        index=dates
    )

    df["volume"] = 100000

    strategy = {
        "symbol": "TEST",
        "years": 1,
        "entry": {
            "operator": "gt",
            "left": 1,
            "right": 0
        },
        "exit": {
            "operator": "lt",
            "left": 0,
            "right": 1
        },
        "stop_loss": stop_loss,
        "take_profit": None,
        "max_hold_days": max_hold_days
    }

    signals = [
        pd.Series(buy_days),
        pd.Series(sell_days)
    ]

    with patch.object(
        ub,
        "get_stock_data",
        return_value=df
    ), patch.object(
        ub,
        "evaluate_condition",
        side_effect=signals
    ):
        return ub.run_universal_backtest(strategy)


# 20個交易日的固定價格
prices = [
    (100, 101, 99, 100)
    for _ in range(20)
]

buy_days = [
    True
] + [
    False
] * 19


# 測試一：持有10天自動賣出
df, trades, stats = run_test(
    prices,
    buy_days,
    max_hold_days=10
)

assert len(trades) == 1
assert trades[0]["reason"] == "持有期限"

# 第2個交易日買進
assert trades[0]["buy_date"] == df.iloc[1]["timestamp"]

# 完整持有10個交易日後
# 第12個交易日開盤賣出
assert trades[0]["sell_date"] == df.iloc[11]["timestamp"]

print("✅ 持有10個交易日後自動出場")


# 測試二：策略訊號提前賣出
sell_days = [
    False
] * 5 + [
    True
] + [
    False
] * 14

df, trades, stats = run_test(
    prices,
    buy_days,
    sell_days=sell_days,
    max_hold_days=10
)

assert len(trades) == 1
assert trades[0]["reason"] == "策略出場"
assert trades[0]["sell_date"] == df.iloc[6]["timestamp"]

print("✅ 策略訊號可提前出場")


# 測試三：停損優先於持有期限
stop_prices = list(prices)

stop_prices[3] = (
    100, 101, 90, 95
)

df, trades, stats = run_test(
    stop_prices,
    buy_days,
    max_hold_days=10,
    stop_loss=5
)

assert len(trades) == 1
assert trades[0]["reason"] == "停損"
assert trades[0]["sell_date"] == df.iloc[3]["timestamp"]

print("✅ 停損可提前出場")


# 測試四：不設定持有期限
df, trades, stats = run_test(
    prices,
    buy_days,
    max_hold_days=None
)

assert len(trades) == 0
assert stats["open_position"] is True

print("✅ 不設定持有期限時保留原本行為")


# 測試五：不合法的持有天數
try:
    run_test(
        prices,
        buy_days,
        max_hold_days=-1
    )
except ValueError:
    print("✅ 不合法持有天數已拒絕")
else:
    raise AssertionError(
        "系統沒有拒絕不合法持有天數"
    )


print("\n✅ 最大持有天數測試全部通過")
