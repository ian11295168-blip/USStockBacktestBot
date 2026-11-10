
"""US Stock Strategy Lab v4.3
本機 / Supabase 雙模式網頁。

啟動：
    python -m streamlit run secure_app.py

.env 設定：
    STOCK_STORAGE_MODE=local
或
    STOCK_STORAGE_MODE=cloud

local：
    SQLite 優先保存，再同步 Supabase。

cloud：
    直接讀寫 Supabase，不使用網頁 SQLite。
    使用載入時的 baseline 保護雲端資料。

注意：
    雲端模式仍是本機驗收階段，
    尚未完成正式公開部署的身份驗證。
"""

import math
import os
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

from web_storage_router import (
    get_storage_mode,
    load_state,
    save_state,
)

from cloud_web_storage import CloudConflictError

from cloud_autosave import (
    get_local_sync_status,
    sync_local_to_cloud,
)

from telegram_bridge import read_telegram_snapshot

from supabase_reader import (
    get_cloud_telegram_states,
    get_cloud_telegram_backtests,
)


load_dotenv()

st.set_page_config(
    page_title="US Stock Strategy Lab",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==========================================
# 1. 模式與基本工具
# ==========================================

try:
    STORAGE_MODE = get_storage_mode()
except Exception as exc:
    st.error(
        "❌ 資料儲存模式設定錯誤。"
        "請檢查 STOCK_STORAGE_MODE。"
    )
    st.caption(type(exc).__name__)
    st.stop()

IS_CLOUD = STORAGE_MODE == "cloud"


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
        st.info("目前沒有可顯示的策略")
        return

    try:
        st.text(format_strategy_summary(strategy))
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
        left, right = st.columns(2)

        with left:
            st.metric(*fields[i])

        with right:
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

    for name in ("close", "equity"):
        curve[name] = pd.to_numeric(
            curve[name],
            errors="coerce",
        )

    curve = (
        curve.dropna()
        .sort_values("timestamp")
    )

    if curve.empty:
        raise ValueError("沒有可顯示的資產資料")

    first_close = float(curve["close"].iloc[0])

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
            pct(sa.get("total_return"), True),
            pct(sb.get("total_return"), True),
        ),
        (
            "CAGR",
            pct(ma.get("cagr"), True),
            pct(mb.get("cagr"), True),
        ),
        (
            "Sharpe",
            fmt(ma.get("sharpe_ratio")),
            fmt(mb.get("sharpe_ratio")),
        ),
        (
            "最大回撤",
            pct(sa.get("max_drawdown")),
            pct(sb.get("max_drawdown")),
        ),
        (
            "勝率",
            pct(sa.get("win_rate")),
            pct(sb.get("win_rate")),
        ),
        (
            "交易次數",
            str(sa.get("trade_count", 0)),
            str(sb.get("trade_count", 0)),
        ),
        (
            "期末資產",
            money(sa.get("final_equity")),
            money(sb.get("final_equity")),
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
        st.text(format_ab_report(result))


# ==========================================
# 2. 資料保存與同步
# ==========================================

def show_notice(notice):
    if not isinstance(notice, dict):
        return

    status = notice.get("status")
    message = notice.get("message", "")

    if status == "success":
        st.success(message)

    elif status == "conflict":
        st.error(message)

    elif status == "error":
        st.error(message)

    else:
        st.warning(message)


def record_notice(status, message):
    st.session_state["_storage_notice"] = {
        "status": status,
        "message": message,
    }


def try_local_cloud_sync():
    """本機模式：SQLite 成功後嘗試同步 Supabase。"""

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
                "⚠️ 本機已保存，但仍有"
                "尚未同步的雲端變更"
            ),
        }

    except Exception as exc:
        if isinstance(exc, CloudConflictError):
            return {
                "status": "conflict",
                "message": (
                    "⚠️ 雲端版本發生衝突。"
                    "本機 SQLite 已保存，"
                    "但停止覆蓋雲端。"
                ),
            }

        return {
            "status": "pending",
            "message": (
                "⚠️ 本機 SQLite 已保存，"
                "但 Supabase 同步失敗。"
                "可稍後重新同步。"
                f"（{type(exc).__name__}）"
            ),
        }


