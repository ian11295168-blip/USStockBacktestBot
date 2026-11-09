
"""美股 AI 策略回測機器人 — MVP v1.0 顯示修正版。"""

import asyncio
import json
import logging
import os
import re
from copy import deepcopy

from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from database import (
    load_state,
    save_state,
    save_backtest,
    get_latest_backtest,
)

from universal_ai_parser import parse_universal_strategy
from universal_backtest import run_universal_backtest
from intent_router import detect_intent
from strategy_summary_v2 import format_strategy_summary
from strategy_diff import format_strategy_diff

from chart import create_backtest_chart

from telegram_performance import (
    build_telegram_performance_report,
)

from yearly_performance import (
    calculate_yearly_performance,
    format_yearly_report,
)

from trade_analytics import (
    analyze_trades,
    format_trade_analytics,
)

from strategy_ab_comparison import (
    compare_strategies,
    format_ab_report,
)

from out_of_sample import (
    analyze_out_of_sample,
    format_oos_report,
)

from strategy_version_manager import (
    make_pending_undo,
    make_pending_strategy,
    commit_pending,
    cancel_pending,
)


load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = os.getenv("TELEGRAM_OWNER_ID")

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def allowed(update):
    user = update.effective_user

    return (
        user is not None
        and bool(OWNER_ID)
        and str(user.id) == OWNER_ID
    )


def restore_memory(update, context):
    if context.user_data.get("_memory_loaded"):
        return

    saved = load_state(update.effective_user.id)

    if saved:
        context.user_data.update(saved)

    context.user_data["_memory_loaded"] = True


def persist_memory(update, context):
    save_state(
        update.effective_user.id,
        context.user_data,
    )


def confirmation_keyboard(request_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ 確認回測",
                callback_data=f"run:{request_id}",
            ),
            InlineKeyboardButton(
                "✏️ 修改策略",
                callback_data=f"edit:{request_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                "❌ 取消提案",
                callback_data=f"cancel:{request_id}",
            ),
        ],
    ])


async def send_long_text(
    message,
    text,
    limit=3500,
    reply_markup=None,
):
    chunks = [
        text[i:i + limit]
        for i in range(0, len(text), limit)
    ] or [""]

    for index, chunk in enumerate(chunks):
        await message.reply_text(
            chunk,
            reply_markup=(
                reply_markup
                if index == len(chunks) - 1
                else None
            ),
        )


def unclear_volume(text):
    vague_words = (
        "成交量萎縮",
        "成交量縮小",
        "成交量減少",
        "量縮",
    )

    if not any(word in text for word in vague_words):
        return False

    definitions = (
        r"連續\s*\d+\s*天.{0,12}"
        r"(?:比前一天少|減少|下降|萎縮)|"
        r"(?:成交量|量)\s*低於\s*\d+\s*日均量|"
        r"(?:成交量|量)\s*連續\s*\d+\s*天"
    )

    return re.search(definitions, text) is None


# =========================================
# 新增：策略顯示與交易設定顯示
# =========================================

def format_current_strategy_status(user_data):
    """
    分開顯示已確認策略和待確認策略。
    不再讓使用者誤以為 pending 已經正式生效。
    """

    confirmed = user_data.get("last_strategy")
    pending = user_data.get("pending")

    sections = ["📋 目前策略狀態"]

    if isinstance(confirmed, dict):
        sections.extend([
            "",
            "✅ 已確認策略",
            format_strategy_summary(confirmed),
        ])
    else:
        sections.extend([
            "",
            "✅ 已確認策略",
            "目前沒有已確認策略。",
        ])

    if isinstance(pending, dict):
        proposed = pending.get("strategy")
        kind = pending.get("kind")

        if kind == "undo":
            heading = "↩️ 待確認的復原提案"
        elif kind == "modify":
            heading = "📝 待確認的修改策略"
        elif kind == "new":
            heading = "📝 待確認的新策略"
        else:
            heading = "📝 待確認策略"

        sections.extend([
            "",
            "━━━━━━━━━━━━",
            "",
            heading,
        ])

        if isinstance(proposed, dict):
            sections.append(
                format_strategy_summary(proposed)
            )
        else:
            sections.append(
                "待確認策略資料格式錯誤。"
            )

        sections.extend([
            "",
            "⚠️ 此提案尚未正式確認。",
            "確認回測成功後才會變成已確認策略。",
            "輸入 /cancel 可取消提案。",
        ])

    else:
        sections.extend([
            "",
            "📌 目前沒有待確認提案。",
        ])

    return "\n".join(sections)


