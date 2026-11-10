
"""按時間順序切分回測績效，檢查樣本內外表現。"""

import math

import numpy as np
import pandas as pd


def calculate_segment(
    data,
    starting_equity,
    starting_close
):
    """計算一個時間區段的報酬與風險。"""

    equity = data["equity"].to_numpy(dtype=float)
    closes = data["close"].to_numpy(dtype=float)

    # 把區段開始之前的資產作為計算基準
    values = np.concatenate([
        [starting_equity], equity
    ])

    returns = values[1:] / values[:-1] - 1

    strategy_return = (
        equity[-1] / starting_equity - 1
    ) * 100

    buy_hold_return = (
        closes[-1] / starting_close - 1
    ) * 100

    peaks = np.maximum.accumulate(values)
    drawdowns = values / peaks - 1

    max_drawdown = float(
        drawdowns.min() * 100
    )

    volatility = None
    sharpe = None

    if len(returns) >= 2:
        std = float(
            np.std(returns, ddof=1)
        )

        volatility = (
            std * math.sqrt(252) * 100
        )

        if std > 1e-12:
            sharpe = (
                float(np.mean(returns))
                / std
                * math.sqrt(252)
            )

    return {
        "start_date": (
            data.iloc[0]["timestamp"]
            .date().isoformat()
        ),
        "end_date": (
            data.iloc[-1]["timestamp"]
            .date().isoformat()
        ),
        "trading_days": len(data),
        "strategy_return": strategy_return,
        "buy_hold_return": buy_hold_return,
        "excess_return": (
            strategy_return - buy_hold_return
        ),
        "max_drawdown": max_drawdown,
        "annual_volatility": volatility,
        "sharpe_ratio": sharpe,
        "starting_equity": starting_equity,
        "ending_equity": float(equity[-1]),
    }


def analyze_out_of_sample(
    df,
    train_ratio=0.70,
    initial_capital=10000.0
):
    """
    對既有完整回測的每日資產曲線分段分析。

    train_ratio=0.70 表示：
    前70%交易日為樣本內，
    後30%交易日為樣本外。

    注意：這不會重新訓練或選擇策略。
    """

    if not isinstance(df, pd.DataFrame):
        raise ValueError("回測資料必須是DataFrame")

    required = {
        "timestamp", "equity", "close"
    }

    if not required.issubset(df.columns):
        raise ValueError(
            "資料缺少timestamp、equity或close"
        )

    if len(df) < 6:
        raise ValueError(
            "至少需要6個交易日資料"
        )

    if (
        type(train_ratio) not in (float, int)
        or not math.isfinite(train_ratio)
        or not 0.2 <= train_ratio <= 0.8
    ):
        raise ValueError(
            "訓練比例必須介於20%至80%"
        )

    if (
        type(initial_capital) not in (float, int)
        or not math.isfinite(initial_capital)
        or initial_capital <= 0
    ):
        raise ValueError(
            "初始資金必須大於0"
        )

    data = df[
        ["timestamp", "equity", "close"]
    ].copy()

    data["timestamp"] = pd.to_datetime(
        data["timestamp"],
        utc=True,
        errors="coerce"
    )

    for name in ("equity", "close"):
        data[name] = pd.to_numeric(
            data[name],
            errors="coerce"
        )

    if data.isna().any().any():
        raise ValueError(
            "資料包含無效日期或數值"
        )

    data = data.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    if data["timestamp"].duplicated().any():
        raise ValueError(
            "交易日期不可重複"
        )

    for name in ("equity", "close"):
        values = data[name].to_numpy(
            dtype=float
        )

        if (
            not np.isfinite(values).all()
            or (values <= 0).any()
        ):
            raise ValueError(
                f"{name}必須是有限正數"
            )

    split_index = int(
        len(data) * train_ratio
    )

    # 避免任一段交易日過少
    split_index = max(
        2,
        min(split_index, len(data) - 2)
    )

    train = data.iloc[
        :split_index
    ].copy()

    test = data.iloc[
        split_index:
    ].copy()

    train_result = calculate_segment(
        train,
        starting_equity=float(initial_capital),
        starting_close=float(
            data.iloc[0]["close"]
        )
    )

    # 測試期以訓練期最後一天為基準，
    # 避免漏算跨越切分日的價格變化
    test_result = calculate_segment(
        test,
        starting_equity=float(
            train.iloc[-1]["equity"]
        ),
        starting_close=float(
            train.iloc[-1]["close"]
        )
    )

    return {
        "train_ratio": train_ratio,
        "split_date": (
            test.iloc[0]["timestamp"]
            .date().isoformat()
        ),
        "train": train_result,
        "test": test_result,
    }


