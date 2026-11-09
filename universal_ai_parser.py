
import os
import re
import json
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ConfigDict

from strategy_validator import (
    validate_strategy,
    validate_operand as check_expression
)

from position_rules import validate_position_rule


load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Operand(StrictModel):
    name: Optional[str]
    period: Optional[int]
    multiplier: Optional[float]
    number: Optional[float]

    fast: Optional[int]
    slow: Optional[int]
    signal: Optional[int]
    output: Optional[str]
    deviation: Optional[float]
    smooth: Optional[int]

    operation: Optional[str]
    source: Optional["Operand"]
    left: Optional["Operand"]
    right: Optional["Operand"]


class Condition(StrictModel):
    operator: str
    left: Optional[Operand]
    right: Optional[Operand]
    conditions: Optional[list["Condition"]]
    period: Optional[int]
    condition: Optional["Condition"]


# 新增：獨立的持倉條件結構
class PositionCondition(StrictModel):
    operator: str
    metric: Optional[str]
    value: Optional[float]
    conditions: Optional[list["PositionCondition"]]


class Strategy(StrictModel):
    supported: bool
    reason: Optional[str]

    symbol: Optional[str]
    years: Optional[int]
    entry: Optional[Condition]
    exit: Optional[Condition]

    stop_loss: Optional[float]
    take_profit: Optional[float]
    max_hold_days: Optional[int]
    trailing_stop_pct: Optional[float]

    # 新增：通用持倉出場規則
    position_exit: Optional[PositionCondition]


COMPARE_OPERATORS = {
    "gt", "gte", "lt", "lte",
    "cross_above", "cross_below"
}

POSITION_OPERATORS = {
    "gt", "gte", "lt", "lte", "eq"
}

POSITION_METRICS = {
    "holding_days",
    "return_pct",
    "peak_return_pct",
    "pullback_pct"
}


def validate_operand(operand):
    """將AI輸出的Operand轉為引擎格式。"""

    if operand is None:
        raise ValueError("缺少比較對象")

    raw = operand.model_dump(
        exclude_none=True
    )

    def convert(node):
        if isinstance(node, dict):
            if "number" in node:
                if set(node) != {"number"}:
                    raise ValueError(
                        "固定數字不能混用指標參數"
                    )
                return node["number"]

            result = {}

            for key, value in node.items():
                if key in (
                    "source", "left", "right"
                ):
                    result[key] = convert(value)
                else:
                    result[key] = value

            return result

        return node

    expression = convert(raw)

    check_expression(expression)

    return expression


def validate_condition(node, depth=0):
    """轉換一般買進與賣出條件。"""

    if node is None or depth > 8:
        raise ValueError(
            "策略條件缺失或過於複雜"
        )

    op = node.operator

    if op == "consecutive":
        if (
            type(node.period) is not int
            or not 2 <= node.period <= 250
            or node.condition is None
        ):
            raise ValueError(
                "連續條件格式錯誤"
            )

        if (
            node.left is not None
            or node.right is not None
            or node.conditions is not None
        ):
            raise ValueError(
                "連續條件不可混用其他欄位"
            )

        return {
            "operator": "consecutive",
            "period": node.period,
            "condition": validate_condition(
                node.condition,
                depth + 1
            )
        }

    if op in ("and", "or"):
        if (
            node.left is not None
            or node.right is not None
            or node.period is not None
            or node.condition is not None
        ):
            raise ValueError(
                "AND/OR條件格式錯誤"
            )

        children = node.conditions

        if not children or len(children) > 20:
            raise ValueError(
                "AND/OR子條件數量錯誤"
            )

        return {
            "operator": op,
            "conditions": [
                validate_condition(
                    child, depth + 1
                )
                for child in children
            ]
        }

    if op not in COMPARE_OPERATORS:
        raise ValueError(
            f"不支援的比較運算子：{op}"
        )

    if (
        node.conditions is not None
        or node.period is not None
        or node.condition is not None
    ):
        raise ValueError(
            "比較條件不能混用其他欄位"
        )

    return {
        "operator": op,
        "left": validate_operand(node.left),
        "right": validate_operand(node.right)
    }


