
from market_data import get_stock_data
from strategy_engine import evaluate_condition

df = get_stock_data("AAPL", 1).reset_index()

# 收盤價在MA20之上，而且RSI低於40
strategy = {
    "left": {"name": "close"},
    "operator": "cross_above",
    "right": {"name": "ma", "period": 20}
}

signals = evaluate_condition(df, strategy)

print("策略條件引擎測試")
print("資料筆數：", len(df))
print("符合條件天數：", int(signals.sum()))
print(df.loc[signals, ["timestamp", "close"]].tail())
