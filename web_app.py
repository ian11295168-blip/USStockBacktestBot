
"""US Stock Strategy Lab v2.2 — 自動雲端保存版。

保留功能：
- AI 中文策略解析與回測
- A/B 策略比較
- 績效、交易、年度、樣本內外分析
- SQLite 永久保存
- Telegram 紀錄與策略匯入
- Telegram / 網頁策略一致性檢查

新增功能：
- 回測完成後自動同步 Supabase
- 側邊欄顯示雲端同步狀態
- 雲端失敗時保留本機結果
- 手動重新同步
- 偵測雲端版本衝突

啟動入口仍為：
    python -m streamlit run secure_app.py
"""

import math
from copy import deepcopy

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from universal_ai_parser import parse_universal_strategy
from universal_backtest import run_universal_backtest
from strategy_summary_v2 import format_strategy_summary
from strategy_diff import format_strategy_diff
from performance_metrics import calculate_performance_metrics

from strategy_ab_comparison import (
    compare_strategies,
    format_ab_report,
)

from yearly_performance import (
    calculate_yearly_performance,
    format_yearly_report,
)

from trade_analytics import (
    analyze_trades,
    format_trade_analytics,
)

from out_of_sample import (
    analyze_out_of_sample,
    format_oos_report,
)

from web_storage import (
    load_web_state,
    save_web_state,
)

from telegram_bridge import read_telegram_snapshot

from cloud_autosave import (
    CloudConflictError,
    get_local_sync_status,
    sync_local_to_cloud,
)


load_dotenv()