def decode_strategy(value):
    """
    解析資料庫中可能以 dict 或 JSON 字串
    儲存的策略設定。
    """

    if isinstance(value, dict):
        return deepcopy(value)

    if isinstance(value, str):
        try:
            decoded = json.loads(value)

            if isinstance(decoded, dict):
                return decoded
        except (ValueError, TypeError):
            pass

    return None


def get_record_strategy(record):
    """
    只讀取該筆回測紀錄真正保存的策略。
    不拿目前 last_strategy 冒充舊回測設定。
    """

    if not isinstance(record, dict):
        return None

    for key in (
        "strategy",
        "strategy_json",
    ):
        strategy = decode_strategy(
            record.get(key)
        )

        if strategy is not None:
            return strategy

    return None


def format_percentage_setting(value):
    """
    停損和停利設定顯示。
    None 表示沒有設定。
    """

    if value is None:
        return "未設定"

    try:
        number = float(value)
    except (ValueError, TypeError):
        return "無法辨識"

    return f"{number:g}%"


def format_backtest_settings(strategy):
    """
    顯示交易明細對應的回測設定。
    只根據該次回測的策略資料產生。
    """

    if not isinstance(strategy, dict):
        return (
            "⚙️ 回測設定\n"
            "此筆歷史紀錄未提供可確認的策略設定。\n"
            "請勿將目前策略當成此筆回測的設定。"
        )

    symbol = strategy.get("symbol", "未知")

    years = strategy.get("years")

    years_text = (
        f"{years}年"
        if years is not None
        else "未知"
    )

    stop_loss = format_percentage_setting(
        strategy.get("stop_loss")
    )

    trailing_stop = format_percentage_setting(
        strategy.get("trailing_stop_pct")
    )

    take_profit = format_percentage_setting(
        strategy.get("take_profit")
    )

    max_hold = strategy.get("max_hold_days")

    max_hold_text = (
        f"{max_hold}天"
        if max_hold is not None
        else "未設定"
    )

    return (
        "⚙️ 本次回測使用的設定\n"
        f"股票：{symbol}\n"
        f"回測期間：{years_text}\n"
        f"固定停損：{stop_loss}\n"
        f"追蹤停損：{trailing_stop}\n"
        f"固定停利：{take_profit}\n"
        f"最長持有天數：{max_hold_text}"
    )


def get_comparison_pair(user_data):
    history = (
        user_data.get("strategy_history") or []
    )
    pending = user_data.get("pending")
    confirmed = user_data.get("last_strategy")

    if isinstance(pending, dict):
        kind = pending.get("kind")

        if kind == "undo":
            raise ValueError(
                "目前有復原提案，請先確認或取消。"
            )

        if kind == "new":
            raise ValueError(
                "目前是全新策略，沒有上一版可比較。"
            )

        if kind == "modify":
            strategy_a = deepcopy(
                pending.get("base_strategy")
            )
            strategy_b = deepcopy(
                pending.get("strategy")
            )
            status = "pending"

        elif kind is None:
            if (
                pending.get("text")
                == "恢復上一版策略"
            ):
                raise ValueError(
                    "舊版復原提案請先使用 /cancel。"
                )

            if not history:
                raise ValueError(
                    "舊版提案缺少修改前策略，"
                    "請取消後重新修改。"
                )

            strategy_a = deepcopy(
                history[-1]
            )
            strategy_b = deepcopy(
                pending.get("strategy")
            )
            status = "pending"

        else:
            raise ValueError(
                "無法辨識待確認策略的版本類型。"
            )

    else:
        if not history:
            raise ValueError(
                "沒有可比較的上一版策略。"
                "請先修改目前的策略。"
            )

        strategy_a = deepcopy(history[-1])
        strategy_b = deepcopy(confirmed)
        status = "confirmed"

    if not isinstance(strategy_a, dict):
        raise ValueError("修改前策略不存在")

    if not isinstance(strategy_b, dict):
        raise ValueError("修改後策略不存在")

    if strategy_a == strategy_b:
        raise ValueError(
            "兩個策略內容相同，無法比較。"
        )

    return strategy_a, strategy_b, status


