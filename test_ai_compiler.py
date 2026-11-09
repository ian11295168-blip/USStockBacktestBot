
import json

from universal_ai_parser import parse_universal_strategy
from universal_backtest import run_universal_backtest

text = (
    "幫我回測NVDA，"
    "當股價連續下跌3天、RSI14低於35，"
    "而且成交量連續2天比前一天少時買進；"
    "當RSI14高於60時賣出。"
    "停損5%，停利10%，回測5年。"
)

print("第一步：AI正在解析中文策略")

strategy = parse_universal_strategy(text)

print(json.dumps(
    strategy,
    ensure_ascii=False,
    indent=2
))

print("\n第二步：開始歷史回測")

df, trades, stats = run_universal_backtest(strategy)

print("\n===== AI策略回測完成 =====")
print("股票：", strategy["symbol"])
print("交易次數：", stats["trade_count"])
print(f"勝率：{stats['win_rate']:.2f}%")
print(f"策略報酬：{stats['total_return']:.2f}%")
print(f"Buy & Hold：{stats['buy_hold_return']:.2f}%")
print(f"最大回撤：{stats['max_drawdown']:.2f}%")
print("資產曲線：", "equity" in df.columns)
