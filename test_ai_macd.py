
import json

from universal_ai_parser import parse_universal_strategy
from strategy_engine import evaluate_condition
from market_data import get_stock_data

text = (
    "NVDA的MACD黃金交叉，"
    "而且收盤價高於20日均線時買進；"
    "MACD死亡交叉時賣出。"
    "停損5%，回測5年。"
)

strategy = parse_universal_strategy(text)

print("=== AI解析結果 ===")
print(json.dumps(
    strategy,
    ensure_ascii=False,
    indent=2
))

# 檢查AI是否真的產生MACD交叉條件
def contains_macd(node):
    if node["operator"] in ("and", "or"):
        return any(
            contains_macd(child)
            for child in node["conditions"]
        )

    return any(
        isinstance(node.get(side), dict)
        and node[side].get("name") == "macd"
        for side in ("left", "right")
    )


assert contains_macd(strategy["entry"])
assert contains_macd(strategy["exit"])

# 檢查策略能否由引擎計算
df = get_stock_data("NVDA", years=5)

entry = evaluate_condition(df, strategy["entry"])
exit_signal = evaluate_condition(df, strategy["exit"])

assert len(entry) == len(df)
assert len(exit_signal) == len(df)

print("買進訊號次數：", int(entry.sum()))
print("賣出訊號次數：", int(exit_signal.sum()))

print("\n✅ AI解析與通用策略引擎整合成功")
