
"""美股策略 A/B 對照回測。"""

from copy import deepcopy
from unittest.mock import patch

import pandas as pd

import universal_backtest as backtest
from market_data import get_stock_data
from performance_metrics import calculate_performance_metrics
from strategy_validator import validate_strategy


def compare_strategies(strategy_a, strategy_b):
    """
    以同一份歷史資料比較兩個策略。

    要求：
    1. 股票代號相同
    2. 回測年數相同
    3. 使用同一份資料與交易成本模型

    不會修改原本的策略。
    """

    a = deepcopy(strategy_a)
    b = deepcopy(strategy_b)

    validate_strategy(a)
    validate_strategy(b)

    if a["symbol"] != b["symbol"]:
        raise ValueError(
            "A/B比較必須使用同一檔股票"
        )

    if a["years"] != b["years"]:
        raise ValueError(
            "A/B比較必須使用相同回測年數"
        )

    symbol = a["symbol"]
    years = a["years"]

    # 只下載一次資料
    shared_data = get_stock_data(
        symbol,
        years
    )

    if (
        not isinstance(shared_data, pd.DataFrame)
        or shared_data.empty
    ):
        raise ValueError("歷史資料為空")

    # 每次回測拿到獨立副本，
    # 避免第一個策略修改第二個策略的資料
    def provide_shared_data(*args, **kwargs):
        return shared_data.copy(deep=True)

    with patch.object(
        backtest,
        "get_stock_data",
        side_effect=provide_shared_data
    ):
        df_a, trades_a, stats_a = (
            backtest.run_universal_backtest(a)
        )

        df_b, trades_b, stats_b = (
            backtest.run_universal_backtest(b)
        )

    # 確保兩個策略實際使用相同交易日期
    dates_a = pd.to_datetime(
        df_a["timestamp"],
        utc=True
    ).reset_index(drop=True)

    dates_b = pd.to_datetime(
        df_b["timestamp"],
        utc=True
    ).reset_index(drop=True)

    if not dates_a.equals(dates_b):
        raise ValueError(
            "兩個策略的交易日期不同，"
            "無法進行公平比較"
        )

    metrics_a = calculate_performance_metrics(
        df_a,
        trades_a
    )

    metrics_b = calculate_performance_metrics(
        df_b,
        trades_b
    )

    # A、B差異：B減A
    differences = {
        "total_return": (
            stats_b["total_return"]
            - stats_a["total_return"]
        ),
        "cagr": (
            metrics_b["cagr"]
            - metrics_a["cagr"]
        ),
        "max_drawdown": (
            stats_b["max_drawdown"]
            - stats_a["max_drawdown"]
        ),
        "win_rate": (
            stats_b["win_rate"]
            - stats_a["win_rate"]
        ),
        "trade_count": (
            stats_b["trade_count"]
            - stats_a["trade_count"]
        ),
        "final_equity": (
            stats_b["final_equity"]
            - stats_a["final_equity"]
        ),
    }

    sharpe_a = metrics_a["sharpe_ratio"]
    sharpe_b = metrics_b["sharpe_ratio"]

    differences["sharpe_ratio"] = (
        sharpe_b - sharpe_a
        if sharpe_a is not None
        and sharpe_b is not None
        else None
    )

    return {
        "symbol": symbol,
        "years": years,
        "strategy_a": a,
        "strategy_b": b,
        "df_a": df_a,
        "df_b": df_b,
        "trades_a": trades_a,
        "trades_b": trades_b,
        "stats_a": stats_a,
        "stats_b": stats_b,
        "metrics_a": metrics_a,
        "metrics_b": metrics_b,
        "differences": differences,
    }


def format_ab_report(result):
    """將 A/B 比較結果整理成 Telegram 文字。"""

    a = result["stats_a"]
    b = result["stats_b"]

    ma = result["metrics_a"]
    mb = result["metrics_b"]

    diff = result["differences"]

    def pct(value):
        if value is None:
            return "無法計算"
        return f"{value:+.2f}%"

    def number(value):
        if value is None:
            return "無法計算"
        return f"{value:.2f}"

    def money(value):
        return f"${value:,.2f}"

    lines = [
        f"⚖️ {result['symbol']} 策略A/B比較",
        f"回測期間：{result['years']}年",
        "",
        "📘 策略 A",
        f"總報酬：{pct(a['total_return'])}",
        f"CAGR：{pct(ma['cagr'])}",
        f"Sharpe：{number(ma['sharpe_ratio'])}",
        f"最大回撤：{pct(a['max_drawdown'])}",
        f"勝率：{a['win_rate']:.2f}%",
        f"交易次數：{a['trade_count']}",
        f"期末資產：{money(a['final_equity'])}",
        "",
        "📗 策略 B",
        f"總報酬：{pct(b['total_return'])}",
        f"CAGR：{pct(mb['cagr'])}",
        f"Sharpe：{number(mb['sharpe_ratio'])}",
        f"最大回撤：{pct(b['max_drawdown'])}",
        f"勝率：{b['win_rate']:.2f}%",
        f"交易次數：{b['trade_count']}",
        f"期末資產：{money(b['final_equity'])}",
        "",
        "🔎 B 相對 A 的差異",
        f"總報酬："
        f"{diff['total_return']:+.2f}個百分點",
        f"CAGR："
        f"{diff['cagr']:+.2f}個百分點",
        f"最大回撤數值差："
        f"{diff['max_drawdown']:+.2f}個百分點",
        f"Sharpe差異："
        f"{number(diff['sharpe_ratio'])}",
        f"交易次數差："
        f"{diff['trade_count']:+d}筆",
        f"期末資產差："
        f"${diff['final_equity']:+,.2f}",
        "",
    ]

    if diff["total_return"] > 0:
        lines.append(
            "📈 策略B的總報酬高於策略A。"
        )
    elif diff["total_return"] < 0:
        lines.append(
            "📉 策略B的總報酬低於策略A。"
        )
    else:
        lines.append(
            "➖ 兩個策略的總報酬相同。"
        )

    if diff["max_drawdown"] > 0:
        lines.append(
            "策略B的最大回撤較小。"
        )
    elif diff["max_drawdown"] < 0:
        lines.append(
            "策略B的最大回撤較大。"
        )

    lines.extend([
        "",
        "📌 比較說明",
        "兩個策略使用同一份歷史股價資料。",
        "最大回撤越接近0，代表回撤幅度越小。",
        "未平倉部位已納入總資產，"
        "但不列入已完成交易。",
        "此為歷史模擬，不能保證未來績效。",
        "若反覆挑選表現最好的參數，"
        "仍可能發生過度擬合。"
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    print(
        "A/B比較模組已載入，"
        "請執行 test_strategy_ab_comparison.py"
    )
