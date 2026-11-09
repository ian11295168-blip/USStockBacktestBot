
import pandas as pd
from unittest.mock import patch
import universal_backtest as ub


def make_data(rows):
    dates = pd.date_range(
        end=pd.Timestamp.now(tz="UTC").normalize(),
        periods=len(rows),
        freq="B",
        name="timestamp"
    )

    return pd.DataFrame(
        rows,
        columns=["open", "high", "low", "close"],
        index=dates
    ).assign(volume=100000)


def run_test(rows, buys, sells, stop=None, target=None):
    data = make_data(rows)

    strategy = {
        "symbol": "TEST",
        "years": 1,
        "entry": {"operator": "gt", "left": 1, "right": 0},
        "exit": {"operator": "lt", "left": 0, "right": 1},
        "stop_loss": stop,
        "take_profit": target
    }

    signals = [
        pd.Series(buys),
        pd.Series(sells)
    ]

    with patch.object(
        ub, "get_stock_data", return_value=data
    ), patch.object(
        ub, "evaluate_condition", side_effect=signals
    ):
        return ub.run_universal_backtest(strategy)


# 測試一：賣出訊號在隔日開盤執行
df, trades, stats = run_test(
    [
        (100, 101, 99, 100),
        (110, 112, 109, 111),
        (120, 122, 119, 121),
        (130, 132, 129, 131)
    ],
    buys=[True, False, False, False],
    sells=[False, True, False, False]
)

assert len(trades) == 1

trade = trades[0]

assert abs(
    trade["buy_price"] - 110 * (1 + ub.SLIPPAGE)
) < 0.01

assert abs(
    trade["sell_price"] - 120 * (1 - ub.SLIPPAGE)
) < 0.01

assert trade["reason"] == "策略出場"

print("✅ 賣出訊號在下一交易日開盤執行")


# 測試二：手續費與滑價都有計入
gross_buy = trade["buy_price"] * (1 + ub.FEE_RATE)
net_sell = trade["sell_price"] * (1 - ub.FEE_RATE)

expected_return = (
    net_sell / gross_buy - 1
) * 100

assert abs(
    trade["return_pct"] - expected_return
) < 0.0001

print("✅ 交易成本計算正確")


# 測試三：買進當天觸及停損
df, trades, stats = run_test(
    [
        (100, 101, 99, 100),
        (100, 102, 94, 100),
        (101, 102, 100, 101)
    ],
    buys=[True, False, False],
    sells=[False, False, False],
    stop=5
)

assert len(trades) == 1
assert trades[0]["reason"] == "停損"

assert (
    trades[0]["buy_date"]
    == trades[0]["sell_date"]
)

print("✅ 買進當天觸及停損可正確出場")

print("\n✅ 第二階段回測準確性測試全部通過")