def get_backtest_lock(context):
    lock = context.application.bot_data.get(
        "_backtest_lock"
    )

    if lock is None:
        lock = asyncio.Lock()

        context.application.bot_data[
            "_backtest_lock"
        ] = lock

    return lock


async def myid(update, context):
    await update.message.reply_text(
        "你的 Telegram User ID："
        f"{update.effective_user.id}\n"
        "請填入 .env 的 TELEGRAM_OWNER_ID。"
    )


async def start(update, context):
    if not allowed(update):
        await update.message.reply_text(
            "尚未授權，請先使用 /myid。"
        )
        return

    await update.message.reply_text(
        "🤖 美股 AI 策略回測機器人\n\n"
        "直接用中文描述交易策略，"
        "確認後才會進行歷史回測。\n\n"
        "📌 可用指令\n"
        "/trades 交易明細與回測設定\n"
        "/chart 績效曲線\n"
        "/yearly 年度績效\n"
        "/analyze 交易品質分析\n"
        "/compare 策略 A/B 比較\n"
        "/oos 樣本內／外績效\n"
        "/undo 預覽上一版策略\n"
        "/cancel 取消待確認提案\n"
        "/start 使用說明\n\n"
        "直接輸入「查看目前策略」"
        "可分別查看已確認與待確認版本。"
    )


async def undo_strategy(update, context):
    if not allowed(update):
        await update.message.reply_text(
            "未授權使用。"
        )
        return

    restore_memory(update, context)

    try:
        pending = make_pending_undo(
            context.user_data
        )

        persist_memory(update, context)

        await send_long_text(
            update.message,
            "↩️ 上一版策略預覽\n\n"
            + format_strategy_summary(
                pending["strategy"]
            )
            + "\n\n這只是預覽，"
            "目前已確認的策略尚未改變。\n"
            "回測成功後才正式復原。\n"
            "也可以輸入 /cancel 取消。",
            reply_markup=confirmation_keyboard(
                pending["id"]
            ),
        )

    except ValueError as exc:
        await update.message.reply_text(
            f"⚠️ 無法復原：{exc}"
        )

    except Exception:
        logger.exception(
            "策略復原提案失敗"
        )

        await update.message.reply_text(
            "❌ 復原提案失敗，請查看終端機。"
        )


async def cancel_strategy(update, context):
    if not allowed(update):
        await update.message.reply_text(
            "未授權使用。"
        )
        return

    restore_memory(update, context)

    if context.user_data.get(
        "_backtest_running"
    ):
        await update.message.reply_text(
            "目前正在回測，暫時無法取消。"
        )
        return

    if cancel_pending(context.user_data):
        try:
            persist_memory(update, context)

        except Exception:
            logger.exception(
                "取消提案儲存失敗"
            )

            await update.message.reply_text(
                "⚠️ 已取消目前提案，"
                "但 SQLite 儲存失敗。"
            )
            return

        await update.message.reply_text(
            "✅ 已取消待確認提案。\n"
            "已確認策略與歷史版本不變。"
        )

    else:
        await update.message.reply_text(
            "目前沒有待確認的策略。"
        )


