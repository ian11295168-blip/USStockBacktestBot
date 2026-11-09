
import json

from universal_ai_parser import parse_universal_strategy
from strategy_validator import validate_strategy
from strategy_summary_v2 import format_strategy_summary


# 使用自然語言描述交易策略
text = (
    "NVDA的RSI14連續3個交易日低於30才買進；"
    "RSI14高於70時賣出。"
    "停損5%，回測5年。"
)

print("正在測試AI自然語言策略理解...\n")

# 呼叫AI解析中文策略
strategy = parse_universal_strategy(text)

print("=== AI產生的策略JSON ===")
print(
    json.dumps(
        strategy,
        ensure_ascii=False,
        indent=2
    )
)

# 檢查完整策略
assert validate_strategy(strategy)

assert strategy["symbol"] == "NVDA"
assert strategy["years"] == 5
assert strategy["stop_loss"] == 5

print("\n✅ 基本策略設定正確")


# 檢查AI有沒有真正理解連續3天
entry = strategy["entry"]

assert entry["operator"] == "consecutive", (
    "AI沒有產生consecutive連續條件"
)

assert entry["period"] == 3, (
    "AI沒有正確設定連續3天"
)

inner = entry["condition"]

assert inner["operator"] == "lt", (
    "AI沒有正確理解低於30"
)

assert inner["left"]["name"] == "rsi"
assert inner["left"]["period"] == 14
assert inner["right"] == 30

print("✅ AI正確理解RSI14連續3天低於30")


# 檢查賣出條件
exit_rule = strategy["exit"]

assert exit_rule["operator"] == "gt"
assert exit_rule["left"]["name"] == "rsi"
assert exit_rule["left"]["period"] == 14
assert exit_rule["right"] == 70

print("✅ AI正確理解RSI14高於70賣出")


# 檢查Telegram中文摘要
summary = format_strategy_summary(strategy)

print("\n=== Telegram策略摘要 ===")
print(summary)

assert "連續3個交易日" in summary
assert "RSI14" in summary

print("\n✅ AI連續條件整合測試全部通過")
