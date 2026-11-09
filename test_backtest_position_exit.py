
import pandas as pd
from unittest.mock import patch

import universal_backtest as ub


def run_test(
    closes,
    position_exit,
    sell_days=None,
    stop_loss=None
):
    n = len(closes)

    dates = pd.date_range(
        end=pd.Timestamp.now(tz="UTC").normalize(),
        periods=n,
        freq="B",
        name="timestamp"
    )

    rows = []

    for close in closes:
        rows.append((
            close,
            close + 1,
            close - 1,
            close
        ))

    data = pd.DataFrame(
        rows,
        columns=["open", "high", "low", "close"],
        index=dates
    )

    data["volume"] = 100000

    buys = pd.Series(
        [True] + [False] * (n - 1)
    )

    if sell_days is None:
        sell_days = [False] * n

    sells = pd.Series(sell_days)

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
        "max_hold_days": None,
        "trailing_stop_pct": None,
        "position_exit": position_exit
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


# 測試一：
# 買進後持有滿5個交易日，
# 收盤報酬仍低於3%時，下一天開盤賣出
rule_timeout = {
    "operator": "and",
    "conditions": [
        {
            "operator": "gte",
            "metric": "holding_days",
            "value": 5
        },
        {
            "operator": "lt",
            "metric": "return_pct",
            "value": 3
        }
    ]
}

df, trades, stats = run_test(
    closes=[
        100, 100, 101, 101,
        102, 102, 102, 103
    ],
    position_exit=rule_timeout
)

assert len(trades) == 1
assert trades[0]["reason"] == "持倉條件出場"

# 第2筆資料開盤買進
assert trades[0]["buy_date"] == df.iloc[1]["timestamp"]

# 第2至第6筆為完整5個持有交易日
# 第7筆資料開盤賣出
assert trades[0]["sell_date"] == df.iloc[6]["timestamp"]

print("✅ 持有5天且報酬不足3%，隔日開盤出場")


# 測試二：
# 即使條件成立，也不能在當天收盤直接賣出
df, trades, stats = run_test(
    closes=[100, 100, 101, 102],
    position_exit={
        "operator": "gte",
        "metric": "holding_days",
        "value": 3
    }
)

assert len(trades) == 0
assert stats["open_position"] is True

print("✅ 最後一天成立的持倉訊號不會提前成交")


# 測試三：
# 獲利曾達10%，最高收盤價回落5%才出場
rule_pullback = {
    "operator": "and",
    "conditions": [
        {
            "operator": "gte",
            "metric": "peak_return_pct",
            "value": 10
        },
        {
            "operator": "gte",
            "metric": "pullback_pct",
            "value": 5
        }
    ]
}

df, trades, stats = run_test(
    closes=[100, 100, 105, 112, 110, 105, 104],
    position_exit=rule_pullback
)

assert len(trades) == 1
assert trades[0]["reason"] == "持倉條件出場"
assert trades[0]["sell_date"] == df.iloc[6]["timestamp"]

print("✅ 曾獲利10%後回落5%，隔日開盤出場")


# 測試四：
# 原本策略賣出訊號優先於持倉規則
df, trades, stats = run_test(
    closes=[100, 100, 101, 102, 103],
    position_exit={
        "operator": "gte",
        "metric": "holding_days",
        "value": 2
    },
    sell_days=[False, False, True, False, False]
)

assert len(trades) == 1
assert trades[0]["reason"] == "策略出場"

print("✅ 原本策略訊號優先順序正常")


# 測試五：沒有持倉出場規則時保留舊行為
df, trades, stats = run_test(
    closes=[100, 100, 101, 102, 103],
    position_exit=None
)

assert len(trades) == 0
assert stats["open_position"] is True

print("✅ 沒有持倉規則時保留原本行為")


# 測試六：未知持倉規則必須拒絕
bad_rule = {
    "operator": "gt",
    "metric": "unknown",
    "value": 5
}

try:
    run_test(
        closes=[100, 100, 101],
        position_exit=bad_rule
    )
except ValueError:
    print("✅ 不合法持倉規則已拒絕")
else:
    raise AssertionError(
        "系統沒有拒絕未知持倉規則"
    )


print("\n✅ 通用持倉出場回測測試全部通過")
