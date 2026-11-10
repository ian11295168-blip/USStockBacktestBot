"""Public, isolated, English-language portfolio demo.

No database, OpenAI, Telegram or user-persisted storage is used here.
Market prices are fetched from Alpaca's IEX historical-data feed.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import streamlit as st


INITIAL_CASH = 10_000.0
FEE_RATE = 0.0005
MAX_DEMO_RUNS = 4


@st.cache_data(ttl=3600, show_spinner=False, max_entries=18)
def load_prices(symbol: str, years: int) -> pd.DataFrame:
    """Fetch bounded daily prices from a real market-data provider."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import DataFeed

    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError("Historical market data is not configured")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=366 * years + 45)
    client = StockHistoricalDataClient(key, secret)
    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        feed=DataFeed.IEX,
    )
    bars = client.get_stock_bars(request)
    frame = bars.df
    if frame is None or frame.empty:
        raise ValueError("No daily historical prices returned")
    if isinstance(frame.index, pd.MultiIndex):
        frame = frame.xs(symbol, level="symbol")
    frame = frame.reset_index()
    if "timestamp" not in frame.columns or "close" not in frame.columns:
        raise ValueError("Unexpected market-data format")
    frame = frame[["timestamp", "close"]].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna().drop_duplicates("timestamp").sort_values("timestamp")
    frame = frame[frame["timestamp"] >= (end - timedelta(days=365 * years))].copy()
    if len(frame) < 80:
        raise ValueError("Insufficient historical data for the selected strategy")
    return frame.reset_index(drop=True)


def compute_signal(prices: pd.DataFrame, strategy: str) -> pd.Series:
    close = prices["close"]
    if strategy == "SMA crossover (20 / 50)":
        fast = close.rolling(20, min_periods=20).mean()
        slow = close.rolling(50, min_periods=50).mean()
        return (fast > slow).fillna(False)
    if strategy == "SMA crossover (10 / 30)":
        fast = close.rolling(10, min_periods=10).mean()
        slow = close.rolling(30, min_periods=30).mean()
        return (fast > slow).fillna(False)
    if strategy == "Buy & hold":
        return pd.Series(True, index=prices.index)
    raise ValueError("Unsupported demonstration strategy")


