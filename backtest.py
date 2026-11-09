
import re
import pandas as pd
from market_data import get_stock_data


INITIAL_CAPITAL = 10000.0
FEE_RATE = 0.0005
SLIPPAGE = 0.0005


def validate_strategy(strategy):
    s = strategy.copy()

    s["symbol"] = str(s["symbol"]).upper().strip()
    s["years"] = int(s["years"])

    if not re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", s["symbol"]):
        raise ValueError("股票代號格式不正確")

    if not 1 <= s["years"] <= 10:
        raise ValueError("回測期間必須為1至10年")

    if s["strategy_type"] == "ma_cross":
        fast = int(s["fast_ma"])
        slow = int(s["slow_ma"])

        if not 1 < fast < slow <= 250:
            raise ValueError("均線設定必須是 1 < 快線 < 慢線 <= 250")

        s["fast_ma"] = fast
        s["slow_ma"] = slow


    elif s["strategy_type"] == "rsi":
        if (
            s.get("rsi_period") is None
            or s.get("rsi_buy") is None
            or s.get("rsi_sell") is None
        ):
            raise ValueError(
                "RSI策略缺少參數，請指定週期與買賣門檻。"
            )

        period = int(s["rsi_period"])
        buy = float(s["rsi_buy"])
        sell = float(s["rsi_sell"])

        if not 2 <= period <= 100:
            raise ValueError("RSI週期必須介於2至100")

        if not 0 < buy < sell < 100:
            raise ValueError("RSI買賣門檻不正確")

        s["rsi_period"] = period
        s["rsi_buy"] = buy
        s["rsi_sell"] = sell

    else:
        raise ValueError("目前只支援 ma_cross 和 rsi")

    for key in ("stop_loss", "take_profit"):
        value = s.get(key)

        if value is not None:
            value = float(value)

            if not 0 < value <= 100:
                raise ValueError(f"{key} 必須介於0至100%")

            s[key] = value

    return s


def calculate_rsi(close, period):
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - 100 / (1 + rs)

    rsi = rsi.mask(
        (avg_loss == 0) & (avg_gain > 0), 100
    )
    rsi = rsi.mask(
        (avg_gain == 0) & (avg_loss > 0), 0
    )

    return rsi


