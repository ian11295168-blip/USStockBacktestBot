
"""US Stock Strategy Lab v4.3
本機 / Supabase 雙模式Web。

啟動：
    python -m streamlit run secure_app.py

.env 設定：
    STOCK_STORAGE_MODE=local
或
    STOCK_STORAGE_MODE=cloud

local：
    SQLite 優先保存，再同步 Supabase。

cloud：
    直接讀寫 Supabase，不使用Web SQLite。
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
from strategy_summary_en import format_strategy_summary
from strategy_diff import format_strategy_diff
from performance_metrics import calculate_performance_metrics

from strategy_ab_comparison import (
    compare_strategies,
    format_ab_report,
)

from yearly_performance import (
    calculate_yearly_performance,
    format_yearly_report_en,
)

from trade_analytics import (
    analyze_trades,
    format_trade_analytics,
)

from out_of_sample import (
    analyze_out_of_sample,
    format_oos_report_en,
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
        "❌ Invalid storage mode."
        "Check STOCK_STORAGE_MODE."
    )
    st.caption(type(exc).__name__)
    st.stop()

IS_CLOUD = STORAGE_MODE == "cloud"
IS_GUEST = not st.session_state.get("_lab_authenticated", False)

# Guests use the original backtesting and AI modules, but session-only storage.
# No guest execution path may read or write a private database.
import threading

@st.cache_resource
def guest_ai_budget():
    return {"lock": threading.Lock(), "used": 0}

GUEST_AI_PER_SESSION = 5
GUEST_AI_PER_PROCESS = 100



def fmt(value, digits=2, suffix="", signed=False):
    if value is None:
        return "N/A"

    try:
        num = float(value)
    except (TypeError, ValueError):
        return "N/A"

    if not math.isfinite(num):
        return "N/A"

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
        return "Not set"

    try:
        return f"{float(value):g}%"
    except (TypeError, ValueError):
        return "Unknown"


def show_strategy(strategy):
    if not isinstance(strategy, dict):
        st.info("No strategy to display")
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
            "Strategy total return",
            pct(stats.get("total_return"), True),
        ),
        (
            "Max drawdown",
            pct(stats.get("max_drawdown")),
        ),
        (
            "CAGR",
            pct(metrics.get("cagr"), True),
        ),
        (
            "Sharpe Ratio",
            fmt(metrics.get("sharpe_ratio")),
        ),
        (
            "Win rate",
            pct(stats.get("win_rate")),
        ),
        (
            "Trade count",
            str(stats.get("trade_count", 0)),
        ),
        (
            "Buy & Hold",
            pct(stats.get("buy_hold_return"), True),
        ),
        (
            "Ending equity",
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
        "Initial capital $10,000 | Open position: "
        + (
            "Yes"
            if stats.get("open_position")
            else "No"
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
        raise ValueError("No equity data available")

    first_close = float(curve["close"].iloc[0])

    if first_close <= 0:
        raise ValueError("Invalid starting close price")

    curve["Strategy Equity"] = curve["equity"]

    curve["Buy & Hold"] = (
        curve["close"]
        / first_close
        * 10000.0
    )

    return curve.set_index("timestamp")[
        ["Strategy Equity", "Buy & Hold"]
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
        columns={"equity": "Strategy A"}
    )

    b = b.rename(
        columns={"equity": "Strategy B"}
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
            "A/B results have no overlapping trading days"
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
            "Total return",
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
            "Max drawdown",
            pct(sa.get("max_drawdown")),
            pct(sb.get("max_drawdown")),
        ),
        (
            "Win rate",
            pct(sa.get("win_rate")),
            pct(sb.get("win_rate")),
        ),
        (
            "Trade count",
            str(sa.get("trade_count", 0)),
            str(sb.get("trade_count", 0)),
        ),
        (
            "Ending equity",
            money(sa.get("final_equity")),
            money(sb.get("final_equity")),
        ),
    ]

    st.dataframe(
        pd.DataFrame(
            rows,
            columns=[
                "Metric",
                "Strategy A",
                "Strategy B",
            ],
        ).set_index("Metric"),
        use_container_width=True,
    )

    st.subheader("A/B Equity Curves")

    st.line_chart(
        ab_curve(result),
        height=360,
    )

    with st.expander("Detailed comparison report"):
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
                    "✅ Local SQLite and "
                    "Supabase saved"
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
                    "⚠️ Cloud version conflict。"
                    "Local SQLite saved，"
                    "but cloud overwrite was blocked."
                ),
            }

        return {
            "status": "pending",
            "message": (
                "⚠️ Local SQLite saved，"
                "but Supabase sync failed."
                "Please retry later."
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

    if IS_GUEST:
        return {
            "status": "success",
            "message": "Saved in this browser session only. No private database was accessed.",
        }

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
                "✅ Saved to Supabase"
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
    if IS_GUEST:
        st.info("Guest workspace: strategies and results are kept in this browser session only.")
        st.caption("Refreshing or closing this session may clear your work. The owner's database is never accessed.")
        return

    st.subheader(
        "☁️ Supabase Storage"
        if IS_CLOUD
        else "💾 Local / Cloud Sync"
    )

    if IS_CLOUD:
        st.success("Using Supabase")

        st.caption(
            "Backtests are saved directly to PostgreSQL;"
            "no local web SQLite is used."
        )

        if st.button(
            "🔄 Reload Cloud Version",
            key="reload_cloud_state",
            use_container_width=True,
        ):
            # 避免意外丟失未確認提案。
            if st.session_state.get(
                "pending_strategy"
            ) is not None:
                st.warning(
                    "Confirm or discard the pending strategy"
                    "before reloading cloud data."
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
                        "✅ Latest Supabase version loaded",
                    )
                    st.rerun()

                except Exception as exc:
                    st.error(
                        "Unable to reload cloud data: "
                        + type(exc).__name__
                    )

        st.caption(
            "Reload replaces the current session view"
            "without modifying cloud data."
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
                "Matches the last successful sync version"
            )

        elif code == "pending":
            st.warning(
                "Local changes are pending sync"
            )

        elif code == "uninitialized":
            st.warning(
                "Sync baseline not initialized"
            )

        else:
            st.error(
                "Unable to verify sync status"
            )

        st.caption(
            "This is a local sync status,"
            "not a real-time cloud status."
        )

        if st.button(
            "🔄 Retry Cloud Sync",
            key="retry_cloud_sync",
            use_container_width=True,
        ):
            with st.spinner(
                "Syncing Supabase..."
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
    "nav_page": "🤖 AI Strategy Backtest",
    "_storage_notice": None,
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = deepcopy(value)


# 只有第一次載入或切換資料模式，
# 才重設並讀取對應資料庫。
ACTIVE_MODE = "guest-session" if IS_GUEST else STORAGE_MODE
if st.session_state.get(
    "_storage_active_mode"
) != ACTIVE_MODE:

    try:
        snapshot = {"state": {}, "baseline": None} if IS_GUEST else load_state(STORAGE_MODE)

    except Exception as exc:
        st.error(
            "❌ Unable to load data for the selected mode."
            "The app stopped loading;"
            "it will not fall back to SQLite"
            "to avoid using an incorrect version."
        )
        st.caption(
            "Error type: "
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
    ] = ACTIVE_MODE


# ==========================================
# 4. Telegram 資料讀取
# ==========================================

def get_telegram_data():
    if IS_GUEST:
        return {
            "confirmed_strategy": None,
            "strategy_history": [],
            "pending": None,
            "latest_backtest": None,
        }
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
            "Cloud mode requires TELEGRAM_OWNER_ID"
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
# 5. 左側Navigation
# ==========================================

MENU = [
    "🤖 AI Strategy Backtest",
    "⚖️ A/B Strategy Comparison",
    "📈 Performance Analysis",
    "📋 Trade History",
    "📅 Annual Performance",
    "🧪 In-sample / Out-of-sample",
    "📱 Telegram Records & Import",
    "🔄 Cross-platform Comparison",
]
if IS_GUEST:
    # The owner's Telegram snapshots are intentionally unavailable to guests.
    MENU = [name for name in MENU if not name.startswith(("📱", "🔄"))]


if IS_GUEST and st.session_state.get("nav_page") not in MENU:
    st.session_state["nav_page"] = MENU[0]

with st.sidebar:
    st.title("📈 US Stock Strategy Lab")
    st.caption("Guest workspace | Full AI & backtesting" if IS_GUEST else "Owner workspace v4.3")

    if IS_GUEST:
        st.info("🌐 Guest mode: private data isolated")
        st.caption("AI usage: " + str(st.session_state.get("_guest_ai_used", 0)) + "/5 per session")
    elif IS_CLOUD:
        st.info("☁️ Cloud Mode: Supabase")
    else:
        st.info("💻 Local Mode: SQLite")

    page = st.radio(
        "Navigation",
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
        st.success("✅ Confirmed Strategy")

        st.write(
            "Ticker:",
            confirmed.get("symbol", "Unknown"),
        )

        st.write(
            "Fixed stop loss:",
            setting(
                confirmed.get("stop_loss")
            ),
        )

    else:
        st.info("No confirmed strategy yet")

    if isinstance(pending, dict):
        st.warning("📝 Pending strategy")

    st.divider()
    st.subheader("💾 Session Save" if IS_GUEST else "💾 Save Strategy")

    if st.button(
        "Save Confirmed Strategy and Backtest",
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
                    "❌ Cloud data was modified elsewhere;"
                    "this save was canceled."
                    "Please review the latest cloud version."
                ),
            }

        except Exception as exc:
            result_notice = {
                "status": "error",
                "message": (
                    "❌ Save failed: "
                    + type(exc).__name__
                ),
            }

        st.session_state[
            "_storage_notice"
        ] = result_notice

        st.rerun()

    st.divider()

    show_storage_sidebar()

    if IS_GUEST:
        st.caption("Your guest session cannot read the owner's Telegram records.")
    elif IS_CLOUD:
        st.caption(
            "Telegram records are read from Supabase."
        )
    else:
        st.caption(
            "Telegram and web data are stored separately."
        )


show_notice(
    st.session_state.get("_storage_notice")
)


# ==========================================
# 6. AI 策略回測
# ==========================================

if page == "🤖 AI Strategy Backtest":
    st.title("🤖 AI Natural-language Strategy Backtesting")

    st.write(
        "Describe a trading strategy. Review the AI interpretation,"
        "then run the historical backtest."
    )

    existing = (
        st.session_state["pending_strategy"]
        or st.session_state["confirmed_strategy"]
    )

    new_strategy = st.checkbox(
        "Create a new strategy",
        value=(existing is None),
        help="Leave unchecked when editing an existing strategy.",
    )

    # Public-facing example is display-only: never prefill the input box.
    if IS_GUEST:
        with st.container(border=True):
            st.markdown("**Example strategy (copy and customize):**")
            st.code(
                "Buy AAPL when RSI(14) is below 30.\n"
                "Sell when RSI(14) is above 70.\n"
                "Set a fixed stop loss of 7% and a take profit of 15%.\n"
                "Backtest the past 5 years.",
                language=None,
            )
            st.caption(
                "This is an example only. Enter your own strategy "
                "in the empty field below."
            )

    strategy_text = st.text_area(
        "Enter trading strategy",
        key="strategy_input",
        height=140,
    )

    if st.button(
        "🧠 Parse Strategy with AI",
        type="primary",
        use_container_width=True,
    ):
        if not strategy_text.strip():
            st.warning("Please enter a strategy")

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
                            "No existing strategy to modify;"
                            "please select Create a new strategy."
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

                if IS_GUEST:
                    used = st.session_state.get("_guest_ai_used", 0)
                    if used >= GUEST_AI_PER_SESSION:
                        st.warning("Guest AI limit reached (5 requests per session).")
                        st.stop()
                    budget = guest_ai_budget()
                    with budget["lock"]:
                        if budget["used"] >= GUEST_AI_PER_PROCESS:
                            st.warning("Public AI capacity is temporarily exhausted.")
                            st.stop()
                        budget["used"] += 1
                    st.session_state["_guest_ai_used"] = used + 1

                with st.spinner("AI is parsing..."):
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
                    "Parsed successfully. Please review the strategy."
                )

            except Exception as exc:
                st.error(
                    "Parsing failed: "
                    + str(exc)
                )

    confirmed = st.session_state[
        "confirmed_strategy"
    ]

    pending = st.session_state[
        "pending_strategy"
    ]

    if confirmed is not None:
        with st.expander("✅ Confirmed Strategy"):
            show_strategy(confirmed)

    if pending is not None:
        st.divider()
        st.subheader("📝 Pending Strategy")

        show_strategy(pending)

        base = st.session_state[
            "pending_base_strategy"
        ]

        if isinstance(base, dict):
            with st.expander("Changes from previous strategy"):
                st.text(
                    format_strategy_diff(
                        base,
                        pending,
                    )
                )

        a, b = st.columns(2)

        with a:
            run_clicked = st.button(
                "✅ Confirm & Run Backtest",
                type="primary",
                use_container_width=True,
            )

        with b:
            cancel_clicked = st.button(
                "Discard Pending Strategy",
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
                with st.spinner("Running backtest..."):
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
                    "❌ Backtest failed: "
                    + str(exc)
                )
                st.stop()

            # 重要：
            # 成功保存後才更新已確認策略。
            # 雲端模式直接寫入 Supabase。
            # 本機模式 SQLite 優先。
            try:
                with st.spinner(
                    "Saving backtest..."
                ):
                    notice = persist_state(
                        deepcopy(pending),
                        previous,
                        result,
                    )

            except CloudConflictError:
                st.error(
                    "❌ Supabase version has changed."
                    "To avoid overwriting another session,"
                    "this save was canceled."
                )
                st.info(
                    "Pending strategy is preserved."
                    "Please review the latest cloud data."
                )
                st.stop()

            except Exception as exc:
                st.error(
                    "❌ Save failed;"
                    "new strategy was not confirmed."
                )
                st.caption(
                    "Error type: "
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
            "📊 Latest Backtest Performance"
        )

        strategy = result["strategy"]

        st.caption(
            f"{strategy['symbol']}｜"
            f"{strategy['years']}年｜"
            f"Fixed stop loss "
            f"{setting(strategy.get('stop_loss'))}"
        )

        try:
            scorecards(
                result["stats"],
                get_metrics(result),
            )

            st.subheader("Equity curve")

            st.line_chart(
                equity_curve(result["df"]),
                height=350,
            )

        except Exception as exc:
            st.warning(
                "Unable to display performance: "
                + str(exc)
            )


# ==========================================
# 7. A/B 策略比較
# ==========================================

elif page == "⚖️ A/B Strategy Comparison":
    st.title("⚖️ A/B Strategy Comparison")

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
            "Please create Strategy A，"
            " then edit it to produce Strategy B。"
        )

    elif a == b:
        st.warning("Both strategies are identical")

    else:
        st.write("**Strategy A: Before**")

        st.caption(
            f"{a.get('symbol')}｜"
            f"停損 {setting(a.get('stop_loss'))}"
        )

        st.write("**Strategy B: After**")

        st.caption(
            f"{b.get('symbol')}｜"
            f"停損 {setting(b.get('stop_loss'))}"
        )

        with st.expander(
            "Review rule differences",
            expanded=True,
        ):
            st.text(
                format_strategy_diff(a, b)
            )

        if st.button(
            "🚀 Run A/B Backtest",
            type="primary",
            use_container_width=True,
        ):
            try:
                with st.spinner(
                    "Comparing strategies..."
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

                st.success("A/B comparison completed")

            except Exception as exc:
                st.error(
                    "A/B comparison failed: "
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
                    "Unable to display comparison: "
                    + str(exc)
                )

        st.caption(
            "A/B comparison does not modify the confirmed strategy."
        )


# ==========================================
# 8. Telegram 紀錄與策略匯入
# ==========================================

elif page == "📱 Telegram Records & Import":
    st.title("📱 Telegram Strategy Records")

    st.info(
        (
            "Reading Telegram snapshot from Supabase."
            if IS_CLOUD
            else "Reading local Telegram SQLite records."
        )
        + " Import only creates a pending web proposal."
    )

    if st.button(
        "🔄 Refresh Telegram Records",
        use_container_width=True,
    ):
        st.rerun()

    try:
        snapshot = get_telegram_data()

    except Exception as exc:
        st.error(
            "Unable to load Telegram records: "
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

    st.subheader("✅ Confirmed Telegram Strategy")

    if not isinstance(tg_strategy, dict):
        st.info(
            "No confirmed Telegram strategy."
        )

    else:
        a, b = st.columns(2)

        with a:
            st.metric(
                "Ticker",
                str(tg_strategy.get(
                    "symbol", "Unknown"
                )),
            )

        with b:
            st.metric(
                "Fixed stop loss",
                setting(
                    tg_strategy.get(
                        "stop_loss"
                    )
                ),
            )

        with st.expander(
            "Full Telegram strategy"
        ):
            show_strategy(tg_strategy)

        st.divider()
        st.subheader("📥 Import into Web Workspace")

        web_confirmed = st.session_state[
            "confirmed_strategy"
        ]

        web_pending = st.session_state[
            "pending_strategy"
        ]

        permitted = True

        if isinstance(web_pending, dict):
            st.warning(
                "A pending proposal already exists;"
                "importing will replace it."
            )

            permitted = st.checkbox(
                "I agree to replace the pending proposal"
            )

        if st.button(
            "📥 Import as Pending Web Strategy",
            type="primary",
            use_container_width=True,
            disabled=not permitted,
        ):
            if (
                not tg_strategy.get("symbol")
                or not tg_strategy.get("years")
            ):
                st.error(
                    "Telegram strategy is missing required fields"
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
                    "✅ Imported as a pending strategy."
                    "Review it on the AI Strategy Backtest page."
                )

    st.divider()
    st.subheader("🗂️ Strategy Version History")

    valid_history = [
        item
        for item in history
        if isinstance(item, dict)
    ] if isinstance(history, list) else []

    st.write(
        f"Number of versions:{len(valid_history)}"
    )

    if valid_history:
        index = st.selectbox(
            "Select historical version",
            range(len(valid_history)),
            format_func=lambda i: (
                f"Version {i + 1}｜"
                f"{valid_history[i].get('symbol', 'Unknown')}"
            ),
        )

        show_strategy(valid_history[index])

    else:
        st.info("No historical versions")

    st.divider()
    st.subheader("📝 Telegram Pending Proposal")

    if isinstance(tg_pending, dict):
        proposed = tg_pending.get("strategy")

        if isinstance(proposed, dict):
            show_strategy(proposed)
        else:
            st.warning("Proposal data is incomplete")
    else:
        st.write("No pending proposal")

    st.divider()
    st.subheader("📊 Latest Telegram Backtest")

    if isinstance(record, dict):
        stats = record.get("stats") or {}
        trades = record.get("trades") or []

        st.write(
            "Ticker:",
            record.get("symbol", "Unknown"),
        )

        if isinstance(stats, dict):
            a, b = st.columns(2)

            with a:
                st.metric(
                    "Strategy return",
                    pct(
                        stats.get("total_return"),
                        True,
                    ),
                )

            with b:
                st.metric(
                    "Ending equity",
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
                "⬇️ Export Telegram Trades",
                table.to_csv(
                    index=False
                ).encode("utf-8-sig"),
                file_name="telegram_trades.csv",
                mime="text/csv",
            )

        else:
            st.info("No closed trades")

    else:
        st.info(
            "No saved Telegram backtest"
        )


# ==========================================
# 9. Telegram / Web策略一致性
# ==========================================

elif page == "🔄 Cross-platform Comparison":
    st.title(
        "🔄 Telegram / Web Strategy Comparison"
    )

    st.info(
        "Compare confirmed strategies."
        "This page does not modify the database."
    )

    if st.button(
        "🔄 Recheck",
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
            "Data loading failed: "
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
                "Ticker:",
                tg.get("symbol"),
            )

            st.write(
                "Fixed stop loss:",
                setting(tg.get("stop_loss")),
            )

            with st.expander("View full strategy"):
                show_strategy(tg)

        else:
            st.info("No confirmed strategy")

    with b:
        st.subheader("🌐 Web Workspace")

        if isinstance(wb, dict):
            st.write(
                "Ticker:",
                wb.get("symbol"),
            )

            st.write(
                "Fixed stop loss:",
                setting(wb.get("stop_loss")),
            )

            with st.expander("View full strategy"):
                show_strategy(wb)

        else:
            st.info("No confirmed strategy")

    st.divider()

    if (
        not isinstance(tg, dict)
        or not isinstance(wb, dict)
    ):
        st.warning(
            "At least one side has no confirmed strategy"
        )

    elif tg == wb:
        st.success(
            "✅ Both confirmed strategies match!"
        )

    else:
        st.warning(
            "⚠️ Confirmed strategies differ"
        )

        try:
            st.text(
                format_strategy_diff(tg, wb)
            )
        except Exception:
            st.json({
                "Telegram": tg,
                "Web": wb,
            })

    st.caption(
        "This page compares strategy rules,"
        "not storage version hashes."
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
            "No saved backtest is available."
            "Run a backtest in the AI Strategy page first."
        )
        st.stop()

    df = result["df"]
    trades = result["trades"]
    stats = result["stats"]
    strategy = result["strategy"]
    symbol = strategy["symbol"]

    if page == "📈 Performance Analysis":
        st.title("📈 Detailed Performance Analysis")

        scorecards(
            stats,
            get_metrics(result),
        )

        st.subheader("Equity Performance Chart")

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
                "Trade Quality Analysis"
            ):
                st.text(
                    format_trade_analytics(
                        analysis,
                        symbol=symbol,
                    )
                )

        except Exception as exc:
            st.warning(
                "Trade analysis failed: "
                + str(exc)
            )

    elif page == "📋 Trade History":
        st.title("📋 Historical Trade Details")

        st.write("Ticker:", symbol)

        st.write(
            "Fixed stop loss:",
            setting(strategy.get("stop_loss")),
        )

        st.write(
            "Trailing stop: ",
            setting(
                strategy.get("trailing_stop_pct")
            ),
        )

        st.write(
            "Fixed take profit: ",
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
                "⬇️ Export Trade History CSV",
                table.to_csv(
                    index=False
                ).encode("utf-8-sig"),
                file_name=f"{symbol}_trades.csv",
                mime="text/csv",
            )

        else:
            st.info(
                "No closed trades in this backtest"
            )

    elif page == "📅 Annual Performance":
        st.title("📅 Annual Performance Analysis")

        try:
            yearly = calculate_yearly_performance(
                df,
                10000.0,
            )

            st.text(
                format_yearly_report_en(
                    yearly,
                    symbol=symbol,
                )
            )

        except Exception as exc:
            st.error(
                "Annual analysis failed: "
                + str(exc)
            )

    elif page == "🧪 In-sample / Out-of-sample":
        st.title("🧪 Segmented Performance Analysis")

        st.info(
            "This divides an existing backtest into segments;"
            "it is not an independent out-of-sample test."
        )

        ratio = st.slider(
            "In-sample proportion",
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
                format_oos_report_en(
                    oos,
                    symbol=symbol,
                )
            )

        except Exception as exc:
            st.error(
                "Segmented analysis failed: "
                + str(exc)
            )


st.divider()

st.caption(
    "US Stock Strategy Lab v4.3 | "
    + (
        "Supabase direct save"
        if IS_CLOUD
        else "SQLite-first with Supabase sync"
    )
    + " | Telegram strategies are separate | "
    "Historical performance does not guarantee future results."
)