def backtest(prices: pd.DataFrame, strategy: str, stop_pct: float) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Simple cash/long-only daily close execution; signal lagged one bar.

    When a stop is reached at the close, exit occurs at that day's close;
    the stop is therefore a close-based rule, not an intraday stop order.
    """
    df = prices.copy().reset_index(drop=True)
    signal = compute_signal(df, strategy)
    cash = INITIAL_CASH
    shares = 0.0
    entry_price = None
    entry_time = None
    records = []
    equity = []
    for i, row in df.iterrows():
        price = float(row["close"])
        desired = bool(signal.iloc[i - 1]) if i > 0 else False
        stop_hit = bool(shares and entry_price and stop_pct > 0 and price <= entry_price * (1 - stop_pct / 100))
        if shares > 0 and (not desired or stop_hit):
            proceeds = shares * price * (1 - FEE_RATE)
            cost_basis = shares * entry_price * (1 + FEE_RATE)
            records.append({
                "Entry date": entry_time.date().isoformat(),
                "Exit date": row["timestamp"].date().isoformat(),
                "Entry price": round(entry_price, 2),
                "Exit price": round(price, 2),
                "P/L ($)": round(proceeds - cost_basis, 2),
                "Exit reason": "Close-based stop" if stop_hit else "Signal",
            })
            cash = proceeds
            shares = 0.0
            entry_price = entry_time = None
        elif shares == 0 and desired:
            shares = cash / (price * (1 + FEE_RATE))
            cash = 0.0
            entry_price = price
            entry_time = row["timestamp"]
        equity.append(cash + shares * price)
    df["Strategy"] = equity
    df["Buy & hold"] = INITIAL_CASH * df["close"] / float(df["close"].iloc[0])
    returns = df["Strategy"].pct_change().dropna()
    duration = max((df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]).days / 365.25, 1 / 365.25)
    total = df["Strategy"].iloc[-1] / INITIAL_CASH - 1
    cagr = (1 + total) ** (1 / duration) - 1
    drawdown = df["Strategy"] / df["Strategy"].cummax() - 1
    vol = float(returns.std(ddof=1)) if len(returns) > 1 else 0
    sharpe = (float(returns.mean()) / vol * np.sqrt(252)) if vol > 0 else float("nan")
    metrics = {
        "total": total,
        "cagr": cagr,
        "max_drawdown": float(drawdown.min()),
        "sharpe": sharpe,
        "buy_hold": df["Buy & hold"].iloc[-1] / INITIAL_CASH - 1,
        "trades": len(records),
        "final": float(df["Strategy"].iloc[-1]),
    }
    return df, pd.DataFrame(records), metrics


def display_comparison(prices: pd.DataFrame, strategy_a: str, strategy_b: str, stop_pct: float):
    a, _, ma = backtest(prices, strategy_a, stop_pct)
    b, _, mb = backtest(prices, strategy_b, stop_pct)
    comp = pd.DataFrame({
        "Strategy A": a["Strategy"].to_numpy(),
        "Strategy B": b["Strategy"].to_numpy(),
    }, index=prices["timestamp"])
    st.line_chart(comp, height=300)
    st.dataframe(pd.DataFrame({
        "Metric": ["Total return", "CAGR", "Max drawdown", "Sharpe ratio"],
        "Strategy A": [f"{ma['total']:.1%}", f"{ma['cagr']:.1%}", f"{ma['max_drawdown']:.1%}", f"{ma['sharpe']:.2f}"],
        "Strategy B": [f"{mb['total']:.1%}", f"{mb['cagr']:.1%}", f"{mb['max_drawdown']:.1%}", f"{mb['sharpe']:.2f}"],
    }), hide_index=True, use_container_width=True)


def main():
    st.title("US Stock Strategy Lab")
    st.caption("Interactive portfolio demo · Python · Streamlit · Quantitative backtesting")
    st.write(
        "Explore rule-based trading strategies using historical U.S. stock prices. "
        "This public demo is isolated from the owner's private strategy database and does not use the AI API."
    )
    st.info("Guest mode: no account required, no database writes, and no access to private strategies or Telegram records.")

    with st.form("demo_parameters"):
        a, b, c = st.columns(3)
        symbol = a.selectbox("U.S. stock", ["NVDA", "AAPL", "MSFT"])
        strategy = b.selectbox("Strategy", ["SMA crossover (20 / 50)", "SMA crossover (10 / 30)", "Buy & hold"])
        years = c.selectbox("History", [1, 2, 3], index=1, format_func=lambda x: f"{x} year" + ("s" if x > 1 else ""))
        stop_pct = st.slider("Close-based stop-loss (%)", 0, 20, 8, step=1,
                             help="0 disables the stop. Stops are evaluated at daily close, not intraday.")
        run = st.form_submit_button("Run historical backtest", type="primary", use_container_width=True)

    st.caption("Execution assumption: signals available at the prior daily close; transactions at the next day's close. "
               "Commission: 0.05% per side; no slippage modeled. IEX daily feed may differ from consolidated exchange data.")

    if "_demo_runs" not in st.session_state:
        st.session_state["_demo_runs"] = 0
    if run:
        if st.session_state["_demo_runs"] >= MAX_DEMO_RUNS:
            st.warning("This demo session has reached its backtest limit. Please open a new session later.")
        else:
            st.session_state["_demo_runs"] += 1
            try:
                with st.spinner("Fetching historical prices and running the backtest..."):
                    prices = load_prices(symbol, years)
                    result = backtest(prices, strategy, stop_pct)
                st.session_state["_demo_result"] = (prices, result, symbol, strategy, stop_pct)
            except Exception:
                st.error("Market data is temporarily unavailable. Please try again later.")

    saved = st.session_state.get("_demo_result")
    if saved:
        prices, (df, trades, stats), used_symbol, used_strategy, used_stop = saved
        st.subheader("Backtest results")
        st.caption(f"{used_symbol} · {used_strategy} · {len(df)} daily bars · close-based stop {used_stop}%")
        cols = st.columns(4)
        cols[0].metric("Total return", f"{stats['total']:+.2%}")
        cols[1].metric("CAGR", f"{stats['cagr']:+.2%}")
        cols[2].metric("Max drawdown", f"{stats['max_drawdown']:.2%}")
        cols[3].metric("Sharpe ratio", f"{stats['sharpe']:.2f}" if np.isfinite(stats['sharpe']) else "N/A")
        st.subheader("Equity curve · $10,000 initial capital")
        chart = pd.DataFrame({"Strategy": df["Strategy"].to_numpy(),
                              "Buy & hold": df["Buy & hold"].to_numpy()},
                             index=df["timestamp"])
        st.line_chart(chart, height=350)
        st.subheader("Trade history")
        if trades.empty:
            st.info("No closed trades in this historical window.")
        else:
            st.dataframe(trades, hide_index=True, use_container_width=True)
            st.download_button("Download trade history (CSV)", trades.to_csv(index=False).encode("utf-8"),
                               "public_demo_trades.csv", mime="text/csv")
        st.subheader("A/B strategy comparison")
        other = "SMA crossover (10 / 30)" if used_strategy != "SMA crossover (10 / 30)" else "SMA crossover (20 / 50)"
        st.caption(f"A: {used_strategy}   |   B: {other}")
        display_comparison(prices, used_strategy, other, used_stop)

    st.divider()
    st.caption("Educational research prototype. Backtests are hypothetical and are not investment advice. "
               "Past performance does not predict future outcomes. AI-assisted natural-language strategy parsing "
               "is available in the private owner edition, not in the public demo.")


if __name__ == "__main__":
    main()
