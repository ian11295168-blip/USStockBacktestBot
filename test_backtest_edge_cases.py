
import pandas as pd
from unittest.mock import patch
import universal_backtest as ub


def run_test(rows, buys, sells):
    dates = pd.date_range(
        end=pd.Timestamp.now(tz="UTC").normalize(),
        periods=len(rows),
        freq="B",
        name="timestamp"
    )

    data = pd.DataFrame(
        rows,
        columns=["open", "high", "low", "close"],
        index=dates
    )

    data["volume"] = 100000

    strategy = {
        "symbol": "TEST",
        "years": 1,
        "entry": {"operator": "gt", "left": 1, "right": 0},
        "exit": {"operator": "lt", "left": 0, "right": 1},
        "stop_loss": None,
        "take_profit": None
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


# 測試一：同時出現買賣訊號
df, trades, stats = run_test(
    [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (110, 111, 109, 110),
        (120, 121, 119, 120)
    ],
    buys=[True, True, False, False],
    sells=[False, True, False, False]
)

# 第一天有買進訊號，第二天開盤買進
# 第二天同時有買賣訊號
# 第三天應先執行賣出，而不是重複買進
assert len(trades) == 1
assert trades[0]["reason"] == "策略出場"
assert stats["open_position"] is False

print("✅ 同時出現買賣訊號，不會重複交易")


# 測試二：期末仍持有股票
df, trades, stats = run_test(
    [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (110, 111, 109, 110),
        (120, 121, 119, 120)
    ],
    buys=[True, False, False, False],
    sells=[False, False, False, False]
)

assert stats["open_position"] is True
assert stats["trade_count"] == 0

buy_price = 100 * (1 + ub.SLIPPAGE)
shares = ub.INITIAL_CAPITAL / (
    buy_price * (1 + ub.FEE_RATE)
)

expected_equity = shares * 120

assert abs(
    stats["final_equity"] - expected_equity
) < 0.01

assert abs(
    df["equity"].iloc[-1] - expected_equity
) < 0.01

print("✅ 未平倉股票正確計入期末資產")


# 測試三：最後一天才出現買進訊號
df, trades, stats = run_test(
    [
        (100, 101, 99, 100),
        (110, 111, 109, 110),
        (120, 121, 119, 120)
    ],
    buys=[False, False, True],
    sells=[False, False, False]
)

assert stats["open_position"] is False
assert stats["trade_count"] == 0
assert stats["final_equity"] == ub.INITIAL_CAPITAL

print("✅ 最後一天訊號不會使用未來價格成交")


print("\n✅ 第三階段回測邊界測試全部通過")
