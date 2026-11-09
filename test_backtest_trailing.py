
import pandas as pd
from unittest.mock import patch

import universal_backtest as ub


def run_test(rows, trailing=None, fixed_stop=None):
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
        "stop_loss": fixed_stop,
        "take_profit": None,
        "max_hold_days": None,
        "trailing_stop_pct": trailing
    }

    buys = pd.Series(
        [True] + [False] * (len(rows) - 1)
    )
    sells = pd.Series(
        [False] * len(rows)
    )

    with patch.object(
        ub, "get_stock_data", return_value=data
    ), patch.object(
        ub, "evaluate_condition",
        side_effect=[buys, sells]
    ):
        return ub.run_universal_backtest(strategy)


# 測試一：買進後漲到120，下一天回落
df, trades, stats = run_test(
    [
        (100, 101, 99, 100),
        (100, 120, 99, 118),
        (115, 116, 108, 110),
        (110, 111, 109, 110)
    ],
    trailing=8
)

assert len(trades) == 1
assert trades[0]["reason"] == "追蹤停損"

expected_stop = 120 * 0.92
expected_sell = expected_stop * (
    1 - ub.SLIPPAGE
)

assert abs(
    trades[0]["sell_price"] - expected_sell
) < 0.01

print("✅ 股價創高後，追蹤停損正確出場")


# 測試二：隔天跳空跌破追蹤停損
df, trades, stats = run_test(
    [
        (100, 101, 99, 100),
        (100, 120, 99, 118),
        (100, 105, 98, 102),
        (103, 104, 102, 103)
    ],
    trailing=8
)

assert len(trades) == 1
assert trades[0]["reason"] == "跳空追蹤停損"

assert abs(
    trades[0]["sell_price"]
    - 100 * (1 - ub.SLIPPAGE)
) < 0.01

print("✅ 跳空跌破追蹤停損，按開盤價出場")


# 測試三：固定停損與追蹤停損同時存在
# 買進初期固定5%比追蹤8%更嚴格
df, trades, stats = run_test(
    [
        (100, 101, 99, 100),
        (100, 101, 94, 96),
        (97, 98, 96, 97)
    ],
    trailing=8,
    fixed_stop=5
)

assert len(trades) == 1
assert trades[0]["reason"] == "停損"

print("✅ 固定停損與追蹤停損可以共同使用")


# 測試四：沒有設定追蹤停損
df, trades, stats = run_test(
    [
        (100, 101, 99, 100),
        (100, 120, 99, 118),
        (115, 116, 108, 110),
        (110, 111, 109, 110)
    ],
    trailing=None
)

assert len(trades) == 0
assert stats["open_position"] is True

print("✅ 未設定追蹤停損時，維持舊版行為")


# 測試五：不合法參數必須拒絕
try:
    run_test(
        [
            (100, 101, 99, 100),
            (100, 101, 99, 100)
        ],
        trailing=-8
    )
except ValueError:
    print("✅ 不合法追蹤停損參數已拒絕")
else:
    raise AssertionError(
        "沒有拒絕不合法的追蹤停損參數"
    )


print("\n✅ 追蹤停損回測整合測試全部通過")
