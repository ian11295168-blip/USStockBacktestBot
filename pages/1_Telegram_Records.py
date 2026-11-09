
"""Telegram 策略紀錄與安全匯入 — 網頁版 v0.5。"""

import sys
from copy import deepcopy
from pathlib import Path

import pandas as pd
import streamlit as st


# 專案根目錄
PROJECT_DIR = Path(__file__).resolve().parent.parent

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


from telegram_bridge import read_telegram_snapshot
from strategy_summary_v2 import format_strategy_summary


st.set_page_config(
    page_title="Telegram 策略匯入",
    page_icon="📱",
    layout="wide",
)


# ========================================
# 格式化工具
# ========================================

def pct(value, signed=False):
    if value is None:
        return "未知"

    try:
        number = float(value)
        return (
            f"{number:+.2f}%"
            if signed
            else f"{number:.2f}%"
        )
    except (ValueError, TypeError):
        return "未知"


def money(value):
    if value is None:
        return "未知"

    try:
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        return "未知"


def setting(value):
    if value is None:
        return "未設定"

    try:
        return f"{float(value):g}%"
    except (ValueError, TypeError):
        return "未知"


def show_strategy(strategy):
    if not isinstance(strategy, dict):
        st.info("目前沒有可顯示的策略。")
        return

    try:
        st.text(
            format_strategy_summary(strategy)
        )
    except Exception:
        st.json(strategy)


# ========================================
# 讀取 Telegram
# ========================================

st.title("📱 Telegram 策略紀錄")

st.write(
    "查看 Telegram 已確認策略、"
    "歷史版本與回測紀錄，"
    "也可以將策略複製到網頁進行回測。"
)

st.info(
    "🔒 本頁只讀取 Telegram 資料庫。"
    "匯入操作只會修改目前網頁的待確認策略，"
    "不會更動 Telegram 的策略。"
)

if st.button(
    "🔄 重新讀取 Telegram 資料",
    type="primary",
    use_container_width=True,
):
    st.rerun()


try:
    snapshot = read_telegram_snapshot()
except Exception as exc:
    st.error(
        f"Telegram 資料讀取失敗：{exc}"
    )
    st.stop()


confirmed = snapshot["confirmed_strategy"]
history = snapshot["strategy_history"]
pending = snapshot["pending"]
record = snapshot["latest_backtest"]


# ========================================
# Telegram 已確認策略
# ========================================

st.divider()
st.subheader("✅ Telegram 已確認策略")

if confirmed is None:
    st.warning(
        "Telegram 目前沒有已確認策略，"
        "因此還無法匯入。"
    )

else:
    left, right = st.columns(2)

    with left:
        st.metric(
            "股票",
            confirmed.get("symbol", "未知"),
        )

    with right:
        st.metric(
            "固定停損",
            setting(
                confirmed.get("stop_loss")
            ),
        )

    with st.expander(
        "查看 Telegram 完整策略",
        expanded=True,
    ):
        show_strategy(confirmed)


# ========================================
# 新增：安全匯入網頁
# ========================================

st.divider()
st.subheader("📥 匯入 Telegram 策略到網頁")

st.write(
    "按下匯入後，Telegram 策略會成為"
    "網頁的「待確認策略」。"
    "你可以先檢查，再決定是否執行回測。"
)

web_confirmed = st.session_state.get(
    "confirmed_strategy"
)

web_pending = st.session_state.get(
    "pending_strategy"
)


if isinstance(web_confirmed, dict):
    st.write(
        "目前網頁已確認策略：",
        web_confirmed.get("symbol", "未知"),
        "｜固定停損",
        setting(
            web_confirmed.get("stop_loss")
        ),
    )

else:
    st.write(
        "目前網頁沒有已確認策略。"
    )


if isinstance(web_pending, dict):
    st.warning(
        "網頁目前已經有一份待確認策略。"
        "再次匯入會取代這份尚未確認的提案，"
        "但不會更動已確認策略。"
    )

    replace_pending = st.checkbox(
        "我同意用 Telegram 策略取代"
        "目前網頁的待確認提案",
        value=False,
    )

else:
    replace_pending = True


