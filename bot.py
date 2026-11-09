
import os
import asyncio
import logging

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from ai_parser import parse_strategy
from backtest import run_strategy_backtest
from chart import create_backtest_chart

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 美股 AI 策略回測機器人\n\n"
        "直接輸入中文交易策略即可回測。\n\n"
        "例如：\n"
        "NVDA 10日線上穿50日線買進，"
        "下穿賣出，停損7%，回測3年。\n\n"
        "也支援：\n"
        "AAPL RSI14低於30買進，"
        "高於70賣出，回測5年。\n\n"
        "目前支援 MA交叉、RSI、停損及停利。"
    )


def execute_backtest(text):
    # AI 理解中文
    strategy = parse_strategy(text)

    # 回測引擎驗證策略並執行
    df, trades, stats = run_strategy_backtest(strategy)

    return strategy, df, trades, stats


async def message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    message = update.effective_message
    text = message.text.strip()

    if len(text) > 1000:
        await message.reply_text(
            "策略文字太長，請縮短至1000字以內。"
        )
        return

    await message.reply_text(
        "🤖 AI 正在解析策略並執行歷史回測..."
    )

    try:
        strategy, df, trades, stats = (
            await asyncio.to_thread(
                execute_backtest, text
            )
        )
        context.user_data["last_trades"] = trades
        context.user_data["last_symbol"] = strategy["symbol"]
        context.user_data["last_df"] = df
        context.user_data["last_stats"] = stats

        symbol = strategy["symbol"]
        years = strategy["years"]
        print("Telegram收到的欄位：", df.columns.tolist())
        if strategy["strategy_type"] == "ma_cross":
            strategy_name = (
                f"MA{strategy['fast_ma']} / "
                f"MA{strategy['slow_ma']}"
            )
        else:
            strategy_name = (
                f"RSI{strategy['rsi_period']} "
                f"買入<{strategy['rsi_buy']} "
                f"賣出>{strategy['rsi_sell']}"
            )

        stop = strategy.get("stop_loss")
        target = strategy.get("take_profit")

        stop_text = (
            f"{stop}%" if stop is not None else "無"
        )
        target_text = (
            f"{target}%" if target is not None else "無"
        )

        start_date = str(
            df.iloc[0]["timestamp"]
        )[:10]

        end_date = str(
            df.iloc[-1]["timestamp"]
        )[:10]

        result = (
            f"📊 {symbol} AI 策略回測\n\n"
            f"📌 策略：{strategy_name}\n"
            f"停損：{stop_text}\n"
            f"停利：{target_text}\n"
            f"回測設定：{years}年\n"
            f"實際資料：{start_date} ～ {end_date}\n\n"
            f"📈 回測績效\n\n"
            f"交易次數：{stats['trade_count']}\n"
            f"勝率：{stats['win_rate']:.2f}%\n\n"
            f"策略總報酬：{stats['total_return']:+.2f}%\n"
            f"Buy & Hold：{stats['buy_hold_return']:+.2f}%\n"
            f"最大回撤：{stats['max_drawdown']:.2f}%\n\n"
            f"平均獲利：{stats['average_win']:.2f}%\n"
            f"平均虧損：{stats['average_loss']:.2f}%\n"
            f"最佳交易：{stats['best_trade']:.2f}%\n"
            f"最差交易：{stats['worst_trade']:.2f}%\n\n"
            f"期末持倉："
            f"{'有' if stats['open_position'] else '無'}\n"
            f"資料：Alpaca IEX 日K\n"
            f"包含模擬交易成本及滑價\n"
            f"歷史績效不代表未來結果"
        )

        await message.reply_text(result)

    except ValueError as e:
        await message.reply_text(
            f"⚠️ 策略設定有問題：{e}"
        )

    except Exception:
        logger.exception("AI 回測失敗")
        await message.reply_text(
            "❌ 回測失敗。\n"
            "請檢查 API 額度、資料連線或策略格式。\n"
            "詳細錯誤可在 VS Code 終端機查看。"
        )


async def show_trades(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    trades = context.user_data.get("last_trades")
    symbol = context.user_data.get("last_symbol", "")

    if trades is None:
        await update.message.reply_text(
            "請先輸入中文策略，完成一次回測。"
        )
        return

    if len(trades) == 0:
        await update.message.reply_text(
            f"{symbol} 這次回測沒有已完成交易。"
        )
        return

    messages = []
    current = f"📊 {symbol} 交易明細\n"

    for i, trade in enumerate(trades, 1):
        buy_date = str(trade["buy_date"])[:10]
        sell_date = str(trade["sell_date"])[:10]

        detail = (
            f"\n第 {i} 筆\n"
            f"買進：{buy_date}\n"
            f"買進價：${trade['buy_price']:.2f}\n"
            f"賣出：{sell_date}\n"
            f"賣出價：${trade['sell_price']:.2f}\n"
            f"報酬：{trade['return_pct']:+.2f}%\n"
            f"原因：{trade['reason']}\n"
        )

        # 避免超過 Telegram 訊息長度限制
        if len(current) + len(detail) > 3500:
            messages.append(current)
            current = f"📊 {symbol} 交易明細（續）\n"

        current += detail

    messages.append(current)

    for message in messages:
        await update.message.reply_text(message)

async def show_chart(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    df = context.user_data.get("last_df")
    stats = context.user_data.get("last_stats")
    symbol = context.user_data.get("last_symbol")

    if df is None or stats is None:
        await update.message.reply_text(
            "請先完成一次策略回測，再輸入 /chart"
        )
        return

    await update.message.reply_text(
        "📈 正在產生績效曲線圖..."
    )

    try:
        image = await asyncio.to_thread(
            create_backtest_chart,
            df,
            stats,
            symbol
        )

        try:
            await update.message.reply_photo(
                photo=image,
                caption=(
                    f"📊 {symbol} 回測績效曲線\n"
                    f"策略：{stats['total_return']:+.2f}%\n"
                    f"Buy & Hold：{stats['buy_hold_return']:+.2f}%\n"
                    f"最大回撤：{stats['max_drawdown']:.2f}%"
                )
            )
        finally:
            image.close()

    except Exception:
        logger.exception("無法產生回測圖表")
        await update.message.reply_text(
            "❌ 圖表產生失敗，請查看終端機錯誤。"
        )

def main():
    if not TOKEN:
        raise ValueError(
            ".env 找不到 TELEGRAM_BOT_TOKEN"
        )

    app = Application.builder().token(TOKEN).build()

    app.add_handler(
        CommandHandler("start", start)
    )
    app.add_handler(
        CommandHandler("trades", show_trades)
    )
    app.add_handler(
        CommandHandler("chart", show_chart)
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            message_handler
        )
    )

    print("Telegram AI Backtest Bot running...")

    app.run_polling()


if __name__ == "__main__":
    main()