def persist_state(
    confirmed_strategy,
    previous_strategy,
    result,
):
    """保存指定狀態。

    雲端保存失敗會拋出錯誤，
    不會被當作成功確認策略。

    本機模式保存成功後，
    雲端同步失敗不會取消 SQLite 結果。
    """

    if IS_CLOUD:
        baseline = st.session_state.get(
            "_cloud_baseline"
        )

        saved = save_state(
            confirmed_strategy,
            previous_strategy,
            result,
            mode="cloud",
            baseline=baseline,
        )

        # 只有確認 Supabase 提交成功，
        # 才更新 session 中的版本基準。
        st.session_state[
            "_cloud_baseline"
        ] = deepcopy(saved["baseline"])

        return {
            "status": "success",
            "message": (
                "✅ Supabase 雲端資料已保存"
            ),
        }

    save_state(
        confirmed_strategy,
        previous_strategy,
        result,
        mode="local",
    )

    return try_local_cloud_sync()


def show_storage_sidebar():
    st.subheader(
        "☁️ Supabase 雲端儲存"
        if IS_CLOUD
        else "💾 本機與雲端同步"
    )

    if IS_CLOUD:
        st.success("目前使用 Supabase")

        st.caption(
            "回測直接保存 PostgreSQL，"
            "不使用本機網頁 SQLite。"
        )

        if st.button(
            "🔄 重新讀取雲端版本",
            key="reload_cloud_state",
            use_container_width=True,
        ):
            # 避免意外丟失未確認提案。
            if st.session_state.get(
                "pending_strategy"
            ) is not None:
                st.warning(
                    "請先確認或取消待確認策略，"
                    "再重新讀取雲端。"
                )
            else:
                try:
                    snapshot = load_state("cloud")

                    state = snapshot["state"] or {}

                    st.session_state[
                        "confirmed_strategy"
                    ] = state.get(
                        "confirmed_strategy"
                    )

                    st.session_state[
                        "previous_confirmed_strategy"
                    ] = state.get(
                        "previous_confirmed_strategy"
                    )

                    st.session_state[
                        "last_result"
                    ] = state.get("last_result")

                    st.session_state[
                        "_cloud_baseline"
                    ] = deepcopy(
                        snapshot["baseline"]
                    )

                    st.session_state["ab_result"] = None
                    st.session_state["ab_pair"] = None

                    record_notice(
                        "success",
                        "✅ 已重新讀取 Supabase 最新版本",
                    )
                    st.rerun()

                except Exception as exc:
                    st.error(
                        "無法重新讀取雲端資料："
                        + type(exc).__name__
                    )

        st.caption(
            "重新讀取會更新目前網頁狀態，"
            "但不會修改雲端資料。"
        )

    else:
        try:
            status = get_local_sync_status()
        except Exception:
            status = {
                "status": "error",
            }

        code = status.get("status")

        if code == "synced":
            st.success(
                "本機與上次成功同步版本一致"
            )

        elif code == "pending":
            st.warning(
                "本機有尚未同步的變更"
            )

        elif code == "uninitialized":
            st.warning(
                "尚未初始化同步基準"
            )

        else:
            st.error(
                "無法確認同步狀態"
            )

        st.caption(
            "這是本機同步紀錄，"
            "不是即時雲端狀態。"
        )

        if st.button(
            "🔄 重新同步雲端",
            key="retry_cloud_sync",
            use_container_width=True,
        ):
            with st.spinner(
                "正在同步 Supabase..."
            ):
                result = try_local_cloud_sync()

            st.session_state[
                "_storage_notice"
            ] = result

            st.rerun()