if isinstance(confirmed, dict):

    if isinstance(web_confirmed, dict):
        same_symbol = (
            confirmed.get("symbol")
            == web_confirmed.get("symbol")
        )

        same_years = (
            confirmed.get("years")
            == web_confirmed.get("years")
        )

        if same_symbol and same_years:
            st.success(
                "Telegram 和網頁目前使用相同股票、"
                "相同回測年數，可在匯入後比較策略。"
            )
        else:
            st.warning(
                "Telegram 與網頁的股票或回測年數不同。"
                "可以匯入並獨立回測，"
                "但不能直接當作同一條件的 A/B 比較。"
            )

    import_clicked = st.button(
        "📥 匯入為網頁待確認策略",
        type="primary",
        use_container_width=True,
        disabled=not replace_pending,
    )

    if import_clicked:
        imported = deepcopy(confirmed)

        # 確認最基本的必要欄位
        if (
            not imported.get("symbol")
            or not imported.get("years")
        ):
            st.error(
                "Telegram 策略缺少股票代號或回測年數，"
                "請先檢查原始策略。"
            )
            st.stop()

        # 只有股票與回測期間相同，
        # 才以網頁已確認策略作為 A/B 比較基準。
        base_strategy = None

        if isinstance(web_confirmed, dict):
            if (
                web_confirmed.get("symbol")
                == imported.get("symbol")
                and web_confirmed.get("years")
                == imported.get("years")
            ):
                base_strategy = deepcopy(
                    web_confirmed
                )

        # 僅更新本次網頁 Session
        # 不呼叫 save_web_state()
        # 不呼叫 Telegram 的資料庫寫入函式
        st.session_state[
            "pending_strategy"
        ] = imported

        st.session_state[
            "pending_base_strategy"
        ] = base_strategy

        # 使舊 A/B 比較報告失效
        st.session_state[
            "ab_result"
        ] = None

        st.session_state[
            "ab_pair"
        ] = None

        # 直接跳回主程式的 AI 策略回測頁
        st.switch_page("web_app.py")


# ========================================
# Telegram 歷史策略版本
# ========================================

st.divider()
st.subheader("🗂️ Telegram 歷史策略版本")

valid_history = [
    item for item in (history or [])
    if isinstance(item, dict)
]

st.write(
    f"目前有 {len(valid_history)} 個歷史版本。"
)

if valid_history:

    selected_index = st.selectbox(
        "查看歷史版本",
        options=list(range(len(valid_history))),
        format_func=lambda i: (
            f"版本 {i + 1}｜"
            f"{valid_history[i].get('symbol', '未知')}"
            f"｜停損 "
            f"{setting(valid_history[i].get('stop_loss'))}"
        ),
    )

    show_strategy(
        valid_history[selected_index]
    )

    st.caption(
        "歷史版本目前僅供查看。"
        "匯入功能只使用 Telegram 已確認策略。"
    )

else:
    st.info("目前沒有歷史版本。")


# ========================================
# Telegram 待確認提案
# ========================================

st.divider()
st.subheader("📝 Telegram 待確認提案")

if isinstance(pending, dict):
    st.warning(
        "Telegram 有尚未確認的提案，"
        "不會自動匯入網頁。"
    )

    proposal = pending.get("strategy")

    if isinstance(proposal, dict):
        with st.expander("查看待確認提案"):
            show_strategy(proposal)

else:
    st.write("目前沒有待確認提案。")


# ========================================
# Telegram 最近一次回測
# ========================================

st.divider()
st.subheader("📊 Telegram 最近一次回測")

if record is None:
    st.info("目前沒有已儲存的回測紀錄。")

else:
    stats = record.get("stats") or {}
    trades = record.get("trades") or []

    if not isinstance(stats, dict):
        stats = {}

    if not isinstance(trades, list):
        trades = []

    st.write(
        "股票：",
        record.get("symbol", "未知"),
    )

    a, b = st.columns(2)

    with a:
        st.metric(
            "策略報酬",
            pct(
                stats.get("total_return"),
                signed=True,
            ),
        )

    with b:
        st.metric(
            "最大回撤",
            pct(stats.get("max_drawdown")),
        )

    a, b = st.columns(2)

    with a:
        st.metric(
            "勝率",
            pct(stats.get("win_rate")),
        )

    with b:
        st.metric(
            "期末資產",
            money(stats.get("final_equity")),
        )

    st.subheader("📋 歷史交易明細")

    if trades:
        table = pd.DataFrame(trades)

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "⬇️ 匯出 Telegram 交易紀錄 CSV",
            data=table.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="telegram_trades.csv",
            mime="text/csv",
        )

    else:
        st.info("這次沒有已完成交易。")

    st.caption(
        "最近一次回測可能不等於目前已確認策略。"
        "這兩份資料分別從 Telegram 紀錄讀取。"
    )


st.divider()

st.caption(
    "Telegram 匯入 v0.5｜"
    "唯讀取得 Telegram 策略｜"
    "網頁確認回測後才寫入網頁獨立資料庫。"
)
