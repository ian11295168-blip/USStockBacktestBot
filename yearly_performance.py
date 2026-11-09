
import math

import numpy as np
import pandas as pd


def calculate_yearly_performance(
    df,
    initial_capital=10000.0
):
    """
    計算每個曆年的策略與買進持有報酬。

    df 必須有：
    timestamp：交易日期
    equity：每日策略總資產
    close：股票每日收盤價

    第一年的策略起點使用 initial_capital。
    第一年的買進持有基準使用首日收盤價。

    後續年份以前一年最後一個交易日
    的數值為比較起點。
    """

    required = {"timestamp", "equity", "close"}

    if not isinstance(df, pd.DataFrame):
        raise ValueError("資料必須是 DataFrame")

    if not required.issubset(df.columns):
        raise ValueError(
            "缺少 timestamp、equity 或 close"
        )

    if (
        type(initial_capital) not in (int, float)
        or not math.isfinite(initial_capital)
        or initial_capital <= 0
    ):
        raise ValueError("初始資金必須大於0")

    if df.empty:
        raise ValueError("沒有回測資料")

    data = df[
        ["timestamp", "equity", "close"]
    ].copy()

    data["timestamp"] = pd.to_datetime(
        data["timestamp"],
        utc=True,
        errors="coerce"
    )

    for column in ("equity", "close"):
        data[column] = pd.to_numeric(
            data[column],
            errors="coerce"
        )

    if data.isna().any().any():
        raise ValueError("資料包含無效值")

    data = data.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    if data["timestamp"].duplicated().any():
        raise ValueError("交易日期不得重複")

    for column in ("equity", "close"):
        values = data[column].to_numpy(
            dtype=float
        )

        if (
            not np.isfinite(values).all()
            or (values <= 0).any()
        ):
            raise ValueError(
                f"{column}必須是有效的正數"
            )

    data["year"] = (
        data["timestamp"].dt.year
    )

    previous_equity = float(
        initial_capital
    )

    previous_close = float(
        data.iloc[0]["close"]
    )

    results = []

    for year, group in data.groupby(
        "year", sort=True
    ):
        ending_equity = float(
            group.iloc[-1]["equity"]
        )

        ending_close = float(
            group.iloc[-1]["close"]
        )

        strategy_return = (
            ending_equity / previous_equity - 1
        ) * 100

        buy_hold_return = (
            ending_close / previous_close - 1
        ) * 100

        difference = (
            strategy_return - buy_hold_return
        )

        # 把年初基準資產加入回撤計算，
        # 避免漏掉該年一開始的跌幅。
        equity_values = np.concatenate([
            [previous_equity],
            group["equity"].to_numpy(dtype=float)
        ])

        running_peak = np.maximum.accumulate(
            equity_values
        )

        drawdowns = (
            equity_values / running_peak - 1
        )

        max_drawdown = (
            float(drawdowns.min()) * 100
        )

        results.append({
            "year": int(year),
            "start_date": group.iloc[0][
                "timestamp"
            ].date().isoformat(),
            "end_date": group.iloc[-1][
                "timestamp"
            ].date().isoformat(),
            "trading_days": len(group),
            "strategy_return": strategy_return,
            "buy_hold_return": buy_hold_return,
            "excess_return": difference,
            "max_drawdown": max_drawdown,
            "ending_equity": ending_equity
        })

        previous_equity = ending_equity
        previous_close = ending_close

    return results


def format_yearly_report(
    yearly_results,
    symbol="股票"
):
    """轉換成 Telegram 文字報告。"""

    if not yearly_results:
        return "目前沒有年度績效資料。"

    lines = [
        f"📅 {symbol} 年度績效比較",
        ""
    ]

    for item in yearly_results:
        lines.extend([
            f"🗓 {item['year']}年",
            f"策略報酬："
            f"{item['strategy_return']:+.2f}%",
            f"買進持有："
            f"{item['buy_hold_return']:+.2f}%",
            f"報酬差距："
            f"{item['excess_return']:+.2f}個百分點",
            f"年度最大回撤："
            f"{item['max_drawdown']:.2f}%",
            f"年末／區間末資產："
            f"${item['ending_equity']:,.2f}",
            ""
        ])

    lines.extend([
        "📌 計算說明",
        "使用歷史回測的每日總資產及收盤價。",
        "第一年與最後一年可能是不完整年度。",
        "報酬是各年度實際涵蓋區間的報酬，"
        "不是年化報酬。",
        "第一年的買進持有比較以首日收盤價為基準。",
        "後續年度使用前一年度最後交易日為基準。",
        "年度最大回撤包含年初基準資產。",
        "未平倉部位按每日收盤價納入總資產。"
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    print(
        "年度績效模組已載入，"
        "請執行 test_yearly_performance.py"
    )