def format_oos_report(result, symbol="股票"):
    """整理成可發送 Telegram 的中文報告。"""

    train = result["train"]
    test = result["test"]

    def pct(value):
        if value is None:
            return "無法計算"
        return f"{value:+.2f}%"

    def num(value):
        if value is None:
            return "無法計算"
        return f"{value:.2f}"

    lines = [
        f"🧪 {symbol} 樣本內／外績效分析",
        "",
        f"切分日期：{result['split_date']}",
        "",
        "📘 樣本內（前段）",
        f"日期：{train['start_date']} "
        f"至 {train['end_date']}",
        f"交易日：{train['trading_days']}天",
        f"策略報酬：{pct(train['strategy_return'])}",
        f"買進持有：{pct(train['buy_hold_return'])}",
        f"最大回撤：{pct(train['max_drawdown'])}",
        f"Sharpe：{num(train['sharpe_ratio'])}",
        "",
        "📗 樣本外（後段）",
        f"日期：{test['start_date']} "
        f"至 {test['end_date']}",
        f"交易日：{test['trading_days']}天",
        f"策略報酬：{pct(test['strategy_return'])}",
        f"買進持有：{pct(test['buy_hold_return'])}",
        f"最大回撤：{pct(test['max_drawdown'])}",
        f"Sharpe：{num(test['sharpe_ratio'])}",
        "",
        "📌 注意",
        "本報告切分既有回測曲線，"
        "不會在切分日強制平倉。",
        "測試期可能承接訓練期的持倉。",
        "只有策略未使用後段資料進行設計、"
        "選擇或調整，後段才有樣本外驗證意義。",
        "Sharpe以0%無風險利率計算。"
    ]

    return "\n".join(lines)


def format_oos_report_en(result, symbol="Stock"):
    """English presentation of an existing equity curve split; no retraining occurs."""
    train = result["train"]
    test = result["test"]

    def percentage(value):
        return "N/A" if value is None else f"{value:+.2f}%"

    def number(value):
        return "N/A" if value is None else f"{value:.2f}"

    lines = [
        f"🧪 {symbol} | In-Sample / Out-of-Sample Analysis",
        "",
        f"Split Date: {result['split_date']}",
        "",
    ]
    for title, segment in (("📘 In-Sample (Earlier Period)", train),
                           ("📗 Out-of-Sample (Later Period)", test)):
        lines.extend([
            title,
            f"Date Range: {segment['start_date']} to {segment['end_date']}",
            f"Trading Days: {segment['trading_days']}",
            f"Strategy Return: {percentage(segment['strategy_return'])}",
            f"Buy & Hold Return: {percentage(segment['buy_hold_return'])}",
            f"Maximum Drawdown: {percentage(segment['max_drawdown'])}",
            f"Sharpe Ratio: {number(segment['sharpe_ratio'])}",
            "",
        ])
    lines.extend([
        "📌 Important Notes",
        "This report splits an existing historical backtest equity curve.",
        "Positions are not forcibly closed at the split date; positions from",
        "the earlier period may carry into the later period.",
        "The later period is a meaningful out-of-sample evaluation only if",
        "its data was not used to design, select, or tune the strategy.",
        "Sharpe ratios assume a 0% risk-free rate.",
    ])
    return "\n".join(lines)