async def handle_text(update, context):
    if not allowed(update):
        await update.message.reply_text(
            "未授權使用。"
        )
        return

    restore_memory(update, context)

    message = update.message
    text = (message.text or "").strip()

    if not text:
        return

    if len(text) > 1000:
        await message.reply_text(
            "策略文字請勿超過1000字。"
        )
        return

    if context.user_data.get(
        "_backtest_running"
    ):
        await message.reply_text(
            "目前正在回測，"
            "請完成後再修改策略。"
        )
        return

    pending = context.user_data.get(
        "pending"
    )
    last_strategy = context.user_data.get(
        "last_strategy"
    )
    incomplete = context.user_data.get(
        "incomplete_strategy"
    )
    history = context.user_data.get(
        "strategy_history", []
    )

    current_strategy = (
        pending.get("strategy")
        if isinstance(pending, dict)
        else last_strategy
    )

    # 新增：直接辨識常見的查看策略指令，
    # 避免 AI 把查詢誤判成修改。
    normalized = re.sub(
        r"\s+",
        "",
        text
    )

    show_commands = {
        "查看目前策略",
        "查看策略",
        "目前策略",
        "顯示目前策略",
        "顯示策略",
        "我的策略",
        "查詢目前策略",
    }

    if normalized in show_commands:
        await send_long_text(
            message,
            format_current_strategy_status(
                context.user_data
            ),
        )
        return

    await message.reply_text(
        "🧠 AI 正在理解你的指令..."
    )

    try:
        intent = await asyncio.to_thread(
            detect_intent,
            text,
            current_strategy is not None,
            incomplete is not None,
            bool(history),
        )

        if intent == "show":
            await send_long_text(
                message,
                format_current_strategy_status(
                    context.user_data
                ),
            )
            return

        if intent == "undo":
            await undo_strategy(
                update,
                context
            )
            return

        if intent == "unknown":
            await message.reply_text(
                "我不確定你想建立、修改或查詢策略，"
                "請再說明一次。"
            )
            return

        if intent == "clarify":
            if incomplete is None:
                await message.reply_text(
                    "目前沒有等待補充的策略。"
                )
                return

            strategy_text = (
                incomplete
                + "\n使用者補充說明："
                + text
            )

            base_strategy = None

        elif intent == "modify":
            if current_strategy is None:
                await message.reply_text(
                    "目前沒有可以修改的策略。"
                )
                return

            if (
                isinstance(pending, dict)
                and pending.get("kind") == "undo"
            ):
                await message.reply_text(
                    "目前正在預覽上一版策略。\n"
                    "請先輸入 /cancel，"
                    "再修改策略。"
                )
                return

            if (
                isinstance(pending, dict)
                and pending.get("kind") is None
            ):
                await message.reply_text(
                    "目前有舊格式的待確認策略。\n"
                    "請先使用 /cancel，"
                    "再重新修改。"
                )
                return

            strategy_text = text
            base_strategy = deepcopy(
                current_strategy
            )

        elif intent == "new":
            strategy_text = text
            base_strategy = None

        else:
            await message.reply_text(
                "目前不支援這個操作。"
            )
            return

        if unclear_volume(strategy_text):
            context.user_data[
                "incomplete_strategy"
            ] = strategy_text

            persist_memory(update, context)

            await message.reply_text(
                "請補充量縮的明確定義。\n"
                "例如：成交量連續2天比前一天少。\n"
                "直接回答即可。"
            )
            return

        strategy = await asyncio.to_thread(
            parse_universal_strategy,
            strategy_text,
            base_strategy,
        )

        diff_text = None

        if intent == "modify":
            diff_text = format_strategy_diff(
                base_strategy,
                strategy,
            )

            new_pending = make_pending_strategy(
                context.user_data,
                strategy,
                kind="modify",
                text=strategy_text,
            )

        else:
            new_pending = make_pending_strategy(
                context.user_data,
                strategy,
                kind="new",
                text=strategy_text,
            )

        context.user_data.pop(
            "incomplete_strategy",
            None
        )

        persist_memory(update, context)

        if diff_text:
            await send_long_text(
                message,
                diff_text
            )

        await send_long_text(
            message,
            format_strategy_summary(strategy)
            + "\n\n📝 尚未正式確認。"
            "可以先使用 /compare 比較，"
            "或輸入 /cancel 取消。",
            reply_markup=confirmation_keyboard(
                new_pending["id"]
            ),
        )

    except ValueError as exc:
        await message.reply_text(
            f"⚠️ 無法完成操作：{exc}"
        )

    except Exception:
        logger.exception(
            "AI 策略處理失敗"
        )

        await message.reply_text(
            "❌ AI 處理失敗，請查看終端機。"
        )


