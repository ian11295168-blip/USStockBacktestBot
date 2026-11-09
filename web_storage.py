
"""Streamlit 網頁版的獨立 SQLite 資料儲存模組。"""

import json
import math
import sqlite3
from contextlib import closing
from datetime import date, datetime
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd


DB_PATH = (
    Path(__file__).resolve().parent
    / "web_backtest.db"
)


def json_default(value):
    """將 pandas / numpy 資料轉為 JSON 格式。"""

    if isinstance(
        value,
        (datetime, date, pd.Timestamp),
    ):
        return value.isoformat()

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.floating):
        number = float(value)

        if math.isfinite(number):
            return number

        return None

    if isinstance(value, np.bool_):
        return bool(value)

    raise TypeError(
        f"無法儲存的資料類型："
        f"{type(value).__name__}"
    )


def clean_json(value):
    """避免 JSON 出現 NaN 或 Infinity。"""

    def sanitize(obj):

        if isinstance(obj, dict):
            return {
                str(k): sanitize(v)
                for k, v in obj.items()
            }

        if isinstance(obj, (list, tuple)):
            return [
                sanitize(v)
                for v in obj
            ]

        if isinstance(obj, (float, np.floating)):
            number = float(obj)

            if math.isfinite(number):
                return number

            return None

        if isinstance(
            obj,
            (datetime, date, pd.Timestamp),
        ):
            return obj.isoformat()

        if isinstance(obj, np.integer):
            return int(obj)

        if isinstance(obj, np.bool_):
            return bool(obj)

        return obj

    return json.dumps(
        sanitize(value),
        ensure_ascii=False,
        allow_nan=False,
        default=json_default,
    )


def init_database(db_path=DB_PATH):
    """建立獨立於 Telegram 的網頁資料表。"""

    with closing(
        sqlite3.connect(str(db_path))
    ) as conn:

        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS web_state (
                    id INTEGER PRIMARY KEY
                        CHECK (id = 1),
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                        DEFAULT CURRENT_TIMESTAMP
                )
                """
            )


def save_web_state(
    confirmed_strategy,
    previous_confirmed_strategy,
    last_result,
    db_path=DB_PATH,
):
    """儲存網頁版的已確認策略及回測資料。"""

    if (
        confirmed_strategy is not None
        and not isinstance(
            confirmed_strategy, dict
        )
    ):
        raise ValueError(
            "已確認策略格式不正確"
        )

    if (
        previous_confirmed_strategy is not None
        and not isinstance(
            previous_confirmed_strategy, dict
        )
    ):
        raise ValueError(
            "上一版策略格式不正確"
        )

    stored_result = None

    if last_result is not None:

        df = last_result.get("df")

        if not isinstance(
            df,
            pd.DataFrame,
        ):
            raise ValueError(
                "回測結果缺少 DataFrame"
            )

        if not isinstance(
            last_result.get("strategy"),
            dict,
        ):
            raise ValueError(
                "回測結果缺少策略設定"
            )

        stored_result = {
            "strategy": last_result["strategy"],
            "trades": last_result["trades"],
            "stats": last_result["stats"],
            "df_json": df.to_json(
                orient="records",
                date_format="iso",
                date_unit="ms",
            ),
        }

    payload = {
        "schema_version": 1,
        "confirmed_strategy": (
            confirmed_strategy
        ),
        "previous_confirmed_strategy": (
            previous_confirmed_strategy
        ),
        "last_result": stored_result,
    }

    encoded = clean_json(payload)

    init_database(db_path)

    # closing 確保離開區塊時關閉 SQLite 連線
    # conn 交易區塊確保成功提交、失敗回滾
    with closing(
        sqlite3.connect(str(db_path))
    ) as conn:

        with conn:
            conn.execute(
                """
                INSERT INTO web_state (
                    id,
                    payload
                )
                VALUES (1, ?)

                ON CONFLICT(id)
                DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (encoded,),
            )


def load_web_state(db_path=DB_PATH):
    """恢復已確認策略與最近一次回測資料。"""

    if not Path(db_path).exists():
        return None

    init_database(db_path)

    with closing(
        sqlite3.connect(str(db_path))
    ) as conn:

        row = conn.execute(
            """
            SELECT payload
            FROM web_state
            WHERE id = 1
            """
        ).fetchone()

    if row is None:
        return None

    payload = json.loads(row[0])

    if payload.get("schema_version") != 1:
        raise ValueError(
            "不支援的網頁資料庫版本"
        )

    result = payload.get("last_result")

    if result is not None:

        df = pd.read_json(
            StringIO(result["df_json"]),
            orient="records",
        )

        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(
                df["timestamp"],
                utc=True,
                errors="raise",
            )

        result = {
            "strategy": result["strategy"],
            "df": df,
            "trades": result["trades"],
            "stats": result["stats"],
        }

    return {
        "confirmed_strategy": payload.get(
            "confirmed_strategy"
        ),
        "previous_confirmed_strategy": payload.get(
            "previous_confirmed_strategy"
        ),
        "last_result": result,
    }
