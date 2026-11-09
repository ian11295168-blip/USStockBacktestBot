
import json
import pandas as pd

from universal_ai_parser import parse_universal_strategy
from strategy_validator import validate_strategy
from strategy_engine import evaluate_condition


text = (
    "NVDA收盤價高於前20個交易日最高價，"
    "而且成交量大於20日均量1.5倍時買進；"
    "收盤價低於10日均線時賣出。"
    "停損5%，回測5年。"
)

# AI將中文轉成JSON
strategy = parse_universal_strategy(text)

print("=== AI產生的策略 ===")
print(json.dumps(
    strategy,
    ensure_ascii=False,
    indent=2
))

# 獨立驗證
assert validate_strategy(strategy)

print("\n✅ 策略驗證成功")

# 使用模擬資料測試條件運算
# 不需要呼叫Alpaca
n = 100

df = pd.DataFrame({
    "open": [100 + i * 0.2 for i in range(n)],
    "high": [102 + i * 0.2 for i in range(n)],
    "low": [98 + i * 0.2 for i in range(n)],
    "close": [100 + i * 0.2 for i in range(n)],
    "volume": [100000 + i * 1000 for i in range(n)]
})

entry = evaluate_condition(
    df, strategy["entry"]
)

exit_signal = evaluate_condition(
    df, strategy["exit"]
)

assert len(entry) == n
assert len(exit_signal) == n
assert entry.dtype == bool
assert exit_signal.dtype == bool

print("✅ 買進條件可以運算")
print("✅ 賣出條件可以運算")

print("買進訊號次數：", int(entry.sum()))
print("賣出訊號次數：", int(exit_signal.sum()))

print("\n✅ AI時間序列策略整合測試完成")
