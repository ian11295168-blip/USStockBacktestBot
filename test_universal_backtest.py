
from universal_backtest import run_universal_backtest

strategy = {
    "symbol": "AAPL",
    "years": 5,
    "entry": {
        "operator": "and",
        "conditions": [
            {
                "left": {"name": "close"},
                "operator": "cross_above",
                "right": {"name": "ma", "period": 20}
            },
            {
                "left": {"name": "rsi", "period": 14},
                "operator": "lt",
                "right": 60
            }
        ]
    },
    "exit": {
        "operator": "or",
        "conditions": [
            {
                "left": {"name": "close"},
                "operator": "lt",
                "right": {"name": "ma", "period": 10}
            },
            {
                "left": {"name": "rsi", "period": 14},
                "operator": "gt",
                "right": 70
            }
        ]
    },
    "stop_loss": 8,
    "take_profit": 20
}

df, trades, stats = run_universal_backtest(strategy)

print("\n===== 通用策略回測完成 =====")
print("股票：", strategy["symbol"])
print("資料來源：Alpaca IEX")
print("交易次數：", stats["trade_count"])
print(f"勝率：{stats['win_rate']:.2f}%")
print(f"策略報酬：{stats['total_return']:.2f}%")
print(f"Buy & Hold：{stats['buy_hold_return']:.2f}%")
print(f"最大回撤：{stats['max_drawdown']:.2f}%")
print(f"期末資產：${stats['final_equity']:.2f}")
print("期末仍持倉：", stats["open_position"])
print("資產曲線欄位：", "equity" in df.columns)

print("\n最近5筆交易：")
for trade in trades[-5:]:
    print(trade)
