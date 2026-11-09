
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


def run_test(data, buy_days, sell_days=None,
             stop_loss=None, take_profit=None):

    if sell_days is None:
        sell_days = [False] * len(data)

    signals = [
        pd.Series(buy_days),
        pd.Series(sell_days)
    ]

    strategy = {
        "symbol": "TEST",
        "years": 1,
        "entry": {"operator": "gt", "left": 1, "right": 0},
        "exit": {"operator": "lt", "left": 0, "right": 1},
        "stop_loss": stop_loss,
        "take_profit": take_profit
    }

    with patch.object(
        ub, "get_stock_data", return_value=data
    ), patch.object(
        ub, "evaluate_condition", side_effect=signals
    ):
        return ub.run_universal_backtest(strategy)


# 測試一：昨天有買進訊號，今天開盤才買
data = make_data([
    (100, 102, 99, 101),
    (110, 112, 109, 111),
    (120, 122, 119, 121)
])

df, trades, stats = run_test(
    data,
    buy_days=[True, False, False]
)

expected_buy = 110 * (1 + ub.SLIPPAGE)

assert stats["open_position"] is True
assert stats["trade_count"] == 0

expected_shares = (
    ub.INITIAL_CAPITAL
    / (expected_buy * (1 + ub.FEE_RATE))
)
expected_equity = expected_shares * 121

assert abs(
    stats["final_equity"] - expected_equity
) < 0.01

print("✅ 測試一：買進使用下一交易日開盤價")


# 測試二：跳空跌破停損價，應按開盤成交
data = make_data([
    (100, 101, 99, 100),
    (100, 101, 99, 100),
    (90, 92, 89, 91),
    (92, 93, 91, 92)
])

df, trades, stats = run_test(
    data,
    buy_days=[True, False, False, False],
    stop_loss=5
)

assert len(trades) == 1

trade = trades[0]

assert trade["reason"] == "跳空停損"

expected_sell = 90 * (1 - ub.SLIPPAGE)

assert abs(
    trade["sell_price"] - expected_sell
) < 0.01

print("✅ 測試二：跳空停損使用開盤價格")


# 測試三：同一天觸及停損和停利
data = make_data([
    (100, 101, 99, 100),
    (100, 110, 94, 100),
    (100, 101, 99, 100)
])

df, trades, stats = run_test(
    data,
    buy_days=[True, False, False],
    stop_loss=5,
    take_profit=5
)

assert len(trades) == 1

assert trades[0]["reason"] == "停損"

print("✅ 測試三：同日觸及停損停利，採保守假設")


print("\n✅ 三項回測準確性測試全部通過")