async def handle_button(update, context):
    query = update.callback_query

    await query.answer()

    if not allowed(update):
        await query.message.reply_text(
            "未授權使用。"
        )
        return

    restore_memory(update, context)

    action, request_id = query.data.split(
        ":", 1
    )

    pending = context.user_data.get(
        "pending"
    )

    if (
        not isinstance(pending, dict)
        or pending.get("id") != request_id
    ):
        await query.message.reply_text(
            "這是舊提案，已經無法使用。"
        )
        return

    if context.user_data.get(
        "_backtest_running"
    ):
        await query.message.reply_text(
            "回測正在執行，請勿重複操作。"
        )
        return

    if action == "cancel":
        cancel_pending(context.user_data)

        try:
            persist_memory(update, context)
        except Exception:
            logger.exception(
                "取消提案儲存失敗"
            )

        await query.edit_message_reply_markup(
            reply_markup=None
        )

        await query.message.reply_text(
            "✅ 已取消待確認策略。"
        )
        return

    if action == "edit":
        await query.edit_message_reply_markup(
            reply_markup=None
        )

        if pending.get("kind") == "undo":
            await query.message.reply_text(
                "目前是復原提案。\n"
                "請先使用 /cancel，"
                "再修改原本策略。"
            )
            return

        await query.message.reply_text(
            "✏️ 請直接告訴我想修改什麼。\n\n"
            "例如：\n"
            "追蹤停損改成8%\n"
            "固定停損改成5%\n"
            "持有期限改成10天\n\n"
            "其他條件會保留。"
        )
        return

    if action != "run":
        return

    if pending.get("kind") not in (
        "new",
        "modify",
        "undo",
    ):
        await query.message.reply_text(
            "⚠️ 這是舊格式的待確認策略。\n"
            "請使用 /cancel 再重新修改。"
        )
        return

    strategy = deepcopy(
        pending["strategy"]
    )

    context.user_data[
        "_backtest_running"
    ] = True

    await query.edit_message_reply_markup(
        reply_markup=None
    )

    await query.message.reply_text(
        f"📊 正在回測 {strategy['symbol']}..."
    )

    try:
        lock = get_backtest_lock(context)

        async with lock:
            df, trades, stats = await asyncio.to_thread(
                run_universal_backtest,
                strategy,
            )

        # 確認成功後才更新版本歷史
        commit_pending(
            context.user_data,
            request_id,
        )

    except Exception:
        logger.exception(
            "回測或版本確認失敗"
        )

        await query.message.reply_text(
            "❌ 回測或版本確認失敗。\n"
            "原本已確認的策略仍保留。"
        )

        if context.user_data.get("pending"):
            await query.message.reply_text(
                "目前提案仍保留。",
                reply_markup=confirmation_keyboard(
                    request_id
                ),
            )
        return

    finally:
        context.user_data.pop(
            "_backtest_running",
            None
        )

    context.user_data["last_df"] = df
    context.user_data["last_trades"] = trades
    context.user_data["last_stats"] = stats

    context.user_data[
        "last_symbol"
    ] = strategy["symbol"]

    # 新增：讓交易明細與實際回測策略綁定
    context.user_data[
        "last_backtest_strategy"
    ] = deepcopy(strategy)

    try:
        await asyncio.to_thread(
            save_backtest,
            update.effective_user.id,
            strategy,
            stats,
            trades,
        )

    except Exception:
        logger.exception(
            "回測紀錄寫入 SQLite 失敗"
        )

        await query.message.reply_text(
            "⚠️ 回測成功，"
            "但交易紀錄寫入資料庫失敗。"
        )

    try:
        persist_memory(update, context)

    except Exception:
        logger.exception(
            "策略狀態寫入 SQLite 失敗"
        )

        await query.message.reply_text(
            "⚠️ 策略已在目前執行階段確認，"
            "但版本狀態寫入資料庫失敗。"
        )

    result = (
        f"✅ {strategy['symbol']} "
        "策略已正式確認\n\n"
        f"交易次數：{stats['trade_count']}\n"
        f"勝率：{stats['win_rate']:.2f}%\n"
        f"策略報酬："
        f"{stats['total_return']:+.2f}%\n"
        f"Buy & Hold："
        f"{stats['buy_hold_return']:+.2f}%\n"
        f"最大回撤："
        f"{stats['max_drawdown']:.2f}%\n"
        f"期末資產："
        f"${stats['final_equity']:,.2f}\n"
        f"期末持倉："
        f"{'有' if stats['open_position'] else '無'}\n\n"
        "資料：Alpaca IEX 日K\n"
        "含模擬手續費與滑價\n\n"
        "/trades 交易明細及對應設定\n"
        "/chart 績效曲線\n"
        "/yearly 年度績效\n"
        "/analyze 交易品質\n"
        "/compare 策略 A/B 比較\n"
        "/oos 樣本內／外績效\n"
        "/undo 恢復上一版"
    )

    await query.message.reply_text(
        result
    )

    try:
        performance_stats = {
            **stats,
            "symbol": strategy["symbol"],
        }

        report, metrics, completed_trades = (
            await asyncio.to_thread(
                build_telegram_performance_report,
                df,
                trades,
                performance_stats,
            )
        )

        await send_long_text(
            query.message,
            report
        )

    except Exception:
        logger.exception(
            "進階績效報告失敗"
        )

        await query.message.reply_text(
            "⚠️ 回測完成，"
            "但進階績效報告產生失敗。"
        )


