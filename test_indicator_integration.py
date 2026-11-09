
from market_data import get_stock_data
from indicator_engine import calculate_indicator

# 取得 NVDA 歷史資料
df = get_stock_data("NVDA", years=2)

# 計算技術指標
df["MA20"] = calculate_indicator(
    df, "ma", period=20
)

df["RSI14"] = calculate_indicator(
    df, "rsi", period=14
)

df["MACD"] = calculate_indicator(
    df, "macd", output="line"
)

df["MACD_SIGNAL"] = calculate_indicator(
    df, "macd", output="signal"
)

# 組合買進條件：
# MACD 黃金交叉 + 收盤價高於 MA20
previous_macd = df["MACD"].shift(1)
previous_signal = df["MACD_SIGNAL"].shift(1)

golden_cross = (
    (previous_macd <= previous_signal)
    & (df["MACD"] > df["MACD_SIGNAL"])
)

above_ma20 = df["close"] > df["MA20"]

buy_signal = golden_cross & above_ma20

print("資料筆數：", len(df))
print("買進訊號次數：", int(buy_signal.sum()))
print("最近5筆資料：")
print(df[["close", "MA20", "MACD", "MACD_SIGNAL"]].tail())

assert len(df) > 30
assert df["MACD"].notna().any()
assert df["MACD_SIGNAL"].notna().any()

print("\n✅ 通用指標與真實股價資料整合成功")
