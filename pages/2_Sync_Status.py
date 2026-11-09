
"""網頁版 v0.6：Telegram 與網頁策略同步狀態。

只讀取兩個資料庫，不修改任何策略。
"""

import math
import sys
from pathlib import Path

import streamlit as st


PROJECT_DIR = Path(__file__).resolve().parent.parent

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


from telegram_bridge import read_telegram_snapshot
from web_storage import load_web_state
from strategy_summary_v2 import format_strategy_summary
from strategy_diff import format_strategy_diff


st.set_page_config(
    page_title="雙端策略同步檢查",
    page_icon="🔄",
    layout="wide",
)


def percentage(value):
    if value is None:
        return "未設定"

    try:
        number = float(value)
        if not math.isfinite(number):
            return "無效數值"
        return f"{number:g}%"
    except (ValueError, TypeError):
        return "無效數值"


def show_strategy(strategy, label):
    """顯示一個已確認策略及主要設定。"""

    st.markdown(f"**{label}**")

    if not isinstance(strategy, dict):
        st.info("沒有已確認策略")
        return

    st.write(
        "股票：",
        strategy.get("symbol", "未知"),
    )

    st.write(
        "回測期間：",
        f"{strategy.get('years', '未知')}年",
    )

    st.write(
        "固定停損：",
        percentage(
            strategy.get("stop_loss")
        ),
    )

    st.write(
        "追蹤停損：",
        percentage(
            strategy.get("trailing_stop_pct")
        ),
    )

    st.write(
        "固定停利：",
        percentage(
            strategy.get("take_profit")
        ),
    )

    with st.expander("查看完整策略"):
        try:
            st.text(
                format_strategy_summary(strategy)
            )
        except Exception:
            st.warning("無法產生中文策略摘要")
            st.json(strategy)


def show_backtest_status(record, source):
    """查看回測記錄，避免混淆策略和回測版本。"""

    st.markdown(f"**{source}**")

    if not isinstance(record, dict):
        st.info("沒有已保存的回測記錄")
        return

    stats = record.get("stats")

    if not isinstance(stats, dict):
        st.warning("回測統計資料不完整")
        return

    result_strategy = record.get("strategy")

    symbol = record.get("symbol")

    if symbol is None and isinstance(result_strategy, dict):
        symbol = result_strategy.get("symbol")

    st.write("股票：", symbol or "未知")

    total_return = stats.get("total_return")

    if total_return is not None:
        try:
            st.metric(
                "最近回測總報酬",
                f"{float(total_return):+.2f}%",
            )
        except (ValueError, TypeError):
            st.write("報酬：無法辨識")

    st.write(
        "完成交易數：",
        stats.get("trade_count", "未知"),
    )

    if isinstance(result_strategy, dict):
        st.caption(
            "此筆回測保存了對應的策略設定。"
        )
        st.write(
            "本次回測固定停損：",
            percentage(
                result_strategy.get("stop_loss")
            ),
        )
    else:
        st.caption(
            "無法從此筆紀錄確認當時的策略設定；"
            "不會假設它等於目前已確認的策略。"
        )


st.title("🔄 Telegram／網頁策略同步檢查")

st.write(
    "比較兩邊目前已確認的策略，"
    "確認是否有設定差異。"
)

st.info(
    "🔒 唯讀模式：不修改 Telegram 或網頁資料庫。"
)

if st.button(
    "🔄 重新檢查兩邊資料",
    type="primary",
    use_container_width=True,
):
    st.rerun()


# 兩個資料來源分開讀取。
# 任一方失敗，都不會讓另一方資料被覆蓋。

telegram_snapshot = None
web_snapshot = None

telegram_error = None
web_error = None

try:
    telegram_snapshot = read_telegram_snapshot()
except Exception as exc:
    telegram_error = str(exc)

try:
    web_snapshot = load_web_state()
except Exception as exc:
    web_error = str(exc)


st.subheader("📡 資料庫連線狀態")

a, b = st.columns(2)

with a:
    if telegram_error:
        st.error("Telegram 資料庫讀取失敗")
        st.caption(telegram_error)
    elif telegram_snapshot is not None:
        st.success("Telegram 資料讀取成功")
    else:
        st.warning("Telegram 尚無資料")

with b:
    if web_error:
        st.error("網頁資料庫讀取失敗")
        st.caption(web_error)
    elif web_snapshot is not None:
        st.success("網頁資料讀取成功")
    else:
        st.warning("網頁尚無保存資料")


if telegram_error or web_error:
    st.warning(
        "至少一個資料來源讀取失敗，"
        "本次不能可靠判斷兩邊是否同步。"
    )
    st.stop()


telegram_strategy = None
web_strategy = None

telegram_record = None
web_record = None

if isinstance(telegram_snapshot, dict):
    telegram_strategy = telegram_snapshot.get(
        "confirmed_strategy"
    )
    telegram_record = telegram_snapshot.get(
        "latest_backtest"
    )

if isinstance(web_snapshot, dict):
    web_strategy = web_snapshot.get(
        "confirmed_strategy"
    )
    web_record = web_snapshot.get(
        "last_result"
    )


st.divider()
st.subheader("📋 已確認策略比較")

left, right = st.columns(2)

with left:
    show_strategy(
        telegram_strategy,
        "📱 Telegram 策略",
    )

with right:
    show_strategy(
        web_strategy,
        "🌐 網頁策略",
    )


st.divider()
st.subheader("⚖️ 策略一致性結果")

if (
    not isinstance(telegram_strategy, dict)
    or not isinstance(web_strategy, dict)
):
    st.warning(
        "至少一邊沒有已確認策略，"
        "目前無法比較。"
    )

elif telegram_strategy == web_strategy:
    st.success(
        "✅ 兩邊已確認策略的全部設定一致！"
    )

else:
    st.warning(
        "⚠️ Telegram 與網頁的已確認策略不同。"
    )

    with st.expander(
        "查看兩邊的策略差異",
        expanded=True,
    ):
        try:
            differences = format_strategy_diff(
                telegram_strategy,
                web_strategy,
            )

            st.text(differences)

        except Exception as exc:
            st.warning(
                f"差異摘要無法產生：{exc}"
            )

            st.json({
                "telegram": telegram_strategy,
                "web": web_strategy,
            })

    same_symbol = (
        telegram_strategy.get("symbol")
        == web_strategy.get("symbol")
    )

    same_years = (
        telegram_strategy.get("years")
        == web_strategy.get("years")
    )

    if same_symbol and same_years:
        st.info(
            "兩邊股票與回測年數相同。"
            "可以到 Telegram Records 頁面"
            "選擇匯入 Telegram 已確認策略，"
            "再自行確認網頁回測。"
        )
    else:
        st.info(
            "兩邊的股票或回測年數不同。"
            "應先核對策略內容，"
            "不要直接當成同條件的 A/B 比較。"
        )


st.divider()
st.subheader("📊 最近回測資料狀態")

a, b = st.columns(2)

with a:
    show_backtest_status(
        telegram_record,
        "📱 Telegram 最近回測",
    )

with b:
    show_backtest_status(
        web_record,
        "🌐 網頁最近回測",
    )


st.divider()
st.caption(
    "US Stock Strategy Lab v0.6｜"
    "本機雙端唯讀檢查｜"
    "相同策略設定不代表不同時間執行的"
    "回測結果必定相同。"
)
