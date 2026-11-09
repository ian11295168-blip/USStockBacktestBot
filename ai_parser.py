import os
import json

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

print("API KEY loaded:", bool(os.getenv("OPENAI_API_KEY")))

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def parse_strategy(user_text):

    response = client.responses.create(
        model="gpt-5.6",
        input=[
            {
                "role": "system",
                "content": (
                    "你是一個美股交易策略解析器。"
                    "你的工作不是提供投資建議，"
                    "而是把使用者的中文交易策略轉成 JSON。"
                    "\n\n"
                    "目前只支援以下策略："
                    "\n1. MA 均線交叉"
                    "\n2. RSI"
                    "\n3. 固定停損"
                    "\n4. 固定停利"
                    "\n\n"
                    "股票代號必須轉成大寫。"
                    "如果使用者沒有指定回測年數，預設為 5 年。"
                )
            },
            {
                "role": "user",
                "content": user_text
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "stock_strategy",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string"
                        },
                        "years": {
                            "type": "integer"
                        },
                        "strategy_type": {
                            "type": "string",
                            "enum": [
                                "ma_cross",
                                "rsi"
                            ]
                        },
                        "fast_ma": {
                            "type": ["integer", "null"]
                        },
                        "slow_ma": {
                            "type": ["integer", "null"]
                        },
                        "rsi_period": {
                            "type": ["integer", "null"]
                        },
                        "rsi_buy": {
                            "type": ["number", "null"]
                        },
                        "rsi_sell": {
                            "type": ["number", "null"]
                        },
                        "stop_loss": {
                            "type": ["number", "null"]
                        },
                        "take_profit": {
                            "type": ["number", "null"]
                        }
                    },
                    "required": [
                        "symbol",
                        "years",
                        "strategy_type",
                        "fast_ma",
                        "slow_ma",
                        "rsi_period",
                        "rsi_buy",
                        "rsi_sell",
                        "stop_loss",
                        "take_profit"
                    ],
                    "additionalProperties": False
                }
            }
        }
    )

    return json.loads(
        response.output_text
    )


if __name__ == "__main__":

    text = (
        "幫我回測 AAPL，"
        "20日均線上穿60日均線買進，"
        "下穿就賣出，"
        "停損8%，"
        "回測5年"
    )

    strategy = parse_strategy(text)

    print(strategy)