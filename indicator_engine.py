
import pandas as pd

from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import MACD, EMAIndicator, SMAIndicator
from ta.volatility import BollingerBands


def calculate_indicator(df, name, period=14, **params):
    """
    統一的技術指標計算介面。

    df: 股票歷史資料
    name: 技術指標名稱
    period: 計算週期
    params: 其他參數
    """

    name = name.lower()

    close = df["close"]

    if name == "close":
        return close

    if name == "volume":
        return df["volume"]

    if name in ("ma", "sma"):
        return SMAIndicator(
            close=close,
            window=period
        ).sma_indicator()

    if name == "ema":
        return EMAIndicator(
            close=close,
            window=period
        ).ema_indicator()

    if name == "rsi":
        return RSIIndicator(
            close=close,
            window=period
        ).rsi()

    if name == "macd":
        fast = params.get("fast", 12)
        slow = params.get("slow", 26)
        signal = params.get("signal", 9)
        output = params.get("output", "line")

        indicator = MACD(
            close=close,
            window_fast=fast,
            window_slow=slow,
            window_sign=signal
        )

        if output == "signal":
            return indicator.macd_signal()

        if output == "histogram":
            return indicator.macd_diff()

        return indicator.macd()

    if name == "bollinger":
        deviation = params.get("deviation", 2)
        output = params.get("output", "middle")

        indicator = BollingerBands(
            close=close,
            window=period,
            window_dev=deviation
        )

        if output == "upper":
            return indicator.bollinger_hband()

        if output == "lower":
            return indicator.bollinger_lband()

        return indicator.bollinger_mavg()

    if name == "stochastic":
        smooth = params.get("smooth", 3)
        output = params.get("output", "k")

        indicator = StochasticOscillator(
            high=df["high"],
            low=df["low"],
            close=close,
            window=period,
            smooth_window=smooth
        )

        if output == "d":
            return indicator.stoch_signal()

        return indicator.stoch()

    raise ValueError(f"尚未支援指標：{name}")
