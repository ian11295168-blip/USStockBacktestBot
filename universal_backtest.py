
import math
import pandas as pd

from market_data import get_stock_data
from strategy_engine import evaluate_condition
from trailing_stop import TrailingStop
from position_rules import (
    PositionState,
    validate_position_rule,
    evaluate_position_rule
)


INITIAL_CAPITAL = 10000.0
FEE_RATE = 0.0005
SLIPPAGE = 0.0005


def run_universal_backtest(strategy):
    symbol = str(strategy["symbol"]).strip().upper()
    years = strategy.get("years", 5)

    if type(years) is not int or not 1 <= years <= 10:
        raise ValueError("回測年數必須是1至10的整數")

    if "entry" not in strategy or "exit" not in strategy:
        raise ValueError("策略必須包含entry和exit")

    stop_loss = strategy.get("stop_loss")
    take_profit = strategy.get("take_profit")
    max_hold_days = strategy.get("max_hold_days")
    trailing_stop_pct = strategy.get("trailing_stop_pct")

    # 新增：通用持倉出場規則
    position_exit = strategy.get("position_exit")

    if position_exit is not None:
        validate_position_rule(position_exit)

    for name, value in (
        ("stop_loss", stop_loss),
        ("take_profit", take_profit),
        ("trailing_stop_pct", trailing_stop_pct)
    ):
        if value is None:
            continue

        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or value <= 0
            or (
                value >= 100
                if name == "trailing_stop_pct"
                else value > 100
            )
        ):
            raise ValueError(f"{name}百分比不合法")

    if max_hold_days is not None:
        if (
            type(max_hold_days) is not int
            or not 1 <= max_hold_days <= 250
        ):
            raise ValueError(
                "最大持有期限必須是1至250個交易日"
            )

    # 取得歷史資料
    df = get_stock_data(symbol, years).reset_index()
    df = df.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    if df.empty:
        raise ValueError("沒有歷史資料")

    # 先利用完整資料計算技術指標，
    # 保留回測期間之前的指標預熱資料
    df["buy_signal"] = evaluate_condition(
        df, strategy["entry"]
    )

    df["sell_signal"] = evaluate_condition(
        df, strategy["exit"]
    )

    cutoff = (
        pd.Timestamp.now(tz="UTC")
        - pd.Timedelta(days=365 * years)
    )

    df = df[
        df["timestamp"] >= cutoff
    ].copy().reset_index(drop=True)

    if len(df) < 2:
        raise ValueError("回測資料不足")

    cash = INITIAL_CAPITAL
    shares = 0.0

    entry_price = None
    entry_date = None
    entry_capital = None
    entry_index = None

    trailing_stop = None

    # 新增：每筆交易各自的持倉狀態
    position_state = None

    # 新增：前一日收盤確認的持倉出場訊號
    pending_position_exit = False

    trades = []
    equity_curve = []

    def close_position(price, date, reason):
        nonlocal cash, shares
        nonlocal entry_index
        nonlocal trailing_stop
        nonlocal position_state
        nonlocal pending_position_exit

        exit_price = price * (1 - SLIPPAGE)

        cash = (
            shares
            * exit_price
            * (1 - FEE_RATE)
        )

        trades.append({
            "buy_date": entry_date,
            "sell_date": date,
            "buy_price": entry_price,
            "sell_price": exit_price,
            "return_pct": (
                cash / entry_capital - 1
            ) * 100,
            "reason": reason
        })

        shares = 0.0
        entry_index = None
        trailing_stop = None
        position_state = None
        pending_position_exit = False

    for i in range(len(df)):
        today = df.iloc[i]

        day_open = float(today["open"])
        day_high = float(today["high"])
        day_low = float(today["low"])
        day_close = float(today["close"])

        # 當天開盤是否已因其他規則出場
        exited_at_open = False

        # 開盤只使用昨天收盤時已知的訊號
        if i > 0:
            yesterday = df.iloc[i - 1]

            if shares > 0:
                # 原本的策略訊號優先
                if bool(yesterday["sell_signal"]):
                    close_position(
                        day_open,
                        today["timestamp"],
                        "策略出場"
                    )
                    exited_at_open = True

                # 新增：前一天收盤成立的持倉規則
                elif pending_position_exit:
                    close_position(
                        day_open,
                        today["timestamp"],
                        "持倉條件出場"
                    )
                    exited_at_open = True

                # 最大持有期限
                elif (
                    max_hold_days is not None
                    and entry_index is not None
                    and i - entry_index >= max_hold_days
                ):
                    close_position(
                        day_open,
                        today["timestamp"],
                        "持有期限"
                    )
                    exited_at_open = True

            # 空手才可買進
            # 如果今天剛賣出，不在同一次開盤重新買進
            if (
                shares == 0
                and not exited_at_open
                and bool(yesterday["buy_signal"])
            ):
                entry_capital = cash

                entry_price = (
                    day_open * (1 + SLIPPAGE)
                )

                entry_date = today["timestamp"]
                entry_index = i

                shares = cash / (
                    entry_price * (1 + FEE_RATE)
                )

                cash = 0.0

                if trailing_stop_pct is not None:
                    trailing_stop = TrailingStop(
                        entry_price=entry_price,
                        percent=trailing_stop_pct
                    )
                else:
                    trailing_stop = None

                # 新交易從頭開始計算持倉狀態
                if position_exit is not None:
                    position_state = PositionState(
                        entry_price=entry_price
                    )
                else:
                    position_state = None

                pending_position_exit = False

        # 停損停利使用當天OHLC模擬成交
        if shares > 0:
            stop_candidates = []

            if stop_loss is not None:
                fixed_stop = entry_price * (
                    1 - float(stop_loss) / 100
                )

                stop_candidates.append((
                    fixed_stop,
                    "停損",
                    "跳空停損"
                ))

            if trailing_stop is not None:
                stop_candidates.append((
                    trailing_stop.stop_price,
                    "追蹤停損",
                    "跳空追蹤停損"
                ))

            # 多條停損線取較高者
            active_stop = (
                max(
                    stop_candidates,
                    key=lambda item: item[0]
                )
                if stop_candidates
                else None
            )

            target_price = None

            if take_profit is not None:
                target_price = entry_price * (
                    1 + float(take_profit) / 100
                )

            exit_price = None
            reason = None

            # 開盤跳空先處理
            if (
                active_stop is not None
                and day_open <= active_stop[0]
            ):
                exit_price = day_open
                reason = active_stop[2]

            elif (
                target_price is not None
                and day_open >= target_price
            ):
                exit_price = day_open
                reason = "跳空停利"

            # 盤中同時觸發停損、停利時，
            # 延續原有的停損優先保守假設
            elif (
                active_stop is not None
                and day_low <= active_stop[0]
            ):
                exit_price = active_stop[0]
                reason = active_stop[1]

            elif (
                target_price is not None
                and day_high >= target_price
            ):
                exit_price = target_price
                reason = "停利"

            if exit_price is not None:
                close_position(
                    exit_price,
                    today["timestamp"],
                    reason
                )

            else:
                # 今日沒有出場，才更新追蹤停損高點
                if trailing_stop is not None:
                    trailing_stop.check_day(
                        day_open=day_open,
                        day_high=day_high,
                        day_low=day_low
                    )

                # 今天收盤後更新持倉狀態
                if position_state is not None:
                    position_state.update_close(
                        day_close
                    )

                    # 今天成立，明天開盤才能出場
                    pending_position_exit = (
                        evaluate_position_rule(
                            position_exit,
                            position_state
                        )
                    )

        equity_curve.append(
            cash + shares * day_close
        )

    df["equity"] = equity_curve

    equity_series = pd.Series(equity_curve)

    max_drawdown = (
        equity_series
        / equity_series.cummax()
        - 1
    ).min() * 100

    returns = [
        trade["return_pct"]
        for trade in trades
    ]

    wins = [
        value for value in returns
        if value > 0
    ]

    losses = [
        value for value in returns
        if value <= 0
    ]

    stats = {
        "trade_count": len(trades),

        "win_rate": (
            len(wins) / len(trades) * 100
            if trades else 0
        ),

        "total_return": (
            equity_curve[-1] / INITIAL_CAPITAL - 1
        ) * 100,

        "buy_hold_return": (
            float(df.iloc[-1]["close"])
            / float(df.iloc[0]["close"])
            - 1
        ) * 100,

        "max_drawdown": max_drawdown,

        "average_win": (
            sum(wins) / len(wins)
            if wins else 0
        ),

        "average_loss": (
            sum(losses) / len(losses)
            if losses else 0
        ),

        "best_trade": (
            max(returns) if returns else 0
        ),

        "worst_trade": (
            min(returns) if returns else 0
        ),

        "open_position": shares > 0,
        "final_equity": equity_curve[-1]
    }

    return df, trades, stats
