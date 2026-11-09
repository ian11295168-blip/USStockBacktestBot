
import math

from performance_metrics import calculate_performance_metrics


def add_realized_pnl(trades, initial_capital=10000.0):
    """
    依照目前回測引擎的全額投入模型，
    還原每一筆已完成交易的美元損益。

    前提：
    1. 每次只持有一檔股票
    2. 每次投入全部可用資金
    3. 沒有出入金、槓桿或分批交易
    4. return_pct已包含交易成本
    """

    capital = float(initial_capital)
    result = []

    for trade in trades:
        item = dict(trade)

        if "return_pct" not in item:
            raise ValueError(
                "交易紀錄缺少return_pct"
            )

        trade_return = float(item["return_pct"])

        if not math.isfinite(trade_return):
            raise ValueError(
                "交易報酬率不合法"
            )

        if trade_return <= -100:
            raise ValueError(
                "單筆交易報酬不得低於或等於-100%"
            )

        pnl = capital * trade_return / 100

        item["realized_pnl"] = pnl

        capital += pnl
        result.append(item)

    return result


def build_telegram_performance_report(
    df,
    trades,
    stats,
    initial_capital=10000.0
):
    """建立可直接傳送Telegram的進階績效報告。"""

    if not isinstance(stats, dict):
        raise ValueError("stats必須是字典")

    completed_trades = add_realized_pnl(
        trades,
        initial_capital=initial_capital
    )

    metrics = calculate_performance_metrics(
        df,
        completed_trades,
        risk_free_rate=0.0
    )

    # 計算與買進持有同期的年化報酬比較
    benchmark_return = stats.get(
        "buy_hold_return"
    )

    benchmark_cagr = None
    excess_return = None

    if benchmark_return is not None:
        benchmark_return = float(
            benchmark_return
        )

        if not math.isfinite(benchmark_return):
            raise ValueError(
                "買進持有報酬不合法"
            )

        benchmark_growth = (
            1 + benchmark_return / 100
        )

        if benchmark_growth > 0:
            benchmark_cagr = (
                benchmark_growth ** (
                    1 / metrics["elapsed_years"]
                ) - 1
            ) * 100

        excess_return = (
            metrics["total_return"]
            - benchmark_return
        )

    def fmt_percent(value):
        if value is None:
            return "無法計算"
        return f"{value:+.2f}%"

    def fmt_number(value):
        if value is None:
            return "無法計算"
        return f"{value:.2f}"

    def fmt_money(value):
        return f"${value:,.2f}"

    profit_factor = metrics["profit_factor"]

    if profit_factor is None:
        profit_factor_text = "無法計算"
    else:
        profit_factor_text = fmt_number(
            profit_factor
        )

    symbol = (
        stats.get("symbol")
        or "股票策略"
    )

    text = (
        f"📊 {symbol} 進階績效報告\n\n"
        "📈 報酬比較\n"
        f"策略總報酬："
        f"{fmt_percent(metrics['total_return'])}\n"
        f"策略CAGR："
        f"{fmt_percent(metrics['cagr'])}\n"
        f"買進持有總報酬："
        f"{fmt_percent(benchmark_return)}\n"
        f"買進持有CAGR："
        f"{fmt_percent(benchmark_cagr)}\n"
        f"總報酬差距："
        f"{fmt_percent(excess_return)}\n\n"
        "📉 風險指標\n"
        f"Sharpe Ratio："
        f"{fmt_number(metrics['sharpe_ratio'])}\n"
        f"年化波動率："
        f"{fmt_percent(metrics['annual_volatility'])}\n"
        f"最大回撤："
        f"{fmt_percent(metrics['max_drawdown'])}\n\n"
        "💰 交易品質\n"
        f"已完成交易："
        f"{metrics['trade_count']}筆\n"
        f"勝率："
        f"{fmt_percent(metrics['win_rate'])}\n"
        f"平均單筆報酬："
        f"{fmt_percent(metrics['average_trade_return'])}\n"
        f"Profit Factor："
        f"{profit_factor_text}\n\n"
        f"期末資產："
        f"{fmt_money(metrics['final_equity'])}\n\n"
        "資料說明：Sharpe使用0%無風險利率；"
        "Profit Factor根據目前全額投入模型"
        "還原已實現美元損益。"
        "未平倉部位納入期末資產，"
        "但不列入已完成交易。"
    )

    return text, metrics, completed_trades
