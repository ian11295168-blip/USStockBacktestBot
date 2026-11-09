
"""US Stock Strategy Lab v4.1
Supabase 網頁回測資料還原模組。

依照 web_storage.py schema_version=1 的真實格式：

payload = {
    "schema_version": 1,
    "confirmed_strategy": {...},
    "previous_confirmed_strategy": {...},
    "last_result": {
        "strategy": {...},
        "trades": [...],
        "stats": {...},
        "df_json": "[...]"
    }
}

功能：
- 將 df_json 還原成 pandas DataFrame
- 還原 timestamp 的 UTC 日期格式
- 驗證 close、equity 等必要欄位
- 恢復成 web_app.py 可使用的資料結構
- 可將雲端資料還原後重新計算績效
- 不連接或修改任何資料庫
"""

from io import StringIO

import pandas as pd


class CloudDataFormatError(ValueError):
    """雲端資料格式不正確。"""


REQUIRED_COLUMNS = (
    "timestamp",
    "close",
    "equity",
)


def restore_dataframe(df_json):
    """將 pandas records JSON 還原成 DataFrame。"""

    if not isinstance(df_json, str):
        raise CloudDataFormatError(
            "df_json 必須是 JSON 字串"
        )

    if not df_json.strip():
        raise CloudDataFormatError(
            "df_json 不可為空"
        )

    try:
        df = pd.read_json(
            StringIO(df_json),
            orient="records",
        )

    except (ValueError, TypeError) as exc:
        raise CloudDataFormatError(
            "df_json 無法還原為 DataFrame"
        ) from exc

    if not isinstance(df, pd.DataFrame):
        raise CloudDataFormatError(
            "還原結果不是 DataFrame"
        )

    if df.empty:
        raise CloudDataFormatError(
            "回測 DataFrame 沒有資料"
        )

    missing = [
        name for name in REQUIRED_COLUMNS
        if name not in df.columns
    ]

    if missing:
        raise CloudDataFormatError(
            "回測 DataFrame 缺少必要欄位："
            + ", ".join(missing)
        )

    try:
        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            utc=True,
            errors="raise",
        )

        for name in ("close", "equity"):
            df[name] = pd.to_numeric(
                df[name],
                errors="raise",
            )

    except (TypeError, ValueError) as exc:
        raise CloudDataFormatError(
            "回測時間或數值格式不正確"
        ) from exc

    if df["timestamp"].isna().any():
        raise CloudDataFormatError(
            "回測資料包含無效時間"
        )

    if df[["close", "equity"]].isna().any().any():
        raise CloudDataFormatError(
            "回測資料包含無效的收盤價或資產"
        )

    if not (
        df["close"].gt(0).all()
        and df["equity"].ge(0).all()
    ):
        raise CloudDataFormatError(
            "回測資料包含異常價格或資產"
        )

    return df


def restore_web_payload(payload):
    """還原 web_storage.py 的完整網頁狀態。"""

    if not isinstance(payload, dict):
        raise CloudDataFormatError(
            "雲端 payload 必須是字典"
        )

    if payload.get("schema_version") != 1:
        raise CloudDataFormatError(
            "不支援的 schema_version"
        )

    confirmed = payload.get(
        "confirmed_strategy"
    )

    previous = payload.get(
        "previous_confirmed_strategy"
    )

    if confirmed is not None and not isinstance(
        confirmed, dict
    ):
        raise CloudDataFormatError(
            "已確認策略格式不正確"
        )

    if previous is not None and not isinstance(
        previous, dict
    ):
        raise CloudDataFormatError(
            "上一版策略格式不正確"
        )

    stored_result = payload.get("last_result")

    result = None

    if stored_result is not None:
        if not isinstance(stored_result, dict):
            raise CloudDataFormatError(
                "last_result 格式不正確"
            )

        strategy = stored_result.get("strategy")
        trades = stored_result.get("trades")
        stats = stored_result.get("stats")

        if not isinstance(strategy, dict):
            raise CloudDataFormatError(
                "回測策略格式不正確"
            )

        if not isinstance(trades, list):
            raise CloudDataFormatError(
                "交易紀錄格式不正確"
            )

        if not isinstance(stats, dict):
            raise CloudDataFormatError(
                "回測統計格式不正確"
            )

        df = restore_dataframe(
            stored_result.get("df_json")
        )

        result = {
            "strategy": strategy,
            "df": df,
            "trades": trades,
            "stats": stats,
        }

    return {
        "confirmed_strategy": confirmed,
        "previous_confirmed_strategy": previous,
        "last_result": result,
    }


def restore_cloud_web_state(record):
    """將 cloud_web_storage 讀出的紀錄還原。

    record 為：
        load_cloud_web_state() 的回傳結果。

    回傳：
        與 load_web_state() 相同的網頁狀態格式。
    """

    if record is None:
        return None

    if not isinstance(record, dict):
        raise CloudDataFormatError(
            "雲端資料列格式不正確"
        )

    if record.get("id") != 1:
        raise CloudDataFormatError(
            "雲端 web_state ID 不正確"
        )

    return restore_web_payload(
        record.get("payload")
    )