async def get_recent_trades(update, context):
    """
    返回：
        trades
        symbol
        backtest_strategy

    策略設定必須與交易紀錄屬於同一回測。
    """

    trades = context.user_data.get(
        "last_trades"
    )

    symbol = context.user_data.get(
        "last_symbol"
    )

    backtest_strategy = decode_strategy(
        context.user_data.get(
            "last_backtest_strategy"
        )
    )

    if trades is not None:
        return (
            trades,
            symbol,
            backtest_strategy
        )

    record = await asyncio.to_thread(
        get_latest_backtest,
        update.effective_user.id,
    )

    if record is None:
        return None, None, None

    trades = record["trades"]
    symbol = record["symbol"]

    # 只從這筆回測本身取得策略資訊
    backtest_strategy = get_record_strategy(
        record
    )

    context.user_data["last_trades"] = trades
    context.user_data["last_symbol"] = symbol
    context.user_data["last_stats"] = record["stats"]

    context.user_data[
        "last_backtest_strategy"
    ] = backtest_strategy

    return (
        trades,
        symbol,
        backtest_strategy
    )


async def show_trades(update, context):
    if not allowed(update):
        return

    restore_memory(update, context)

    try:
        trades, symbol, backtest_strategy = (
            await get_recent_trades(
                update,
                context,
            )
        )

        if trades is None:
            await update.message.reply_text(
                "目前沒有已儲存的回測紀錄。"
            )
            return

        report = (
            f"📋 {symbol or '股票'} 歷史交易明細\n\n"
            + format_backtest_settings(
                backtest_strategy
            )
        )

        if not trades:
            await send_long_text(
                update.message,
                report
                + "\n\n此策略沒有已完成交易。"
            )
            return

        report += "\n\n━━━━━━━━━━━━"

        for index, trade in enumerate(
            trades, 1
        ):
            part = (
                f"\n\n第{index}筆\n"
                f"買進："
                f"{str(trade['buy_date'])[:10]} "
                f"${trade['buy_price']:.2f}\n"
                f"賣出："
                f"{str(trade['sell_date'])[:10]} "
                f"${trade['sell_price']:.2f}\n"
                f"報酬："
                f"{trade['return_pct']:+.2f}%\n"
                f"原因：{trade['reason']}"
            )

            report += part

        await send_long_text(
            update.message,
            report
        )

    except Exception:
        logger.exception(
            "交易明細讀取失敗"
        )

        await update.message.reply_text(
            "❌ 交易明細讀取失敗，請查看終端機。"
        )


async def show_chart(update, context):
    if not allowed(update):
        return

    df = context.user_data.get(
        "last_df"
    )

    stats = context.user_data.get(
        "last_stats"
    )

    symbol = context.user_data.get(
        "last_symbol"
    )

    if df is None or stats is None:
        await update.message.reply_text(
            "請先完成一次回測。\n"
            "重新啟動後需要重新回測才能查看圖表。"
        )
        return

    try:
        chart_image = await asyncio.to_thread(
            create_backtest_chart,
            df,
            stats,
            symbol,
        )

        try:
            await update.message.reply_photo(
                photo=chart_image,
                caption=(
                    f"{symbol} 策略績效曲線"
                ),
            )

        finally:
            chart_image.close()

    except Exception:
        logger.exception(
            "績效圖表失敗"
        )

        await update.message.reply_text(
            "❌ 圖表產生失敗。"
        )


async def show_yearly(update, context):
    if not allowed(update):
        return

    restore_memory(update, context)

    df = context.user_data.get(
        "last_df"
    )

    symbol = context.user_data.get(
        "last_symbol"
    )

    if df is None:
        await update.message.reply_text(
            "目前沒有每日資產資料。\n"
            "請先回測，再輸入 /yearly。"
        )
        return

    try:
        results = await asyncio.to_thread(
            calculate_yearly_performance,
            df,
            10000.0,
        )

        report = format_yearly_report(
            results,
            symbol=symbol or "股票",
        )

        await send_long_text(
            update.message,
            report
        )

    except Exception:
        logger.exception(
            "年度績效失敗"
        )

        await update.message.reply_text(
            "❌ 年度績效分析失敗。"
        )


