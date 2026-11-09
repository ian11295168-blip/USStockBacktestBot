
import io
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


def create_backtest_chart(df, stats, symbol):
    dates = df["timestamp"]

    # 策略每日資產
    strategy_equity = df["equity"]

    # 同樣以10000美元起始的買進持有
    buy_hold_equity = (
        df["close"]
        / df["close"].iloc[0]
        * 10000
    )

    fig, ax = plt.subplots(figsize=(11, 6))

    ax.plot(
        dates,
        strategy_equity,
        label="AI Strategy",
        linewidth=2
    )

    ax.plot(
        dates,
        buy_hold_equity,
        label="Buy & Hold",
        linewidth=2,
        linestyle="--"
    )

    ax.set_title(
        f"{symbol} - Backtest Performance",
        fontsize=16
    )

    ax.set_xlabel("Date")
    ax.set_ylabel("Portfolio Value (USD)")

    ax.grid(True, alpha=0.3)
    ax.legend()

    info = (
        f"Strategy: {stats['total_return']:+.2f}%    "
        f"Buy & Hold: {stats['buy_hold_return']:+.2f}%\n"
        f"Max Drawdown: {stats['max_drawdown']:.2f}%"
    )

    fig.text(
        0.5, 0.015, info,
        ha="center",
        fontsize=11
    )

    fig.autofmt_xdate()
    fig.tight_layout(rect=[0, 0.08, 1, 1])

    image = io.BytesIO()
    fig.savefig(
        image,
        format="png",
        dpi=150
    )

    image.seek(0)
    plt.close(fig)

    return image