# ==========================================
# 3. 載入目前模式的資料
# ==========================================

DEFAULTS = {
    "confirmed_strategy": None,
    "previous_confirmed_strategy": None,
    "pending_strategy": None,
    "pending_base_strategy": None,
    "last_result": None,
    "ab_result": None,
    "ab_pair": None,
    "strategy_input": "",
    "nav_page": "🤖 AI 策略回測",
    "_storage_notice": None,
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = deepcopy(value)


# 只有第一次載入或切換資料模式，
# 才重設並讀取對應資料庫。
if st.session_state.get(
    "_storage_active_mode"
) != STORAGE_MODE:

    try:
        snapshot = load_state(STORAGE_MODE)

    except Exception as exc:
        st.error(
            "❌ 無法載入目前模式的資料。"
            "網站已停止載入，"
            "不會自動切回 SQLite，"
            "避免誤用其他版本。"
        )
        st.caption(
            "錯誤類型："
            + type(exc).__name__
        )
        st.stop()

    state = snapshot["state"] or {}

    st.session_state[
        "confirmed_strategy"
    ] = state.get("confirmed_strategy")

    st.session_state[
        "previous_confirmed_strategy"
    ] = state.get(
        "previous_confirmed_strategy"
    )

    st.session_state[
        "last_result"
    ] = state.get("last_result")

    st.session_state[
        "_cloud_baseline"
    ] = deepcopy(snapshot["baseline"])

    st.session_state[
        "pending_strategy"
    ] = None

    st.session_state[
        "pending_base_strategy"
    ] = None

    st.session_state["ab_result"] = None
    st.session_state["ab_pair"] = None

    st.session_state[
        "_storage_notice"
    ] = None

    st.session_state[
        "_storage_active_mode"
    ] = STORAGE_MODE


# ==========================================
# 4. Telegram 資料讀取
# ==========================================

def get_telegram_data():
    """依模式取得 Telegram 已保存資料。

    local：本機 SQLite
    cloud：Supabase 已同步的 Telegram 資料

    cloud 模式不讀取本機 strategies.db。
    """

    if not IS_CLOUD:
        return read_telegram_snapshot()

    owner_id = os.getenv(
        "TELEGRAM_OWNER_ID",
        "",
    ).strip()

    if not owner_id:
        raise RuntimeError(
            "雲端模式需要設定 TELEGRAM_OWNER_ID"
        )

    all_states = get_cloud_telegram_states()

    selected = next(
        (
            row for row in all_states
            if str(row.get("user_id")) == owner_id
        ),
        None,
    )

    records = get_cloud_telegram_backtests(
        owner_id,
        limit=1,
    )

    state = selected or {}
    latest = records[0] if records else None

    record = None

    if latest is not None:
        record = {
            "symbol": latest.get("symbol"),
            "strategy": latest.get("strategy_json"),
            "stats": latest.get("stats_json"),
            "trades": latest.get("trades_json"),
            "created_at": latest.get("created_at"),
        }

    return {
        "confirmed_strategy": state.get(
            "last_strategy"
        ),
        "strategy_history": (
            state.get("strategy_history") or []
        ),
        "pending": state.get(
            "pending_strategy"
        ),
        "latest_backtest": record,
    }


# ==========================================
# 5. 左側功能選單
# ==========================================

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
    st.caption("網頁版 v4.3")

    if IS_CLOUD:
        st.info("☁️ 雲端模式：Supabase")
    else:
        st.info("💻 本機模式：SQLite")

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
        st.success("✅ 已確認策略")

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
        st.info("尚未有已確認策略")

    if isinstance(pending, dict):
        st.warning("📝 有待確認策略")

    st.divider()
    st.subheader("💾 儲存策略")

    if st.button(
        "儲存已確認策略與回測",
        key="manual_save",
        use_container_width=True,
    ):
        try:
            result_notice = persist_state(
                st.session_state[
                    "confirmed_strategy"
                ],
                st.session_state[
                    "previous_confirmed_strategy"
                ],
                st.session_state[
                    "last_result"
                ],
            )

        except CloudConflictError:
            result_notice = {
                "status": "conflict",
                "message": (
                    "❌ 雲端資料已被其他來源修改，"
                    "本次保存已取消。"
                    "請檢查雲端最新版本。"
                ),
            }

        except Exception as exc:
            result_notice = {
                "status": "error",
                "message": (
                    "❌ 保存失敗："
                    + type(exc).__name__
                ),
            }

        st.session_state[
            "_storage_notice"
        ] = result_notice

        st.rerun()

    st.divider()

    show_storage_sidebar()

    if IS_CLOUD:
        st.caption(
            "Telegram 使用 Supabase 已同步快照。"
        )
    else:
        st.caption(
            "Telegram 與網頁 SQLite 分開保存。"
        )


show_notice(
    st.session_state.get("_storage_notice")
)


# ==========================================
# 6. AI 策略回測
# ==========================================

if page == "🤖 AI 策略回測":
    st.title("🤖 AI 自然語言策略回測")

    st.write(
        "輸入中文策略，AI 解析後由你確認，"
        "再進行歷史回測。"
    )

    existing = (
        st.session_state["pending_strategy"]
        or st.session_state["confirmed_strategy"]
    )

    new_strategy = st.checkbox(
        "建立全新策略",
        value=(existing is None),
        help="修改現有條件時請不要勾選。",
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
            st.warning("請輸入策略內容")

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

                    if st.session_state[
                        "pending_strategy"
                    ] is not None:
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

                with st.spinner("AI 正在解析..."):
                    parsed = parse_universal_strategy(
                        strategy_text.strip(),
                        deepcopy(base),
                    )

                st.session_state[
                    "pending_strategy"
                ] = deepcopy(parsed)

                st.session_state[
                    "pending_base_strategy"
                ] = deepcopy(original)

                st.session_state["ab_result"] = None
                st.session_state["ab_pair"] = None

                st.success(
                    "解析完成，請確認策略"
                )

            except Exception as exc:
                st.error(
                    "解析失敗："
                    + str(exc)
                )

    confirmed = st.session_state[
        "confirmed_strategy"
    ]

    pending = st.session_state[
        "pending_strategy"
    ]

    if confirmed is not None:
        with st.expander("✅ 已確認策略"):
            show_strategy(confirmed)

    if pending is not None:
        st.divider()
        st.subheader("📝 待確認策略")

        show_strategy(pending)

        base = st.session_state[
            "pending_base_strategy"
        ]

        if isinstance(base, dict):
            with st.expander("修改前後差異"):
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

            st.session_state["ab_result"] = None
            st.session_state["ab_pair"] = None

            st.rerun()

        if run_clicked:
            # 先進行回測
            try:
                with st.spinner("正在回測..."):
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

                previous = deepcopy(confirmed)

                result = {
                    "strategy": deepcopy(pending),
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

            # 重要：
            # 成功保存後才更新已確認策略。
            # 雲端模式直接寫入 Supabase。
            # 本機模式 SQLite 優先。
            try:
                with st.spinner(
                    "正在保存回測結果..."
                ):
                    notice = persist_state(
                        deepcopy(pending),
                        previous,
                        result,
                    )

            except CloudConflictError:
                st.error(
                    "❌ Supabase 雲端版本已改變。"
                    "為避免覆蓋其他裝置的策略，"
                    "本次保存已取消。"
                )
                st.info(
                    "待確認策略仍然保留。"
                    "請先確認雲端最新資料。"
                )
                st.stop()

            except Exception as exc:
                st.error(
                    "❌ 保存失敗，"
                    "新策略尚未確認。"
                )
                st.caption(
                    "錯誤類型："
                    + type(exc).__name__
                )
                st.stop()

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

            st.session_state["ab_result"] = None
            st.session_state["ab_pair"] = None

            st.session_state[
                "_storage_notice"
            ] = notice

            st.rerun()

    result = st.session_state["last_result"]

    if result is not None:
        st.divider()

        st.subheader(
            "📊 最近一次回測績效"
        )

        strategy = result["strategy"]

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

            st.subheader("資產曲線")

            st.line_chart(
                equity_curve(result["df"]),
                height=350,
            )

        except Exception as exc:
            st.warning(
                "績效顯示失敗："
                + str(exc)
            )


# ==========================================
# 7. A/B 策略比較
# ==========================================

elif page == "⚖️ A/B 策略比較":
    st.title("⚖️ A/B 策略比較")

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
        st.warning("兩個策略設定相同")

    else:
        st.write("**策略 A：修改前**")

        st.caption(
            f"{a.get('symbol')}｜"
            f"停損 {setting(a.get('stop_loss'))}"
        )

        st.write("**策略 B：修改後**")

        st.caption(
            f"{b.get('symbol')}｜"
            f"停損 {setting(b.get('stop_loss'))}"
        )

        with st.expander(
            "查看條件差異",
            expanded=True,
        ):
            st.text(
                format_strategy_diff(a, b)
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
                    compared = compare_strategies(
                        deepcopy(a),
                        deepcopy(b),
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

                st.success("A/B 比較完成")

            except Exception as exc:
                st.error(
                    "A/B 比較失敗："
                    + str(exc)
                )

        comparison = st.session_state[
            "ab_result"
        ]

        pair = st.session_state["ab_pair"]

        if (
            comparison is not None
            and pair is not None
            and pair[0] == a
            and pair[1] == b
        ):
            try:
                show_ab(comparison)
            except Exception as exc:
                st.error(
                    "比較報告顯示失敗："
                    + str(exc)
                )

        st.caption(
            "A/B 比較不會修改已確認策略。"
        )


# ==========================================
# 8. Telegram 紀錄與策略匯入
# ==========================================

elif page == "📱 Telegram 紀錄與匯入":
    st.title("📱 Telegram 策略紀錄")

    st.info(
        (
            "目前讀取 Supabase 的 Telegram 快照。"
            if IS_CLOUD
            else "目前讀取本機 Telegram SQLite。"
        )
        + " 匯入只建立網頁待確認提案。"
    )

    if st.button(
        "🔄 重新讀取 Telegram",
        use_container_width=True,
    ):
        st.rerun()

    try:
        snapshot = get_telegram_data()

    except Exception as exc:
        st.error(
            "Telegram 資料讀取失敗："
            + type(exc).__name__
        )
        st.stop()

    tg_strategy = snapshot.get(
        "confirmed_strategy"
    )

    history = snapshot.get(
        "strategy_history"
    ) or []

    tg_pending = snapshot.get("pending")

    record = snapshot.get(
        "latest_backtest"
    )

    st.subheader("✅ Telegram 已確認策略")

    if not isinstance(tg_strategy, dict):
        st.info(
            "Telegram 沒有已確認策略。"
        )

    else:
        a, b = st.columns(2)

        with a:
            st.metric(
                "股票",
                str(tg_strategy.get(
                    "symbol", "未知"
                )),
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
            show_strategy(tg_strategy)

        st.divider()
        st.subheader("📥 匯入網頁")

        web_confirmed = st.session_state[
            "confirmed_strategy"
        ]

        web_pending = st.session_state[
            "pending_strategy"
        ]

        permitted = True

        if isinstance(web_pending, dict):
            st.warning(
                "目前已有待確認提案，"
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

                if isinstance(web_confirmed, dict):
                    if (
                        web_confirmed.get("symbol")
                        == tg_strategy.get("symbol")
                        and web_confirmed.get("years")
                        == tg_strategy.get("years")
                    ):
                        base = deepcopy(
                            web_confirmed
                        )

                st.session_state[
                    "pending_strategy"
                ] = deepcopy(tg_strategy)

                st.session_state[
                    "pending_base_strategy"
                ] = base

                st.session_state["ab_result"] = None
                st.session_state["ab_pair"] = None

                st.success(
                    "✅ 已匯入待確認策略。"
                    "請前往 AI 策略回測頁確認。"
                )

    st.divider()
    st.subheader("🗂️ 歷史策略版本")

    valid_history = [
        item
        for item in history
        if isinstance(item, dict)
    ] if isinstance(history, list) else []

    st.write(
        f"版本數量：{len(valid_history)}"
    )

    if valid_history:
        index = st.selectbox(
            "選擇歷史版本",
            range(len(valid_history)),
            format_func=lambda i: (
                f"版本 {i + 1}｜"
                f"{valid_history[i].get('symbol', '未知')}"
            ),
        )

        show_strategy(valid_history[index])

    else:
        st.info("沒有歷史版本")

    st.divider()
    st.subheader("📝 Telegram 待確認提案")

    if isinstance(tg_pending, dict):
        proposed = tg_pending.get("strategy")

        if isinstance(proposed, dict):
            show_strategy(proposed)
        else:
            st.warning("提案資料不完整")
    else:
        st.write("目前沒有待確認提案")

    st.divider()
    st.subheader("📊 Telegram 最近一次回測")

    if isinstance(record, dict):
        stats = record.get("stats") or {}
        trades = record.get("trades") or []

        st.write(
            "股票：",
            record.get("symbol", "未知"),
        )

        if isinstance(stats, dict):
            a, b = st.columns(2)

            with a:
                st.metric(
                    "策略報酬",
                    pct(
                        stats.get("total_return"),
                        True,
                    ),
                )

            with b:
                st.metric(
                    "期末資產",
                    money(
                        stats.get("final_equity")
                    ),
                )

        if isinstance(trades, list) and trades:
            table = pd.DataFrame(trades)

            st.dataframe(
                table,
                use_container_width=True,
                hide_index=True,
            )

            st.download_button(
                "⬇️ 匯出 Telegram 交易明細",
                table.to_csv(
                    index=False
                ).encode("utf-8-sig"),
                file_name="telegram_trades.csv",
                mime="text/csv",
            )

        else:
            st.info("沒有已完成交易")

    else:
        st.info(
            "沒有已儲存的 Telegram 回測"
        )


# ==========================================
# 9. Telegram / 網頁策略一致性
# ==========================================

elif page == "🔄 雙端同步檢查":
    st.title(
        "🔄 Telegram／網頁策略同步檢查"
    )

    st.info(
        "比較兩邊的已確認策略。"
        "本頁不修改資料庫。"
    )

    if st.button(
        "🔄 重新檢查",
        type="primary",
        use_container_width=True,
    ):
        st.rerun()

    try:
        tg_snapshot = get_telegram_data()

        web_snapshot = load_state(
            STORAGE_MODE
        )

    except Exception as exc:
        st.error(
            "資料讀取失敗："
            + type(exc).__name__
        )
        st.stop()

    tg = tg_snapshot.get(
        "confirmed_strategy"
    )

    web_state = web_snapshot.get("state")

    wb = (
        web_state.get("confirmed_strategy")
        if isinstance(web_state, dict)
        else None
    )

    a, b = st.columns(2)

    with a:
        st.subheader("📱 Telegram")

        if isinstance(tg, dict):
            st.write(
                "股票：",
                tg.get("symbol"),
            )

            st.write(
                "固定停損：",
                setting(tg.get("stop_loss")),
            )

            with st.expander("查看完整策略"):
                show_strategy(tg)

        else:
            st.info("沒有已確認策略")

    with b:
        st.subheader("🌐 網頁版")

        if isinstance(wb, dict):
            st.write(
                "股票：",
                wb.get("symbol"),
            )

            st.write(
                "固定停損：",
                setting(wb.get("stop_loss")),
            )

            with st.expander("查看完整策略"):
                show_strategy(wb)

        else:
            st.info("沒有已確認策略")

    st.divider()

    if (
        not isinstance(tg, dict)
        or not isinstance(wb, dict)
    ):
        st.warning(
            "至少一邊沒有已確認策略"
        )

    elif tg == wb:
        st.success(
            "✅ 兩邊已確認策略的全部設定一致！"
        )

    else:
        st.warning(
            "⚠️ 兩邊已確認策略不同"
        )

        try:
            st.text(
                format_strategy_diff(tg, wb)
            )
        except Exception:
            st.json({
                "Telegram": tg,
                "網頁": wb,
            })

    st.caption(
        "此頁比較策略內容，"
        "不是雲端儲存版本狀態。"
    )


# ==========================================
# 10. 績效與交易分析
# ==========================================

else:
    result = st.session_state[
        "last_result"
    ]

    if result is None:
        st.info(
            "目前沒有已保存回測。"
            "請先在 AI 策略回測頁完成回測。"
        )
        st.stop()

    df = result["df"]
    trades = result["trades"]
    stats = result["stats"]
    strategy = result["strategy"]
    symbol = strategy["symbol"]

    if page == "📈 績效分析":
        st.title("📈 完整績效分析")

        scorecards(
            stats,
            get_metrics(result),
        )

        st.subheader("資產績效曲線")

        st.line_chart(
            equity_curve(df),
            height=360,
        )

        try:
            analysis = analyze_trades(
                trades,
                10000.0,
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
                "交易分析失敗："
                + str(exc)
            )

    elif page == "📋 交易明細":
        st.title("📋 歷史交易明細")

        st.write("股票：", symbol)

        st.write(
            "固定停損：",
            setting(strategy.get("stop_loss")),
        )

        st.write(
            "追蹤停損：",
            setting(
                strategy.get("trailing_stop_pct")
            ),
        )

        st.write(
            "固定停利：",
            setting(
                strategy.get("take_profit")
            ),
        )

        if trades:
            table = pd.DataFrame(trades)

            st.dataframe(
                table,
                use_container_width=True,
                hide_index=True,
            )

            st.download_button(
                "⬇️ 匯出交易明細 CSV",
                table.to_csv(
                    index=False
                ).encode("utf-8-sig"),
                file_name=f"{symbol}_trades.csv",
                mime="text/csv",
            )

        else:
            st.info(
                "這次沒有已完成交易"
            )

    elif page == "📅 年度績效":
        st.title("📅 年度績效分析")

        try:
            yearly = calculate_yearly_performance(
                df,
                10000.0,
            )

            st.text(
                format_yearly_report(
                    yearly,
                    symbol=symbol,
                )
            )

        except Exception as exc:
            st.error(
                "年度績效分析失敗："
                + str(exc)
            )

    elif page == "🧪 樣本內／樣本外":
        st.title("🧪 分段績效分析")

        st.info(
            "此功能將既有回測分段，"
            "不等於真正獨立的樣本外驗證。"
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
            oos = analyze_out_of_sample(
                df,
                ratio / 100,
                10000.0,
            )

            st.text(
                format_oos_report(
                    oos,
                    symbol=symbol,
                )
            )

        except Exception as exc:
            st.error(
                "分段分析失敗："
                + str(exc)
            )


st.divider()

st.caption(
    "US Stock Strategy Lab v4.3｜"
    + (
        "Supabase 直接保存"
        if IS_CLOUD
        else "SQLite 優先、Supabase 同步"
    )
    + "｜Telegram 策略獨立｜"
    "歷史回測不保證未來績效。"
)