def convert_position_condition(node, depth=0):
    """將AI持倉條件轉成position_rules格式。"""

    if node is None:
        return None

    if depth > 8:
        raise ValueError(
            "持倉條件過於複雜"
        )

    op = node.operator

    if op in ("and", "or"):
        if (
            node.metric is not None
            or node.value is not None
        ):
            raise ValueError(
                "持倉AND/OR不能混用比較值"
            )

        children = node.conditions

        if not children or not 2 <= len(children) <= 20:
            raise ValueError(
                "持倉AND/OR需要2至20個子條件"
            )

        result = {
            "operator": op,
            "conditions": [
                convert_position_condition(
                    child, depth + 1
                )
                for child in children
            ]
        }

    elif op in POSITION_OPERATORS:
        if node.conditions is not None:
            raise ValueError(
                "持倉比較條件不能包含子條件"
            )

        if node.metric not in POSITION_METRICS:
            raise ValueError(
                f"不支援的持倉資訊：{node.metric}"
            )

        if node.value is None:
            raise ValueError(
                "持倉條件缺少比較值"
            )

        value = node.value

        # holding_days必須轉成整數
        if node.metric == "holding_days":
            if (
                type(value) not in (int, float)
                or not float(value).is_integer()
            ):
                raise ValueError(
                    "持有天數必須是整數"
                )

            value = int(value)

        result = {
            "operator": op,
            "metric": node.metric,
            "value": value
        }

    else:
        raise ValueError(
            f"不支援的持倉運算子：{op}"
        )

    validate_position_rule(result)

    return result


AI_INSTRUCTIONS = """
你是美股交易策略解析器。
將使用者的中文交易策略轉換為結構化JSON。
不提供投資建議，也不執行真實交易。

基本規則：
1. 只允許目前回測引擎支援的條件。
2. 不得猜測、替換、刪除未提及的條件。
3. 遇到無法支援或重要歧義時，
   supported=false，reason用中文說明。
4. supported=true時，輸出完整策略。
5. 沒有使用的模型欄位一律填null。
6. 只支援單一股票、多頭、單一持倉。
7. 沒指定回測年數時預設5年。
8. 百分比用直接數字，例如5%填5。

一般買進與賣出條件：
entry和exit必須是完整Condition。
支援open、high、low、close、volume。
支援ma、volume_ma、rsi、ema、
macd、bollinger、stochastic、
down_days、up_days、volume_down_days。

RSI14：
name=rsi，period=14。
20日均線：
name=ma，period=20。
EMA20：
name=ema，period=20。
20日均量：
name=volume_ma，period=20。

比較運算子：
gt、gte、lt、lte、
cross_above、cross_below。
固定數字使用Operand.number。
例如RSI14低於30：
left是RSI14指標，
operator=lt，
right的number為30。

AND/OR條件：
operator=and或or，
conditions放完整子條件。

任意條件連續N個交易日成立：
operator=consecutive，
period=N，
condition放完整比較或邏輯條件。

MACD標準參數：
fast=12，slow=26，signal=9。
output=line表示DIF線，
output=signal表示訊號線，
output=histogram表示柱狀圖。
黃金交叉使用cross_above。
死亡交叉使用cross_below。

布林通道：
預設period=20、deviation=2。
output=upper、middle、lower。

KD：
預設period=14、smooth=3。
output=k或d。

指標倍數：
使用Operand.multiplier。
例如成交量高於20日均量1.5倍，
右側使用volume_ma、
period=20、multiplier=1.5。

時間序列運算：
lag、rolling_max、rolling_min、
add、sub、mul、div。

「前20個交易日最高價」不含今天，
應使用：
lag(rolling_max(high,20),1)。
不得錯誤使用含當日的區間最高價。

固定停損：
頂層stop_loss。
從買進成本下跌5%停損，
stop_loss=5。

固定停利：
頂層take_profit。
獲利20%停利，
take_profit=20。

最大持有期限：
頂層max_hold_days。
最多持有10個交易日，
max_hold_days=10。
未設定則為null。
「至少持有10天才能賣」不等於
最大持有期限，目前不支援。

追蹤停損：
頂層trailing_stop_pct。
買進後，從持有期間最高價回落8%
設定trailing_stop_pct=8。
未設定則為null。
使用最高價，不是最高收盤價。
依日K回測模型，當天新高要到
下一交易日才提高追蹤停損線。

新增功能：通用持倉出場條件。
頂層欄位position_exit。
這些條件只能放在position_exit，
不可塞進一般entry或exit。

position_exit可用的metric：

holding_days：
已持有的交易日數。
買進當天算第1天。
例：「持有滿5個交易日」
metric=holding_days，
operator=gte，value=5。

return_pct：
現在收盤價相對實際買進價格
的報酬百分比，尚未扣除賣出費用。
例：「目前報酬低於3%」
metric=return_pct，
operator=lt，value=3。

peak_return_pct：
從買進後，到目前為止的
最高收盤價相對買進價格
的報酬百分比。
例：「曾經獲利至少10%」
metric=peak_return_pct，
operator=gte，value=10。

pullback_pct：
從買進後已知的最高收盤價，
回落到目前收盤價的百分比。
例：「最高收盤價回落至少5%」
metric=pullback_pct，
operator=gte，value=5。

持倉比較運算子：
gt、gte、lt、lte、eq。
每個比較條件只使用：
operator、metric、value。
conditions必須為null。

持倉AND/OR：
operator=and或or。
conditions填2至20個子條件。
metric與value必須為null。

舉例一：
「持有滿5天，報酬還不到3%就賣」
position_exit為AND：
1. holding_days gte 5
2. return_pct lt 3

舉例二：
「曾獲利10%，後來從最高收盤價
回落至少5%，就賣出」
position_exit為AND：
1. peak_return_pct gte 10
2. pullback_pct gte 5

注意：
position_exit在每天收盤後評估，
訊號成立時，下一個交易日開盤出場。
不得誤認為當天收盤成交。

trailing_stop_pct與
position_exit.pullback_pct不同：
trailing_stop_pct使用日K最高價，
可以盤中模擬停損觸發。
position_exit.pullback_pct使用
最高收盤價及當日收盤價，
隔天開盤才執行出場。
不可自行混用。

若使用者只說：
「最高價回落5%就賣」
但無法確認是盤中最高價
還是最高收盤價，
應要求澄清。

新規則不能表達：
1. 持倉條件滿足時立即盤中成交。
2. 分批賣出或加碼。
3. 做空。
4. 持倉狀態規則的動態停損價格。
5. 尚未提供一般exit條件，
   卻要求以position_exit作為唯一賣出條件。

若目前架構無法完整表達原意，
supported=false，reason說明。

多輪修改：
若輸入包含上一份完整策略JSON，
必須保留未要求改動的所有欄位，
包括entry、exit、stop_loss、
take_profit、max_hold_days、
trailing_stop_pct、position_exit。

「把持倉出場改成持有7天且報酬
低於3%，其他不變」：
只更新position_exit。

「取消持倉條件」：
position_exit=null，
其他欄位不變。

「追蹤停損改成6%」：
只更新trailing_stop_pct。

「取消最大持有期限」：
max_hold_days=null。

不能把「取消某項規則」
誤解成「復原上一版策略」。

若要求「新增另一個持倉出場條件」，
必須依使用者意思用OR或AND組合。
如果使用者沒有明確說明兩個
持倉條件之間的關係，
請先要求澄清，不可猜測。

修改時不得自行改變
任何原本存在的巢狀條件。
"""