async def show_analyze(update, context):
    if not allowed(update):
        return

    restore_memory(update, context)

    try:
        trades, symbol, backtest_strategy = (
            await get_recent_trades(
                update,
                context,
            )
        )

        if trades is None:
            await update.message.reply_text(
                "目前沒有已儲存交易紀錄。"
            )
            return

        analysis = await asyncio.to_thread(
            analyze_trades,
            trades,
            10000.0,
        )

        report = format_trade_analytics(
            analysis,
            symbol=symbol or "股票",
        )

        await send_long_text(
            update.message,
            report
        )

    except Exception:
        logger.exception(
            "交易品質分析失敗"
        )

        await update.message.reply_text(
            "❌ 交易品質分析失敗。"
        )


async def show_compare(update, context):
    if not allowed(update):
        return

    restore_memory(update, context)

    try:
        strategy_a, strategy_b, status = (
            get_comparison_pair(
                context.user_data
            )
        )

        diff = format_strategy_diff(
            strategy_a,
            strategy_b,
        )

        header = (
            "⚖️ 策略 A/B 比較\n\n"
            "策略 A：修改前版本\n"
            "策略 B："
            + (
                "待確認版本"
                if status == "pending"
                else "已確認版本"
            )
            + "\n\n此操作不會修改策略版本。"
        )

        await send_long_text(
            update.message,
            header,
        )

        await send_long_text(
            update.message,
            diff,
        )

        await update.message.reply_text(
            "📊 正在執行 A/B 對照回測..."
        )

        lock = get_backtest_lock(context)

        async with lock:
            result = await asyncio.to_thread(
                compare_strategies,
                strategy_a,
                strategy_b,
            )

        report = format_ab_report(
            result
        )

        await send_long_text(
            update.message,
            report
        )

    except ValueError as exc:
        await update.message.reply_text(
            f"⚠️ 無法比較：{exc}"
        )

    except Exception:
        logger.exception(
            "A/B 比較失敗"
        )

        await update.message.reply_text(
            "❌ A/B 比較失敗，請查看終端機。"
        )


async def show_oos(update, context):
    if not allowed(update):
        return

    restore_memory(update, context)

    df = context.user_data.get(
        "last_df"
    )

    symbol = context.user_data.get(
        "last_symbol"
    )

    if df is None:
        await update.message.reply_text(
            "🧪 目前沒有可分析的每日資產資料。\n"
            "請先完成回測，再輸入 /oos。\n"
            "重新啟動後也需要重新回測。"
        )
        return

    try:
        result = await asyncio.to_thread(
            analyze_out_of_sample,
            df,
            0.70,
            10000.0,
        )

        report = format_oos_report(
            result,
            symbol=symbol or "股票",
        )

        await send_long_text(
            update.message,
            report
        )

    except ValueError as exc:
        await update.message.reply_text(
            f"⚠️ 無法分析：{exc}"
        )

    except Exception:
        logger.exception(
            "樣本內／外分析失敗"
        )

        await update.message.reply_text(
            "❌ 樣本內／外分析失敗。"
        )


def main():
    if not TOKEN:
        raise ValueError(
            ".env 缺少 TELEGRAM_BOT_TOKEN"
        )

    if not OWNER_ID:
        raise ValueError(
            ".env 缺少 TELEGRAM_OWNER_ID"
        )

    app = Application.builder().token(
        TOKEN
    ).build()

    app.add_handler(
        CommandHandler("myid", myid)
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("undo", undo_strategy)
    )

    app.add_handler(
        CommandHandler("cancel", cancel_strategy)
    )

    app.add_handler(
        CommandHandler("trades", show_trades)
    )

    app.add_handler(
        CommandHandler("chart", show_chart)
    )

    app.add_handler(
        CommandHandler("yearly", show_yearly)
    )

    app.add_handler(
        CommandHandler("analyze", show_analyze)
    )

    app.add_handler(
        CommandHandler("compare", show_compare)
    )

    app.add_handler(
        CommandHandler("oos", show_oos)
    )

    app.add_handler(
        CallbackQueryHandler(
            handle_button,
            pattern=(
                r"^(run|edit|cancel):[0-9a-f]{8}$"
            ),
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text,
        )
    )

    print(
        "AI Strategy Confirmation Bot running..."
    )

    app.run_polling()


if __name__ == "__main__":
    main()
