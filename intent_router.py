
import os
import json

from typing import Literal
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ConfigDict

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


class IntentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal[
        "new",
        "modify",
        "undo",
        "show",
        "clarify",
        "unknown"
    ]

    reason: str


def detect_intent(
    text,
    has_strategy=False,
    has_incomplete=False,
    has_history=False
):
    context = {
        "user_message": text,
        "has_existing_strategy": has_strategy,
        "has_incomplete_strategy": has_incomplete,
        "has_previous_version": has_history
    }

    response = client.responses.parse(
        model="gpt-5.6",
        instructions=(
            "你是美股回測機器人的對話意圖辨識器。"
            "你的工作只有判斷使用者的意圖，"
            "不要解析交易策略，也不要執行回測。"

            "可用意圖："
            "new：建立一份新策略。"
            "modify：修改上一份策略的條件。"
            "undo：恢復上一個策略版本。"
            "show：查詢目前策略內容。"
            "clarify：補充上一個不完整策略的資訊。"
            "unknown：無法確定意圖。"

            "請根據自然語言意思判斷，"
            "不要只匹配固定關鍵字。"

            "例如："
            "『幫我測NVDA連跌3天買進』屬於new。"
            "『停損改成5%』屬於modify。"
            "『把成交量條件刪掉』屬於modify。"
            "『改回上一個步驟』屬於undo。"
            "『剛剛的修改不要了』屬於undo。"
            "『現在的進場條件是什麼』屬於show。"
            "『成交量是連續兩天比前一天少』"
            "若正在等待補充資訊，屬於clarify。"

            "如果沒有待補充策略，"
            "不要把獨立的短句判成clarify。"
            "如果意圖不明確，回傳unknown。"
            "只判斷意圖，不得自行更改策略。"
        ),
        input=json.dumps(
            context,
            ensure_ascii=False
        ),
        text_format=IntentResult,
        store=False
    )

    result = response.output_parsed

    if result is None:
        raise ValueError("AI 無法判斷使用者意圖")

    return result.intent


if __name__ == "__main__":
    samples = [
        "幫我回測NVDA連跌3天買進",
        "RSI賣出門檻改成70",
        "我不要剛剛那個版本了",
        "幫我看現在的買賣條件",
        "成交量是連續2天比前一天少"
    ]

    for message in samples:
        intent = detect_intent(
            message,
            has_strategy=True,
            has_incomplete=True,
            has_history=True
        )

        print(message, "→", intent)
