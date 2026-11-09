
"""美股回測交易品質分析。"""

import math
from collections import defaultdict

from telegram_performance import add_realized_pnl


def valid_number(value):
    return (
        type(value) in (int, float)
        and math.isfinite(value)
    )


def analyze_trades(trades, initial_capital=10000.0):
    """
    分析已完成的交易。

    目前支援：
    - 單一股票
    - 全額投入
    - 沒有槓桿、分批交易及出入金

    未平倉交易不計入勝率與實現損益。
    """

    if not isinstance(trades, list):
        raise ValueError("交易紀錄必須是list")

    if (
        not valid_number(initial_capital)
        or initial_capital <= 0
    ):
        raise ValueError("初始資金必須大於0")

    completed = add_realized_pnl(
        trades,
        initial_capital=initial_capital
    )

    # 檢查並整理交易紀錄
    normalized = []

    for index, trade in enumerate(completed):
        trade_return = trade.get("return_pct")
        pnl = trade.get("realized_pnl")
        reason = trade.get("reason", "未分類")

        if not valid_number(trade_return):
            raise ValueError("交易報酬率不合法")

        if not valid_number(pnl):
            raise ValueError("實現損益不合法")

        if not isinstance(reason, str):
            raise ValueError("出場原因格式錯誤")

        reason = reason.strip() or "未分類"

        normalized.append({
            "index": index,
            "return_pct": float(trade_return),
            "realized_pnl": float(pnl),
            "reason": reason,
        })

    if not normalized:
        return {
            "trade_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "breakeven_count": 0,
            "win_rate": None,
            "average_return": None,
            "best_return": None,
            "worst_return": None,
            "net_realized_pnl": 0.0,
            "max_consecutive_losses": 0,
            "exit_reasons": [],
        }

    win_count = sum(
        trade["realized_pnl"] > 0
        for trade in normalized
    )

    loss_count = sum(
        trade["realized_pnl"] < 0
        for trade in normalized
    )

    breakeven_count = (
        len(normalized) - win_count - loss_count
    )

    # 依照回測產生的交易順序計算
    # 連續虧損；損益為零時中斷
    losing_streak = 0
    max_losing_streak = 0

    for trade in normalized:
        if trade["realized_pnl"] < 0:
            losing_streak += 1
            max_losing_streak = max(
                max_losing_streak,
                losing_streak
            )
        else:
            losing_streak = 0

    # 按出場原因分組
    groups = defaultdict(list)

    for trade in normalized:
        groups[trade["reason"]].append(trade)

    exit_reasons = []

    for reason, items in groups.items():
        count = len(items)

        wins = sum(
            item["realized_pnl"] > 0
            for item in items
        )

        losses = sum(
            item["realized_pnl"] < 0
            for item in items
        )

        returns = [
            item["return_pct"]
            for item in items
        ]

        pnls = [
            item["realized_pnl"]
            for item in items
        ]

        exit_reasons.append({
            "reason": reason,
            "count": count,
            "win_count": wins,
            "loss_count": losses,
            "win_rate": wins / count * 100,
            "average_return": (
                sum(returns) / count
            ),
            "best_return": max(returns),
            "worst_return": min(returns),
            "net_realized_pnl": sum(pnls),
        })

    # 最常出現的原因排在前面
    exit_reasons.sort(
        key=lambda item: (
            -item["count"],
            item["reason"]
        )
    )

    returns = [
        trade["return_pct"]
        for trade in normalized
    ]

    return {
        "trade_count": len(normalized),
        "win_count": win_count,
        "loss_count": loss_count,
        "breakeven_count": breakeven_count,
        "win_rate": (
            win_count / len(normalized) * 100
        ),
        "average_return": (
            sum(returns) / len(returns)
        ),
        "best_return": max(returns),
        "worst_return": min(returns),
        "net_realized_pnl": sum(
            trade["realized_pnl"]
            for trade in normalized
        ),
        "max_consecutive_losses": (
            max_losing_streak
        ),
        "exit_reasons": exit_reasons,
    }


def format_trade_analytics(result, symbol="股票"):
    """輸出 Telegram 可閱讀的交易分析報告。"""

    if result["trade_count"] == 0:
        return (
            f"🔬 {symbol} 交易品質分析\n\n"
            "目前沒有已完成交易。\n"
            "未平倉部位不列入交易勝率統計。"
        )

    def pct(value):
        return f"{value:+.2f}%"

    def money(value):
        return f"${value:+,.2f}"

    lines = [
        f"🔬 {symbol} 交易品質分析",
        "",
        "📊 整體交易表現",
        f"完成交易：{result['trade_count']}筆",
        f"獲利交易：{result['win_count']}筆",
        f"虧損交易：{result['loss_count']}筆",
        f"損益兩平：{result['breakeven_count']}筆",
        f"勝率：{result['win_rate']:.2f}%",
        f"平均單筆報酬：{pct(result['average_return'])}",
        f"最佳交易：{pct(result['best_return'])}",
        f"最差交易：{pct(result['worst_return'])}",
        f"最大連續虧損："
        f"{result['max_consecutive_losses']}筆",
        f"累計已實現損益："
        f"{money(result['net_realized_pnl'])}",
        "",
        "📋 出場原因分析",
    ]

    for item in result["exit_reasons"]:
        lines.extend([
            "",
            f"▸ {item['reason']}",
            f"觸發次數：{item['count']}筆",
            f"勝率：{item['win_rate']:.2f}%",
            f"平均報酬：{pct(item['average_return'])}",
            f"已實現損益："
            f"{money(item['net_realized_pnl'])}",
        ])

    lines.extend([
        "",
        "📌 分析說明",
        "只統計已完成交易，"
        "未平倉損益不包含在已實現損益內。",
        "美元損益依全額投入的複利模型還原，"
        "已包含回測交易報酬中的模擬成本。",
        "單一出場原因的勝率高低，"
        "不代表該出場規則對整體績效的因果貢獻。"
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    print(
        "交易品質模組已載入，"
        "請執行 test_trade_analytics.py"
    )