def run_strategy_backtest(strategy):
    s = validate_strategy(strategy)

    df = get_stock_data(
        s["symbol"], s["years"]
    ).reset_index()

    df = df.sort_values("timestamp").reset_index(drop=True)

    if s["strategy_type"] == "ma_cross":
        fast = s["fast_ma"]
        slow = s["slow_ma"]

        df["fast_ma"] = df["close"].rolling(fast).mean()
        df["slow_ma"] = df["close"].rolling(slow).mean()

        df["buy_signal"] = (
            (df["fast_ma"] > df["slow_ma"]) &
            (df["fast_ma"].shift(1) <= df["slow_ma"].shift(1))
        )

        df["sell_signal"] = (
            (df["fast_ma"] < df["slow_ma"]) &
            (df["fast_ma"].shift(1) >= df["slow_ma"].shift(1))
        )

    else:
        df["rsi"] = calculate_rsi(
            df["close"], s["rsi_period"]
        )

        df["buy_signal"] = (
            df["rsi"] < s["rsi_buy"]
        )

        df["sell_signal"] = (
            df["rsi"] > s["rsi_sell"]
        )

    # 排除指標預熱期，只保留指定回測期間
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(
        days=365 * s["years"]
    )

    df = df[df["timestamp"] >= cutoff].copy()
    df = df.reset_index(drop=True)

    if len(df) < 2:
        raise ValueError("回測期間資料不足")

    cash = INITIAL_CAPITAL
    shares = 0.0
    entry_price = None
    entry_date = None
    entry_capital = None

    trades = []
    equity_curve = [INITIAL_CAPITAL]

    for i in range(1, len(df)):
        today = df.iloc[i]
        yesterday = df.iloc[i - 1]

        day_open = float(today["open"])
        day_high = float(today["high"])
        day_low = float(today["low"])
        day_close = float(today["close"])

        # 昨天收盤產生訊號，今天開盤執行
        if shares > 0 and bool(yesterday["sell_signal"]):
            exit_price = day_open * (1 - SLIPPAGE)

            cash = shares * exit_price * (1 - FEE_RATE)

            trades.append({
                "buy_date": entry_date,
                "sell_date": today["timestamp"],
                "buy_price": entry_price,
                "sell_price": exit_price,
                "return_pct": (
                    cash / entry_capital - 1
                ) * 100,
                "reason": "策略出場"
            })

            shares = 0.0

        elif shares == 0 and bool(yesterday["buy_signal"]):
            entry_capital = cash
            entry_price = day_open * (1 + SLIPPAGE)
            entry_date = today["timestamp"]

            shares = cash / (
                entry_price * (1 + FEE_RATE)
            )
            cash = 0.0

        # 停損與停利
        if shares > 0:
            stop = None
            target = None

            if s.get("stop_loss") is not None:
                stop = entry_price * (
                    1 - s["stop_loss"] / 100
                )

            if s.get("take_profit") is not None:
                target = entry_price * (
                    1 + s["take_profit"] / 100
                )

            exit_price = None
            reason = None

            # 跳空時以開盤價成交；同日同時觸及
            # 停損與停利時，保守假設先停損
            if stop is not None and day_open <= stop:
                exit_price = day_open
                reason = "跳空停損"

            elif target is not None and day_open >= target:
                exit_price = day_open
                reason = "跳空停利"

            elif stop is not None and day_low <= stop:
                exit_price = stop
                reason = "停損"

            elif target is not None and day_high >= target:
                exit_price = target
                reason = "停利"

            if exit_price is not None:
                exit_price *= (1 - SLIPPAGE)

                cash = shares * exit_price * (1 - FEE_RATE)

                trades.append({
                    "buy_date": entry_date,
                    "sell_date": today["timestamp"],
                    "buy_price": entry_price,
                    "sell_price": exit_price,
                    "return_pct": (
                        cash / entry_capital - 1
                    ) * 100,
                    "reason": reason
                })

                shares = 0.0

        # 每日以收盤價計算資產淨值
        equity = cash + shares * day_close
        equity_curve.append(equity)
    df["equity"] = equity_curve

    equity = pd.Series(equity_curve)
    peak = equity.cummax()

    max_drawdown = (
        (equity / peak - 1).min() * 100
    )

    returns = [t["return_pct"] for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]

    buy_hold = (
        df.iloc[-1]["close"] / df.iloc[0]["close"] - 1
    ) * 100

    stats = {
        "trade_count": len(trades),
        "win_rate": (
            len(wins) / len(trades) * 100
            if trades else 0
        ),
        "total_return": (
            equity.iloc[-1] / INITIAL_CAPITAL - 1
        ) * 100,
        "buy_hold_return": buy_hold,
        "max_drawdown": max_drawdown,
        "average_win": (
            sum(wins) / len(wins) if wins else 0
        ),
        "average_loss": (
            sum(losses) / len(losses) if losses else 0
        ),
        "best_trade": max(returns) if returns else 0,
        "worst_trade": min(returns) if returns else 0,
        "open_position": shares > 0
    }
    print("回傳欄位：", df.columns.tolist())
    return df, trades, stats


if __name__ == "__main__":
    test_strategy = {
        "symbol": "AAPL",
        "years": 5,
        "strategy_type": "ma_cross",
        "fast_ma": 20,
        "slow_ma": 60,
        "stop_loss": 8,
        "take_profit": None
    }

    df, trades, stats = run_strategy_backtest(test_strategy)

    print("\n美股策略回測完成")
    print("股票：", test_strategy["symbol"])
    print("資料來源：Alpaca IEX")
    print("資料起日：", df.iloc[0]["timestamp"])
    print("資料迄日：", df.iloc[-1]["timestamp"])
    print("完整交易：", stats["trade_count"])
    print(f"勝率：{stats['win_rate']:.2f}%")
    print(f"總報酬：{stats['total_return']:.2f}%")
    print(f"Buy & Hold：{stats['buy_hold_return']:.2f}%")
    print(f"最大回撤：{stats['max_drawdown']:.2f}%")
    print("期末仍持倉：", stats["open_position"])

    print("\n最近5筆交易：")
    for trade in trades[-5:]:
        print(trade)
