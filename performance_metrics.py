
import math

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR = 252
CALENDAR_DAYS_PER_YEAR = 365.2425


def calculate_performance_metrics(
    df,
    trades=None,
    risk_free_rate=0.0
):
    """
    計算策略績效分析。

    df需要包含：
        timestamp：交易日期
        equity：每日期末資產

    trades可包含：
        return_pct：單筆淨報酬率
        realized_pnl：單筆實現損益（美元）

    risk_free_rate：
        年化無風險利率，0.04代表4%。
        預設為0，以方便比較。

    注意：
    若沒有realized_pnl，不計算標準Profit Factor。
    """

    if not isinstance(df, pd.DataFrame):
        raise ValueError("回測資料必須是DataFrame")

    if not {"timestamp", "equity"}.issubset(df.columns):
        raise ValueError(
            "回測資料缺少timestamp或equity"
        )

    if len(df) < 2:
        raise ValueError("至少需要兩個交易日資料")

    if (
        type(risk_free_rate) not in (int, float)
        or not math.isfinite(risk_free_rate)
        or risk_free_rate <= -1
    ):
        raise ValueError("無風險利率不合法")

    data = df[["timestamp", "equity"]].copy()

    data["timestamp"] = pd.to_datetime(
        data["timestamp"],
        utc=True,
        errors="coerce"
    )

    data["equity"] = pd.to_numeric(
        data["equity"],
        errors="coerce"
    )

    if data.isna().any().any():
        raise ValueError("回測資料包含無效值")

    data = data.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    if data["timestamp"].duplicated().any():
        raise ValueError("交易日期不得重複")

    equity = data["equity"].astype(float)

    if not np.isfinite(equity.to_numpy()).all():
        raise ValueError("資產數值必須有限")

    if (equity <= 0).any():
        raise ValueError("資產數值必須大於0")

    first_date = data.iloc[0]["timestamp"]
    last_date = data.iloc[-1]["timestamp"]

    elapsed_years = (
        (last_date - first_date).total_seconds()
        / (86400 * CALENDAR_DAYS_PER_YEAR)
    )

    if elapsed_years <= 0:
        raise ValueError("回測日期區間不合法")

    first_equity = float(equity.iloc[0])
    final_equity = float(equity.iloc[-1])

    total_return = (
        final_equity / first_equity - 1
    ) * 100

    cagr = (
        (final_equity / first_equity)
        ** (1 / elapsed_years)
        - 1
    ) * 100

    daily_returns = (
        equity.pct_change().dropna()
    )

    daily_std = float(
        daily_returns.std(ddof=1)
    ) if len(daily_returns) >= 2 else 0.0

    if not math.isfinite(daily_std):
        daily_std = 0.0

    annual_volatility = (
        daily_std
        * math.sqrt(TRADING_DAYS_PER_YEAR)
        * 100
    )

    # 將年化無風險利率換算成每日複利報酬
    daily_risk_free = (
        (1 + risk_free_rate)
        ** (1 / TRADING_DAYS_PER_YEAR)
        - 1
    )

    # 波動為零時Sharpe無法定義
    sharpe_ratio = None

    if daily_std > 1e-12:
        sharpe_ratio = (
            (
                float(daily_returns.mean())
                - daily_risk_free
            )
            / daily_std
            * math.sqrt(TRADING_DAYS_PER_YEAR)
        )

    running_peak = equity.cummax()

    drawdowns = (
        equity / running_peak - 1
    )

    max_drawdown = float(
        drawdowns.min()
    ) * 100

    trades = [] if trades is None else trades

    if not isinstance(trades, list):
        raise ValueError("trades必須是交易清單")

    trade_returns = []

    for trade in trades:
        if not isinstance(trade, dict):
            raise ValueError("交易紀錄格式錯誤")

        value = trade.get("return_pct")

        if value is not None:
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
            ):
                raise ValueError("交易報酬數值不合法")

            trade_returns.append(float(value))

    trade_count = len(trades)

    win_count = sum(
        value > 0 for value in trade_returns
    )

    loss_count = sum(
        value < 0 for value in trade_returns
    )

    win_rate = (
        win_count / len(trade_returns) * 100
        if trade_returns else None
    )

    average_trade_return = (
        sum(trade_returns) / len(trade_returns)
        if trade_returns else None
    )

    # 標準Profit Factor必須使用實際美元損益。
    # 舊版回測交易紀錄只有return_pct，
    # 不可把百分比總和比值冒充標準Profit Factor。
    profit_factor = None

    has_full_pnl = (
        trade_count > 0
        and all(
            "realized_pnl" in trade
            for trade in trades
        )
    )

    if has_full_pnl:
        pnls = []

        for trade in trades:
            value = trade["realized_pnl"]

            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
            ):
                raise ValueError(
                    "實現損益必須是有效數字"
                )

            pnls.append(float(value))

        gross_profit = sum(
            value for value in pnls if value > 0
        )

        gross_loss = abs(sum(
            value for value in pnls if value < 0
        ))

        if gross_loss > 0:
            profit_factor = (
                gross_profit / gross_loss
            )

        # 沒有虧損時，PF未定義或無限大；
        # 先用None表示，不顯示虛假的有限值。

    return {
        "total_return": total_return,
        "cagr": cagr,
        "annual_volatility": annual_volatility,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
        "elapsed_years": elapsed_years,
        "trade_count": trade_count,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": win_rate,
        "average_trade_return": average_trade_return,
        "profit_factor": profit_factor,
        "first_equity": first_equity,
        "final_equity": final_equity
    }


def format_performance_report(metrics):
    """將績效數字轉成可閱讀的中文文字。"""

    def percent(value):
        if value is None:
            return "無法計算"
        return f"{value:+.2f}%"

    def number(value):
        if value is None:
            return "無法計算"
        return f"{value:.2f}"

    return (
        "📊 進階回測績效\n\n"
        f"總報酬：{percent(metrics['total_return'])}\n"
        f"年化報酬 CAGR：{percent(metrics['cagr'])}\n"
        f"年化波動率："
        f"{percent(metrics['annual_volatility'])}\n"
        f"Sharpe Ratio："
        f"{number(metrics['sharpe_ratio'])}\n"
        f"最大回撤："
        f"{percent(metrics['max_drawdown'])}\n\n"
        f"已完成交易：{metrics['trade_count']}筆\n"
        f"勝率：{percent(metrics['win_rate'])}\n"
        f"單筆平均報酬："
        f"{percent(metrics['average_trade_return'])}\n"
        f"Profit Factor："
        f"{number(metrics['profit_factor'])}\n\n"
        "註：Sharpe以每日資產變化計算，"
        "預設無風險利率0%。\n"
        "Profit Factor必須有每筆實際實現損益"
        "才能計算。"
    )
