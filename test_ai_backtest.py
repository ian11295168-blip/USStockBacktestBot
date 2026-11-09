
from ai_parser import parse_strategy
from backtest import run_strategy_backtest

text = (
    "幫我回測 NVDA，"
    "10日均線上穿50日均線買進，"
    "下穿賣出，停損7%，回測3年"
)

print("AI 正在解析策略...")

strategy = parse_strategy(text)

print("AI 解析結果：")
print(strategy)

print("\n開始歷史回測...")

df, trades, stats = run_strategy_backtest(strategy)

print("\n回測完成！")
print(f"交易次數：{stats['trade_count']}")
print(f"勝率：{stats['win_rate']:.2f}%")
print(f"總報酬：{stats['total_return']:.2f}%")
print(f"Buy & Hold：{stats['buy_hold_return']:.2f}%")
print(f"最大回撤：{stats['max_drawdown']:.2f}%")