def parse_universal_strategy(
    text,
    base_strategy=None
):
    """解析完整策略或修改既有策略。"""

    if not isinstance(text, str) or not text.strip():
        raise ValueError("請提供交易策略文字")

    if base_strategy is not None:
        original = json.loads(
            json.dumps(
                base_strategy,
                ensure_ascii=False
            )
        )

        # 舊版SQLite策略相容
        original.setdefault(
            "max_hold_days", None
        )
        original.setdefault(
            "trailing_stop_pct", None
        )
        original.setdefault(
            "position_exit", None
        )

        prompt_text = (
            "目前已存在的完整策略JSON：\n"
            + json.dumps(
                original,
                ensure_ascii=False
            )
            + "\n\n使用者的新修改要求：\n"
            + text
            + "\n\n請回傳修改後的完整策略。"
            "除使用者明確要求的內容外，"
            "所有欄位必須完全保留。"
            "有歧義時supported=false。"
        )
    else:
        prompt_text = text

    response = client.responses.parse(
        model="gpt-5.6",
        instructions=AI_INSTRUCTIONS,
        input=prompt_text,
        text_format=Strategy,
        store=False
    )

    result = response.output_parsed

    if result is None:
        raise ValueError(
            "AI未能產生有效策略"
        )

    if not result.supported:
        raise ValueError(
            result.reason
            or "目前不支援這個策略"
        )

    if (
        result.symbol is None
        or result.years is None
        or result.entry is None
        or result.exit is None
    ):
        raise ValueError(
            "缺少必要的完整策略資訊"
        )

    symbol = result.symbol.strip().upper()

    if not re.fullmatch(
        r"[A-Z]{1,5}(\.[A-Z])?",
        symbol
    ):
        raise ValueError(
            "股票代號格式不正確"
        )

    if (
        type(result.years) is not int
        or not 1 <= result.years <= 10
    ):
        raise ValueError(
            "回測年數必須是1至10"
        )

    position_exit = convert_position_condition(
        result.position_exit
    )

    strategy = {
        "symbol": symbol,
        "years": result.years,
        "entry": validate_condition(
            result.entry
        ),
        "exit": validate_condition(
            result.exit
        ),
        "stop_loss": result.stop_loss,
        "take_profit": result.take_profit,
        "max_hold_days": result.max_hold_days,
        "trailing_stop_pct": (
            result.trailing_stop_pct
        ),
        "position_exit": position_exit
    }

    validate_strategy(strategy)

    return strategy


if __name__ == "__main__":
    text = (
        "NVDA的RSI14低於30買進，"
        "RSI14高於70賣出，"
        "買進後持有滿5個交易日，"
        "如果報酬低於3%就賣出，"
        "回測5年。"
    )

    try:
        result = parse_universal_strategy(text)

        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2
            )
        )

    except ValueError as error:
        print(
            "策略無法執行：",
            error
        )
