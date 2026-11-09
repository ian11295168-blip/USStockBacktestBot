
import pandas as pd
from unittest.mock import patch

import universal_backtest as ub


def run_test(
    rows,
    fixed_stop=None,
    trailing_stop=None,
    take_profit=None,
    max_hold_days=None,
    sell_days=None
):
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

    buys = pd.Series(
        [True] + [False] * (len(rows) - 1)
    )

    if sell_days is None:
        sell_days = [False] * len(rows)

    sells = pd.Series(sell_days)

    strategy = {
        "symbol": "TEST",
        "years": 1,
        "entry": {
            "operator": "lt",
            "left": {"name": "rsi", "period": 14},
            "right": 30
        },
        "exit": {
            "operator": "gt",
            "left": {"name": "rsi", "period": 14},
            "right": 70
        },
        "stop_loss": fixed_stop,
        "take_profit": take_profit,
        "max_hold_days": max_hold_days,
        "trailing_stop_pct": trailing_stop
    }

    with patch.object(
        ub,
        "get_stock_data",
        return_value=data
    ), patch.object(
        ub,
        "evaluate_condition",
        side_effect=[buys, sells]
    ):
        return ub.run_universal_backtest(strategy)


def check_trade(trades, reason, number=1):
    assert len(trades) == number, (
        f"預期{number}筆交易，"
        f"實際為{len(trades)}筆"
    )

    assert trades[0]["reason"] == reason, (
        f"預期出場原因：{reason}，"
        f"實際為：{trades[0]['reason']}"
    )


# 測試一：追蹤停損價提高後，
# 比固定停損更早觸發
df, trades, stats = run_test(
    [
        (100, 101, 99, 100),
        (100, 120, 99, 118),
        (115, 116, 109, 110),
        (110, 111, 109, 110)
    ],
    fixed_stop=5,
    trailing_stop=8
)

check_trade(trades, "追蹤停損")

expected_price = 120 * 0.92

assert abs(
    trades[0]["sell_price"]
    - expected_price * (1 - ub.SLIPPAGE)
) < 0.01

print("✅ 追蹤停損比固定停損更早觸發")


# 測試二：買進初期固定停損較嚴格，
# 先由固定停損出場
df, trades, stats = run_test(
    [
        (100, 101, 99, 100),
        (100, 103, 94, 96),
        (97, 98, 96, 97)
    ],
    fixed_stop=5,
    trailing_stop=8
)

check_trade(trades, "停損")

print("✅ 固定停損可以優先觸發")


# 測試三：前一天出現策略賣出訊號，
# 隔天開盤直接出場
df, trades, stats = run_test(
    [
        (100, 101, 99, 100),
        (100, 120, 99, 118),
        (115, 116, 109, 110),
        (110, 111, 109, 110)
    ],
    trailing_stop=8,
    sell_days=[False, True, False, False]
)

check_trade(trades, "策略出場")

assert abs(
    trades[0]["sell_price"]
    - 115 * (1 - ub.SLIPPAGE)
) < 0.01

print("✅ 前日策略賣出訊號在隔日開盤執行")


# 測試四：持有期限到期，
# 即使還沒觸及追蹤停損也出場
df, trades, stats = run_test(
    [
        (100, 101, 99, 100),
        (100, 110, 99, 108),
        (109, 110, 108, 109),
        (110, 111, 109, 110)
    ],
    trailing_stop=8,
    max_hold_days=1
)

check_trade(trades, "持有期限")

assert (
    trades[0]["sell_date"]
    == df.iloc[2]["timestamp"]
)

print("✅ 持有期限到期後按下一交易日開盤出場")


# 測試五：開盤跳空跌破追蹤停損
df, trades, stats = run_test(
    [
        (100, 101, 99, 100),
        (100, 120, 99, 118),
        (100, 105, 98, 102),
        (103, 104, 102, 103)
    ],
    trailing_stop=8
)

check_trade(trades, "跳空追蹤停損")

assert abs(
    trades[0]["sell_price"]
    - 100 * (1 - ub.SLIPPAGE)
) < 0.01

print("✅ 追蹤停損跳空時按開盤價模擬成交")


# 測試六：同一天同時觸及停損與停利
# 日K無法知道先後，依目前模型採停損優先
df, trades, stats = run_test(
    [
        (100, 101, 99, 100),
        (100, 120, 99, 118),
        (115, 130, 105, 115),
        (116, 117, 114, 116)
    ],
    trailing_stop=8,
    take_profit=25
)

check_trade(trades, "追蹤停損")

print("✅ 同日觸及追蹤停損與停利時採保守假設")


print("\n✅ 六項出場優先順序測試全部通過")
