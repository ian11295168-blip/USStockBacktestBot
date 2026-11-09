
import json

from universal_ai_parser import parse_universal_strategy
from universal_backtest import run_universal_backtest

text = (
    "AAPL 收盤價向上突破20日均線，"
    "而且RSI14低於60時買進；"
    "收盤價向下跌破10日均線，"
    "或RSI14高於70時賣出。"
    "停損8%，停利20%，回測5年。"
)

print("第一步：AI解析中文策略")

strategy = parse_universal_strategy(text)

print(json.dumps(
    strategy,
    ensure_ascii=False,
    indent=2
))

print("\n第二步：開始通用策略回測")

df, trades, stats = run_universal_backtest(strategy)

print("\n===== AI通用策略回測完成 =====")
print(f"股票：{strategy['symbol']}")
print(f"交易次數：{stats['trade_count']}")
print(f"勝率：{stats['win_rate']:.2f}%")
print(f"策略報酬：{stats['total_return']:.2f}%")
print(f"Buy & Hold：{stats['buy_hold_return']:.2f}%")
print(f"最大回撤：{stats['max_drawdown']:.2f}%")
print(f"期末資產：${stats['final_equity']:.2f}")
print(f"資產曲線：{'equity' in df.columns}")

print("\n最近3筆交易：")
for trade in trades[-3:]:
    print(trade)
