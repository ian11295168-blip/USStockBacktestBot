
"""US Stock Strategy Lab v1.9 — 雲端資料檢視。

功能：
- 唯讀 Supabase 資料筆數
- 查看自己的 Telegram 雲端策略
- 查看最近 Telegram 雲端回測
- 查看網頁雲端策略摘要

安全：
- 只在已登入的 secure_app.py 中使用
- 不顯示資料庫密碼、Token 或 user_id
- 不修改任何資料庫
"""

import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from supabase_reader import (
    get_cloud_counts,
    get_cloud_telegram_states,
    get_cloud_telegram_backtests,
    get_cloud_web_state,
)
from strategy_summary_v2 import format_strategy_summary


load_dotenv()


def show_strategy(strategy):
    """安全顯示策略摘要。"""

    if not isinstance(strategy, dict):
        st.info("沒有已確認策略")
        return

    a, b = st.columns(2)

    with a:
        st.metric(
            "股票",
            str(strategy.get("symbol", "未知")),
        )

    with b:
        stop = strategy.get("stop_loss")

        st.metric(
            "固定停損",
            f"{stop}%" if stop is not None else "未設定",
        )

    st.write(
        "回測期間：",
        strategy.get("years", "未知"),
        "年",
    )

    with st.expander("查看完整策略"):
        try:
            st.text(
                format_strategy_summary(strategy)
            )
        except Exception:
            st.warning("無法產生策略摘要")


def load_cloud():
    """在每次頁面執行時讀取最新雲端資料。"""

    counts = get_cloud_counts()
    states = get_cloud_telegram_states()
    web = get_cloud_web_state()

    return counts, states, web


def main():
    # 雙重檢查，防止直接執行此頁。
    if not st.session_state.get(
        "_lab_authenticated", False
    ):
        st.error("請先從 secure_app.py 登入。")
        st.stop()

    st.title("☁️ Supabase 雲端資料")

    st.info(
        "這裡讀取 Supabase 的資料快照，"
        "不會修改 Telegram 或網頁資料庫。"
    )

    st.caption(
        "目前是本機單人測試版。"
        "雲端資料不會隨 Telegram 自動更新。"
    )

    if st.button(
        "🔄 重新讀取雲端資料",
        type="primary",
        use_container_width=True,
    ):
        st.rerun()

    try:
        with st.spinner("正在讀取 Supabase..."):
            counts, states, web = load_cloud()

    except Exception as exc:
        st.error(
            "Supabase 讀取失敗。"
            "請確認網路及 .env 連線設定。"
        )

        st.caption(
            "錯誤類型：" + type(exc).__name__
        )
        st.stop()

    # ===================================
    # 1. 雲端資料概況
    # ===================================

    st.subheader("📊 雲端資料概況")

    a, b, c = st.columns(3)

    with a:
        st.metric(
            "Telegram 策略",
            counts["telegram_strategy_state"],
        )

    with b:
        st.metric(
            "Telegram 回測",
            counts["telegram_backtest_results"],
        )

    with c:
        st.metric(
            "網頁狀態",
            counts["web_state"],
        )

    st.success("✅ Supabase 資料讀取成功")

    # ===================================
    # 2. 自己的 Telegram 策略
    # ===================================

    st.divider()
    st.subheader("📱 Telegram 雲端策略")

    owner_id = os.getenv("TELEGRAM_OWNER_ID", "").strip()

    if not owner_id:
        st.warning(
            "未設定 TELEGRAM_OWNER_ID，"
            "為避免顯示其他使用者資料，"
            "暫不顯示 Telegram 策略與交易。"
        )

    else:
        own_states = [
            item for item in states
            if str(item.get("user_id")) == owner_id
        ]

        if not own_states:
            st.info(
                "目前雲端沒有找到你的 Telegram 策略。"
            )

        else:
            state = own_states[0]

            show_strategy(
                state.get("last_strategy")
            )

            history = (
                state.get("strategy_history") or []
            )

            if isinstance(history, list):
                st.caption(
                    f"雲端保存的歷史策略版本："
                    f"{len(history)} 個"
                )

        # ===================================
        # 3. 最近 Telegram 回測
        # ===================================

        st.divider()
        st.subheader("📈 Telegram 雲端回測紀錄")

        try:
            backtests = get_cloud_telegram_backtests(
                owner_id,
                limit=20,
            )

        except Exception as exc:
            st.error("回測紀錄讀取失敗")
            st.caption(
                "錯誤類型：" + type(exc).__name__
            )
            backtests = []

        if backtests:
            rows = []

            for record in backtests:
                stats = record.get("stats_json")

                if not isinstance(stats, dict):
                    stats = {}

                rows.append({
                    "股票": record.get("symbol"),
                    "策略報酬(%)": stats.get(
                        "total_return"
                    ),
                    "交易次數": stats.get(
                        "trade_count"
                    ),
                    "建立時間": record.get(
                        "created_at"
                    ),
                })

            table = pd.DataFrame(rows)

            st.dataframe(
                table,
                use_container_width=True,
                hide_index=True,
            )

            st.caption(
                "最多顯示最近20筆自己的雲端回測。"
            )

        else:
            st.info("目前沒有可顯示的雲端回測。")

    # ===================================
    # 4. 網頁雲端策略狀態
    # ===================================

    st.divider()
    st.subheader("🌐 網頁雲端策略")

    if web is None:
        st.info("Supabase 尚未保存網頁狀態。")

    else:
        payload = web.get("payload")

        if not isinstance(payload, dict):
            st.warning("網頁雲端資料格式不正確")

        else:
            strategy = payload.get(
                "confirmed_strategy"
            )

            show_strategy(strategy)

            st.caption(
                "本筆雲端狀態為先前遷移的快照，"
                "不會自動覆蓋目前本機網頁策略。"
            )

    st.divider()
    st.caption(
        "US Stock Strategy Lab v1.9｜"
        "Supabase 唯讀檢視｜"
        "尚未開啟雲端自動同步。"
    )


if __name__ == "__main__":
    main()