st.set_page_config(
    page_title="US Stock Strategy Lab",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ========================================
# 1. 格式化工具
# ========================================

def fmt(value, digits=2, suffix="", signed=False):
    if value is None:
        return "無法計算"

    try:
        num = float(value)
    except (TypeError, ValueError):
        return "無法計算"

    if not math.isfinite(num):
        return "無法計算"

    flag = "+" if signed else ""
    return f"{num:{flag},.{digits}f}{suffix}"


def pct(value, signed=False):
    return fmt(
        value,
        suffix="%",
        signed=signed,
    )


def money(value):
    if value is None:
        return "無法計算"

    return "$" + fmt(value)


def setting(value):
    if value is None:
        return "未設定"

    try:
        return f"{float(value):g}%"
    except (TypeError, ValueError):
        return "未知"


def show_strategy(strategy):
    if not isinstance(strategy, dict):
        st.info("沒有可顯示的策略")
        return

    try:
        st.text(
            format_strategy_summary(strategy)
        )
    except Exception:
        st.json(strategy)


def get_metrics(result):
    if result.get("metrics") is None:
        result["metrics"] = calculate_performance_metrics(
            result["df"],
            result["trades"],
        )

    return result["metrics"]


def scorecards(stats, metrics):
    fields = [
        (
            "策略總報酬",
            pct(stats.get("total_return"), True),
        ),
        (
            "最大回撤",
            pct(stats.get("max_drawdown")),
        ),
        (
            "CAGR 年化報酬",
            pct(metrics.get("cagr"), True),
        ),
        (
            "Sharpe Ratio",
            fmt(metrics.get("sharpe_ratio")),
        ),
        (
            "勝率",
            pct(stats.get("win_rate")),
        ),
        (
            "交易次數",
            str(stats.get("trade_count", 0)),
        ),
        (
            "Buy & Hold",
            pct(stats.get("buy_hold_return"), True),
        ),
        (
            "期末資產",
            money(stats.get("final_equity")),
        ),
    ]

    for i in range(0, len(fields), 2):
        a, b = st.columns(2)

        with a:
            st.metric(*fields[i])

        with b:
            st.metric(*fields[i + 1])

    st.caption(
        "初始資金 $10,000｜目前持倉："
        + (
            "有"
            if stats.get("open_position")
            else "無"
        )
    )


def equity_curve(df):
    curve = df[
        ["timestamp", "close", "equity"]
    ].copy()

    curve["timestamp"] = pd.to_datetime(
        curve["timestamp"],
        utc=True,
        errors="coerce",
    )

    for col in ("close", "equity"):
        curve[col] = pd.to_numeric(
            curve[col],
            errors="coerce",
        )

    curve = (
        curve.dropna()
        .sort_values("timestamp")
    )

    if curve.empty:
        raise ValueError("沒有可顯示的資產資料")

    first_close = float(
        curve["close"].iloc[0]
    )

    if first_close <= 0:
        raise ValueError("起始收盤價錯誤")

    curve["策略資產"] = curve["equity"]

    curve["買進持有"] = (
        curve["close"]
        / first_close
        * 10000.0
    )

    return curve.set_index("timestamp")[
        ["策略資產", "買進持有"]
    ]


def ab_curve(result):
    a = result["df_a"][
        ["timestamp", "equity"]
    ].copy()

    b = result["df_b"][
        ["timestamp", "equity"]
    ].copy()

    for frame in (a, b):
        frame["timestamp"] = pd.to_datetime(
            frame["timestamp"],
            utc=True,
        )

    a = a.rename(
        columns={"equity": "策略 A"}
    )

    b = b.rename(
        columns={"equity": "策略 B"}
    )

    merged = pd.merge(
        a,
        b,
        on="timestamp",
        how="inner",
        validate="one_to_one",
    )

    if merged.empty:
        raise ValueError(
            "A/B 沒有共同的交易日期"
        )

    return (
        merged.sort_values("timestamp")
        .set_index("timestamp")
    )


def show_ab(result):
    sa = result["stats_a"]
    sb = result["stats_b"]
    ma = result["metrics_a"]
    mb = result["metrics_b"]

    rows = [
        (
            "總報酬",
            pct(sa["total_return"], True),
            pct(sb["total_return"], True),
        ),
        (
            "CAGR",
            pct(ma["cagr"], True),
            pct(mb["cagr"], True),
        ),
        (
            "Sharpe",
            fmt(ma["sharpe_ratio"]),
            fmt(mb["sharpe_ratio"]),
        ),
        (
            "最大回撤",
            pct(sa["max_drawdown"]),
            pct(sb["max_drawdown"]),
        ),
        (
            "勝率",
            pct(sa["win_rate"]),
            pct(sb["win_rate"]),
        ),
        (
            "交易次數",
            str(sa["trade_count"]),
            str(sb["trade_count"]),
        ),
        (
            "期末資產",
            money(sa["final_equity"]),
            money(sb["final_equity"]),
        ),
    ]

    st.dataframe(
        pd.DataFrame(
            rows,
            columns=[
                "指標",
                "策略 A",
                "策略 B",
            ],
        ).set_index("指標"),
        use_container_width=True,
    )

    st.subheader("A/B 資產曲線")

    st.line_chart(
        ab_curve(result),
        height=360,
    )

    with st.expander("詳細比較報告"):
        st.text(
            format_ab_report(result)
        )


# ========================================
# 2. 保存與雲端同步
# ========================================

def save_current():
    """保存目前已確認策略至 SQLite。"""

    save_web_state(
        st.session_state["confirmed_strategy"],
        st.session_state[
            "previous_confirmed_strategy"
        ],
        st.session_state["last_result"],
    )


def try_cloud_sync():
    """嘗試雲端同步，不拋出錯誤中斷回測。

    回傳：
        success / pending / conflict / error
    """

    try:
        result = sync_local_to_cloud()

        if result["status"] == "synced":
            return {
                "status": "success",
                "message": (
                    "✅ 本機 SQLite 與 "
                    "Supabase 雲端已保存"
                ),
            }

        return {
            "status": "pending",
            "message": (
                "⚠️ 雲端已保存一個版本，"
                "但本機又有新的變更，"
                "仍需重新同步"
            ),
        }

    except CloudConflictError:
        return {
            "status": "conflict",
            "message": (
                "⚠️ Supabase 雲端版本已變更，"
                "為避免覆蓋其他版本，"
                "系統已停止自動同步。"
                "本機 SQLite 已保留。"
            ),
        }

    except Exception as exc:
        return {
            "status": "error",
            "message": (
                "⚠️ 本機 SQLite 已保存，"
                "但 Supabase 同步失敗。"
                "可以稍後按「重新同步雲端」。"
                f"（{type(exc).__name__}）"
            ),
        }


def record_sync_result(result):
    """記錄操作結果，供網頁重新整理後顯示。"""

    st.session_state[
        "_cloud_sync_notice"
    ] = result


def display_sync_notice():
    """顯示最近一次保存或同步結果。"""

    notice = st.session_state.get(
        "_cloud_sync_notice"
    )

    if not isinstance(notice, dict):
        return

    status = notice.get("status")
    message = notice.get("message", "")

    if status == "success":
        st.success(message)

    elif status == "conflict":
        st.error(message)

    else:
        st.warning(message)


def show_sync_sidebar():
    """側邊欄雲端同步狀態與手動重試。"""

    st.subheader("☁️ Supabase 同步")

    try:
        status = get_local_sync_status()

    except Exception:
        status = {
            "status": "error",
            "message": (
                "無法讀取本機同步狀態"
            ),
        }

    code = status.get("status")

    if code == "synced":
        st.success(
            "✅ 本機與上次成功同步的"
            "版本一致"
        )

    elif code == "pending":
        st.warning(
            "⚠️ 本機有尚未同步的變更"
        )

    elif code == "uninitialized":
        st.warning(
            "⚠️ 尚未建立同步基準"
        )

    else:
        st.error(
            "❌ 無法確認同步狀態"
        )

    st.caption(
        "這是本機同步紀錄，"
        "並非即時查詢雲端版本。"
    )

    if st.button(
        "🔄 重新同步雲端",
        key="retry_cloud_sync",
        use_container_width=True,
    ):
        with st.spinner(
            "正在檢查並同步 Supabase..."
        ):
            result = try_cloud_sync()

        record_sync_result(result)
        st.rerun()


# ========================================
# 3. 啟動時恢復 SQLite
# ========================================

defaults = {
    "confirmed_strategy": None,
    "previous_confirmed_strategy": None,
    "pending_strategy": None,
    "pending_base_strategy": None,
    "last_result": None,
    "ab_result": None,
    "ab_pair": None,
    "strategy_input": (
        "NVDA RSI14低於30買進，"
        "RSI14高於70賣出，"
        "固定停損5%，回測5年"
    ),
    "nav_page": "🤖 AI 策略回測",
    "_cloud_sync_notice": None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = deepcopy(value)

if "_web_storage_loaded" not in st.session_state:
    try:
        saved = load_web_state()

        if saved:
            for key, value in saved.items():
                if st.session_state.get(key) is None:
                    st.session_state[key] = value

        st.session_state["_storage_error"] = None

    except Exception as exc:
        st.session_state[
            "_storage_error"
        ] = str(exc)

    st.session_state[
        "_web_storage_loaded"
    ] = True


# ========================================
# 4. 網站導覽
# ========================================

MENU = [
    "🤖 AI 策略回測",
    "⚖️ A/B 策略比較",
    "📈 績效分析",
    "📋 交易明細",
    "📅 年度績效",
    "🧪 樣本內／樣本外",
    "📱 Telegram 紀錄與匯入",
    "🔄 雙端同步檢查",
]


with st.sidebar:
    st.title("📈 US Stock Strategy Lab")
    st.caption("網頁版 v2.2")

    page = st.radio(
        "功能選單",
        MENU,
        key="nav_page",
    )

    st.divider()

    confirmed = st.session_state[
        "confirmed_strategy"
    ]

    pending = st.session_state[
        "pending_strategy"
    ]

    if isinstance(confirmed, dict):
        st.success("✅ 網頁已確認策略")

        st.write(
            "股票：",
            confirmed.get("symbol", "未知"),
        )

        st.write(
            "固定停損：",
            setting(
                confirmed.get("stop_loss")
            ),
        )

    else:
        st.info("尚未有網頁已確認策略")

    if isinstance(pending, dict):
        st.warning(
            "📝 有待確認的網頁策略"
        )

    st.divider()
    st.subheader("💾 本機資料保存")

    if st.button(
        "儲存已確認策略與回測",
        key="manual_save",
        use_container_width=True,
    ):
        try:
            save_current()

        except Exception as exc:
            record_sync_result({
                "status": "error",
                "message": (
                    "❌ SQLite 保存失敗，"
                    "沒有進行 Supabase 同步。"
                    f"（{type(exc).__name__}）"
                ),
            })

        else:
            with st.spinner(
                "本機保存成功，"
                "正在同步 Supabase..."
            ):
                sync_result = try_cloud_sync()

            record_sync_result(
                sync_result
            )

        st.rerun()

    if st.session_state.get(
        "_storage_error"
    ):
        st.error(
            "讀取舊紀錄失敗："
            + st.session_state[
                "_storage_error"
            ]
        )

    st.divider()

    show_sync_sidebar()

    st.caption(
        "Telegram 和網頁 SQLite "
        "仍分開保存。"
    )


# 在主要內容區顯示最近一次同步結果
display_sync_notice()


# ========================================
# 5. AI 策略回測
# ========================================

if page == "🤖 AI 策略回測":
    st.title(
        "🤖 AI 自然語言策略回測"
    )

    st.write(
        "輸入中文策略，AI 解析後由你確認，"
        "再進行歷史回測。"
    )

    existing = (
        st.session_state[
            "pending_strategy"
        ]
        or st.session_state[
            "confirmed_strategy"
        ]
    )

    new_strategy = st.checkbox(
        "建立全新策略",
        value=(existing is None),
        help=(
            "修改現有條件時請不要勾選。"
        ),
    )

    strategy_text = st.text_area(
        "輸入交易策略",
        key="strategy_input",
        height=140,
    )

    if st.button(
        "🧠 AI 解析策略",
        type="primary",
        use_container_width=True,
    ):
        if not strategy_text.strip():
            st.warning(
                "請輸入策略內容"
            )

        else:
            try:
                if new_strategy:
                    base = None
                    original = None

                else:
                    base = (
                        st.session_state[
                            "pending_strategy"
                        ]
                        or st.session_state[
                            "confirmed_strategy"
                        ]
                    )

                    if base is None:
                        st.error(
                            "沒有可修改的策略，"
                            "請勾選建立全新策略。"
                        )
                        st.stop()

                    if (
                        st.session_state[
                            "pending_strategy"
                        ]
                        is not None
                    ):
                        original = deepcopy(
                            st.session_state[
                                "pending_base_strategy"
                            ]
                        )

                    else:
                        original = deepcopy(
                            st.session_state[
                                "confirmed_strategy"
                            ]
                        )

                with st.spinner(
                    "AI 正在解析..."
                ):
                    parsed = (
                        parse_universal_strategy(
                            strategy_text.strip(),
                            deepcopy(base),
                        )
                    )

                st.session_state[
                    "pending_strategy"
                ] = deepcopy(parsed)

                st.session_state[
                    "pending_base_strategy"
                ] = deepcopy(original)

                st.session_state[
                    "ab_result"
                ] = None

                st.session_state[
                    "ab_pair"
                ] = None

                st.success(
                    "解析完成，請確認策略"
                )

            except Exception as exc:
                st.error(
                    f"解析失敗：{exc}"
                )

    confirmed = st.session_state[
        "confirmed_strategy"
    ]

    pending = st.session_state[
        "pending_strategy"
    ]

    if confirmed is not None:
        with st.expander(
            "✅ 已確認策略"
        ):
            show_strategy(
                confirmed
            )

    if pending is not None:
        st.divider()

        st.subheader(
            "📝 待確認策略"
        )

        show_strategy(pending)

        base = st.session_state[
            "pending_base_strategy"
        ]

        if isinstance(base, dict):
            with st.expander(
                "修改前後差異"
            ):
                st.text(
                    format_strategy_diff(
                        base,
                        pending,
                    )
                )

        a, b = st.columns(2)

        with a:
            run_clicked = st.button(
                "✅ 確認並執行回測",
                type="primary",
                use_container_width=True,
            )

        with b:
            cancel_clicked = st.button(
                "取消待確認策略",
                use_container_width=True,
            )

        if cancel_clicked:
            st.session_state[
                "pending_strategy"
            ] = None

            st.session_state[
                "pending_base_strategy"
            ] = None

            st.session_state[
                "ab_result"
            ] = None

            st.session_state[
                "ab_pair"
            ] = None

            st.rerun()

        if run_clicked:

            # 第一步：回測
            try:
                with st.spinner(
                    "正在回測..."
                ):
                    df, trades, stats = (
                        run_universal_backtest(
                            deepcopy(pending)
                        )
                    )

                    metrics = (
                        calculate_performance_metrics(
                            df,
                            trades,
                        )
                    )

                previous = deepcopy(
                    confirmed
                )

                result = {
                    "strategy": deepcopy(
                        pending
                    ),
                    "df": df,
                    "trades": trades,
                    "stats": stats,
                    "metrics": metrics,
                }

            except Exception as exc:
                st.error(
                    "❌ 回測失敗："
                    + str(exc)
                )
                st.stop()

            # 第二步：先保存本機 SQLite
            try:
                save_web_state(
                    deepcopy(pending),
                    previous,
                    result,
                )

            except Exception as exc:
                st.error(
                    "❌ 本機 SQLite 保存失敗，"
                    "新策略尚未確認。"
                )

                st.caption(
                    "錯誤類型："
                    + type(exc).__name__
                )

                st.stop()

            # SQLite 成功，才更新正式策略
            st.session_state[
                "confirmed_strategy"
            ] = deepcopy(pending)

            st.session_state[
                "previous_confirmed_strategy"
            ] = previous

            st.session_state[
                "last_result"
            ] = result

            st.session_state[
                "pending_strategy"
            ] = None

            st.session_state[
                "pending_base_strategy"
            ] = None

            st.session_state[
                "ab_result"
            ] = None

            st.session_state[
                "ab_pair"
            ] = None

            # 第三步：自動同步 Supabase
            # 雲端失敗不會取消本機已保存結果
            with st.spinner(
                "本機保存成功，"
                "正在同步 Supabase..."
            ):
                sync_result = (
                    try_cloud_sync()
                )

            record_sync_result(
                sync_result
            )

            st.rerun()

    result = st.session_state[
        "last_result"
    ]

    if result is not None:
        st.divider()

        st.subheader(
            "📊 最近一次回測績效"
        )

        strategy = result[
            "strategy"
        ]

        st.caption(
            f"{strategy['symbol']}｜"
            f"{strategy['years']}年｜"
            f"固定停損 "
            f"{setting(strategy.get('stop_loss'))}"
        )

        try:
            scorecards(
                result["stats"],
                get_metrics(result),
            )

            st.subheader(
                "資產曲線"
            )

            st.line_chart(
                equity_curve(
                    result["df"]
                ),
                height=350,
            )

        except Exception as exc:
            st.warning(
                "績效顯示失敗："
                + str(exc)
            )


# ========================================
# 6. A/B 策略比較
# ========================================

elif page == "⚖️ A/B 策略比較":
    st.title(
        "⚖️ A/B 策略比較"
    )

    pending = st.session_state[
        "pending_strategy"
    ]

    confirmed = st.session_state[
        "confirmed_strategy"
    ]

    if pending is not None:
        a = st.session_state[
            "pending_base_strategy"
        ]
        b = pending

    else:
        a = st.session_state[
            "previous_confirmed_strategy"
        ]
        b = confirmed

    if (
        not isinstance(a, dict)
        or not isinstance(b, dict)
    ):
        st.info(
            "請先建立策略 A，"
            "再修改產生策略 B。"
        )

    elif a == b:
        st.warning(
            "兩個策略設定相同。"
        )

    else:
        st.write(
            "**策略 A：修改前**"
        )

        st.caption(
            f"{a.get('symbol')}｜"
            f"停損 "
            f"{setting(a.get('stop_loss'))}"
        )

        st.write(
            "**策略 B：修改後**"
        )

        st.caption(
            f"{b.get('symbol')}｜"
            f"停損 "
            f"{setting(b.get('stop_loss'))}"
        )

        with st.expander(
            "查看條件差異",
            expanded=True,
        ):
            st.text(
                format_strategy_diff(
                    a, b
                )
            )

        if st.button(
            "🚀 執行 A/B 對照回測",
            type="primary",
            use_container_width=True,
        ):
            try:
                with st.spinner(
                    "正在比較策略..."
                ):
                    compared = (
                        compare_strategies(
                            deepcopy(a),
                            deepcopy(b),
                        )
                    )

                st.session_state[
                    "ab_result"
                ] = compared

                st.session_state[
                    "ab_pair"
                ] = (
                    deepcopy(a),
                    deepcopy(b),
                )

                st.success(
                    "A/B 比較完成"
                )

            except Exception as exc:
                st.error(
                    f"A/B 比較失敗：{exc}"
                )

        comparison = st.session_state[
            "ab_result"
        ]

        pair = st.session_state[
            "ab_pair"
        ]

        if (
            comparison is not None
            and pair is not None
            and pair[0] == a
            and pair[1] == b
        ):
            try:
                show_ab(
                    comparison
                )

            except Exception as exc:
                st.error(
                    "比較報告顯示失敗："
                    + str(exc)
                )

        st.caption(
            "A/B 比較不會修改已確認策略。"
        )


# ========================================
# 7. Telegram 紀錄與安全匯入
# ========================================

elif page == "📱 Telegram 紀錄與匯入":
    st.title(
        "📱 Telegram 策略紀錄"
    )

    st.info(
        "唯讀取得 Telegram 資料。"
        "匯入只建立網頁待確認提案。"
    )

    if st.button(
        "🔄 重新讀取 Telegram",
        use_container_width=True,
    ):
        st.rerun()

    try:
        snapshot = (
            read_telegram_snapshot()
        )

    except Exception as exc:
        st.error(
            f"Telegram 讀取失敗：{exc}"
        )
        st.stop()

    tg_strategy = snapshot[
        "confirmed_strategy"
    ]

    history = snapshot[
        "strategy_history"
    ]

    tg_pending = snapshot[
        "pending"
    ]

    record = snapshot[
        "latest_backtest"
    ]

    st.subheader(
        "✅ Telegram 已確認策略"
    )

    if not isinstance(
        tg_strategy, dict
    ):
        st.info(
            "Telegram 沒有已確認策略。"
        )

    else:
        a, b = st.columns(2)

        with a:
            st.metric(
                "股票",
                str(
                    tg_strategy.get(
                        "symbol", "未知"
                    )
                ),
            )

        with b:
            st.metric(
                "固定停損",
                setting(
                    tg_strategy.get(
                        "stop_loss"
                    )
                ),
            )

        with st.expander(
            "完整 Telegram 策略"
        ):
            show_strategy(
                tg_strategy
            )

        st.divider()

        st.subheader(
            "📥 匯入網頁"
        )

        web_confirmed = (
            st.session_state[
                "confirmed_strategy"
            ]
        )

        web_pending = (
            st.session_state[
                "pending_strategy"
            ]
        )

        permitted = True

        if isinstance(
            web_pending, dict
        ):
            st.warning(
                "網頁目前已有待確認提案，"
                "匯入會取代它。"
            )

            permitted = st.checkbox(
                "我同意取代目前待確認提案"
            )

        if st.button(
            "📥 匯入為網頁待確認策略",
            type="primary",
            use_container_width=True,
            disabled=not permitted,
        ):
            if (
                not tg_strategy.get("symbol")
                or not tg_strategy.get("years")
            ):
                st.error(
                    "Telegram 策略缺少必要欄位"
                )

            else:
                base = None

                if isinstance(
                    web_confirmed, dict
                ):
                    if (
                        web_confirmed.get(
                            "symbol"
                        )
                        == tg_strategy.get(
                            "symbol"
                        )
                        and web_confirmed.get(
                            "years"
                        )
                        == tg_strategy.get(
                            "years"
                        )
                    ):
                        base = deepcopy(
                            web_confirmed
                        )

                st.session_state[
                    "pending_strategy"
                ] = deepcopy(
                    tg_strategy
                )

                st.session_state[
                    "pending_base_strategy"
                ] = base

                st.session_state[
                    "ab_result"
                ] = None

                st.session_state[
                    "ab_pair"
                ] = None

                st.success(
                    "✅ 已匯入！"
                    "請點左側「AI 策略回測」"
                    "確認。"
                )

    st.divider()

    st.subheader(
        "🗂️ 歷史策略版本"
    )

    valid_history = [
        item
        for item in (history or [])
        if isinstance(item, dict)
    ]

    st.write(
        f"版本數量：{len(valid_history)}"
    )

    if valid_history:
        index = st.selectbox(
            "選擇歷史版本",
            range(
                len(valid_history)
            ),
            format_func=lambda i: (
                f"版本 {i + 1}｜"
                f"{valid_history[i].get('symbol', '未知')}"
            ),
        )

        show_strategy(
            valid_history[index]
        )

    else:
        st.info(
            "沒有歷史版本。"
        )

    st.divider()

    st.subheader(
        "📝 Telegram 待確認提案"
    )

    if isinstance(
        tg_pending, dict
    ):
        proposed = (
            tg_pending.get("strategy")
        )

        if isinstance(
            proposed, dict
        ):
            show_strategy(
                proposed
            )

        else:
            st.warning(
                "提案資料不完整。"
            )

    else:
        st.write(
            "目前沒有待確認提案。"
        )

    st.divider()

    st.subheader(
        "📊 Telegram 最近一次回測"
    )

    if isinstance(
        record, dict
    ):
        stats = (
            record.get("stats") or {}
        )

        trades = (
            record.get("trades") or []
        )

        st.write(
            "股票：",
            record.get(
                "symbol", "未知"
            ),
        )

        if isinstance(
            stats, dict
        ):
            a, b = st.columns(2)

            with a:
                st.metric(
                    "策略報酬",
                    pct(
                        stats.get(
                            "total_return"
                        ),
                        True,
                    ),
                )

            with b:
                st.metric(
                    "期末資產",
                    money(
                        stats.get(
                            "final_equity"
                        )
                    ),
                )

        if (
            isinstance(trades, list)
            and trades
        ):
            table = pd.DataFrame(
                trades
            )

            st.dataframe(
                table,
                use_container_width=True,
                hide_index=True,
            )

            st.download_button(
                "⬇️ 匯出 Telegram 交易明細",
                table.to_csv(
                    index=False
                ).encode(
                    "utf-8-sig"
                ),
                file_name=(
                    "telegram_trades.csv"
                ),
                mime="text/csv",
            )

        else:
            st.info(
                "沒有已完成交易。"
            )

    else:
        st.info(
            "沒有已儲存的 Telegram 回測。"
        )


# ========================================
# 8. 雙端策略一致性檢查
# ========================================

elif page == "🔄 雙端同步檢查":
    st.title(
        "🔄 Telegram／網頁策略同步檢查"
    )

    st.info(
        "這是 Telegram 與網頁已確認"
        "策略的唯讀比較，"
        "不會修改任一資料庫。"
    )

    if st.button(
        "🔄 重新檢查",
        type="primary",
        use_container_width=True,
    ):
        st.rerun()

    try:
        tg_snapshot = (
            read_telegram_snapshot()
        )

        web_snapshot = (
            load_web_state()
        )

    except Exception as exc:
        st.error(
            f"資料讀取失敗：{exc}"
        )
        st.stop()

    tg = tg_snapshot.get(
        "confirmed_strategy"
    )

    wb = (
        web_snapshot.get(
            "confirmed_strategy"
        )
        if isinstance(
            web_snapshot, dict
        )
        else None
    )

    a, b = st.columns(2)

    with a:
        st.subheader(
            "📱 Telegram"
        )

        if isinstance(tg, dict):
            st.write(
                "股票：",
                tg.get("symbol"),
            )

            st.write(
                "固定停損：",
                setting(
                    tg.get(
                        "stop_loss"
                    )
                ),
            )

            with st.expander(
                "查看完整策略"
            ):
                show_strategy(tg)

        else:
            st.info(
                "沒有已確認策略"
            )

    with b:
        st.subheader(
            "🌐 網頁版"
        )

        if isinstance(wb, dict):
            st.write(
                "股票：",
                wb.get("symbol"),
            )

            st.write(
                "固定停損：",
                setting(
                    wb.get(
                        "stop_loss"
                    )
                ),
            )

            with st.expander(
                "查看完整策略"
            ):
                show_strategy(wb)

        else:
            st.info(
                "沒有已確認策略"
            )

    st.divider()

    if (
        not isinstance(tg, dict)
        or not isinstance(wb, dict)
    ):
        st.warning(
            "至少一邊沒有已確認策略。"
        )

    elif tg == wb:
        st.success(
            "✅ 兩邊已確認策略的"
            "全部設定一致！"
        )

    else:
        st.warning(
            "⚠️ 兩邊已確認策略不同。"
        )

        try:
            st.text(
                format_strategy_diff(
                    tg, wb
                )
            )

        except Exception:
            st.json({
                "Telegram": tg,
                "網頁": wb,
            })

    st.caption(
        "本頁比較 Telegram 與網頁策略，"
        "不是 Supabase 同步狀態。"
    )


# ========================================
# 9. 其他績效頁面
# ========================================

else:
    result = st.session_state[
        "last_result"
    ]

    if result is None:
        st.info(
            "目前沒有網頁已保存回測。"
            "請先在 AI 策略回測頁完成回測。"
        )
        st.stop()

    df = result["df"]
    trades = result["trades"]
    stats = result["stats"]
    strategy = result["strategy"]
    symbol = strategy["symbol"]

    if page == "📈 績效分析":
        st.title(
            "📈 完整績效分析"
        )

        scorecards(
            stats,
            get_metrics(result),
        )

        st.subheader(
            "資產績效曲線"
        )

        st.line_chart(
            equity_curve(df),
            height=360,
        )

        try:
            analysis = (
                analyze_trades(
                    trades,
                    10000.0,
                )
            )

            with st.expander(
                "交易品質分析"
            ):
                st.text(
                    format_trade_analytics(
                        analysis,
                        symbol=symbol,
                    )
                )

        except Exception as exc:
            st.warning(
                f"交易分析失敗：{exc}"
            )

    elif page == "📋 交易明細":
        st.title(
            "📋 歷史交易明細"
        )

        st.write(
            "股票：", symbol
        )

        st.write(
            "固定停損：",
            setting(
                strategy.get(
                    "stop_loss"
                )
            ),
        )

        st.write(
            "追蹤停損：",
            setting(
                strategy.get(
                    "trailing_stop_pct"
                )
            ),
        )

        st.write(
            "固定停利：",
            setting(
                strategy.get(
                    "take_profit"
                )
            ),
        )

        if trades:
            table = pd.DataFrame(
                trades
            )

            st.dataframe(
                table,
                use_container_width=True,
                hide_index=True,
            )

            st.download_button(
                "⬇️ 匯出交易明細 CSV",
                table.to_csv(
                    index=False
                ).encode(
                    "utf-8-sig"
                ),
                file_name=(
                    f"{symbol}_trades.csv"
                ),
                mime="text/csv",
            )

        else:
            st.info(
                "這次沒有已完成交易。"
            )

    elif page == "📅 年度績效":
        st.title(
            "📅 年度績效分析"
        )

        try:
            yearly = (
                calculate_yearly_performance(
                    df,
                    10000.0,
                )
            )

            st.text(
                format_yearly_report(
                    yearly,
                    symbol=symbol,
                )
            )

        except Exception as exc:
            st.error(
                f"年度績效分析失敗：{exc}"
            )

    elif page == "🧪 樣本內／樣本外":
        st.title(
            "🧪 分段績效分析"
        )

        st.info(
            "此功能是將既有回測分段，"
            "不等於真正的獨立樣本外驗證。"
        )

        ratio = st.slider(
            "樣本內比例",
            min_value=20,
            max_value=80,
            value=70,
            step=5,
            format="%d%%",
        )

        try:
            oos = (
                analyze_out_of_sample(
                    df,
                    ratio / 100,
                    10000.0,
                )
            )

            st.text(
                format_oos_report(
                    oos,
                    symbol=symbol,
                )
            )

        except Exception as exc:
            st.error(
                f"分段分析失敗：{exc}"
            )


st.divider()

st.caption(
    "US Stock Strategy Lab v2.2｜"
    "SQLite 優先保存｜"
    "Supabase 自動同步｜"
    "Telegram 資料保持唯讀｜"
    "歷史回測不保證未來績效。"
)
