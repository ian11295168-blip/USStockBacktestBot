
"""US Stock Strategy Lab v4.2
網頁本機 / 雲端雙模式儲存介面。

本機：
    load_state("local")
    save_state(..., mode="local")

雲端：
    snapshot = load_state("cloud")
    save_state(
        ...,
        mode="cloud",
        baseline=snapshot["baseline"],
    )

安全規則：
- 雲端保存必須提供先前讀取的 baseline。
- 不允許在保存前重新讀取 baseline 來跳過衝突。
- 雲端模式完全不寫入 SQLite。
- 本機模式只寫入 SQLite；現有的雲端同步
  仍由原本 web_app.py 負責，避免重複同步。
"""

import json
import os
from copy import deepcopy

import pandas as pd

from web_storage import (
    clean_json,
    load_web_state,
    save_web_state,
)

from cloud_web_storage import (
    load_cloud_web_state,
    save_cloud_web_state,
    CloudConflictError,
)

from cloud_dataframe_codec import (
    restore_cloud_web_state,
)


class StorageModeError(ValueError):
    pass


def get_storage_mode(mode=None):
    """辨識 local / cloud 模式。"""

    value = (
        mode
        if mode is not None
        else os.getenv(
            "STOCK_STORAGE_MODE",
            "local",
        )
    )

    value = str(value).strip().lower()

    if value not in ("local", "cloud"):
        raise StorageModeError(
            "STOCK_STORAGE_MODE 只能是 local 或 cloud"
        )

    return value


def build_payload(
    confirmed_strategy,
    previous_confirmed_strategy,
    last_result,
):
    """產生與 web_storage.py 相容的 schema v1。"""

    for name, value in (
        ("confirmed_strategy", confirmed_strategy),
        (
            "previous_confirmed_strategy",
            previous_confirmed_strategy,
        ),
    ):
        if value is not None and not isinstance(
            value, dict
        ):
            raise ValueError(
                name + " 必須是策略字典或 None"
            )

    stored_result = None

    if last_result is not None:
        if not isinstance(last_result, dict):
            raise ValueError(
                "last_result 格式不正確"
            )

        df = last_result.get("df")

        if not isinstance(df, pd.DataFrame):
            raise ValueError(
                "回測結果缺少 pandas DataFrame"
            )

        strategy = last_result.get("strategy")
        trades = last_result.get("trades")
        stats = last_result.get("stats")

        if not isinstance(strategy, dict):
            raise ValueError(
                "回測結果缺少策略字典"
            )

        if not isinstance(trades, list):
            raise ValueError(
                "回測交易紀錄必須是 list"
            )

        if not isinstance(stats, dict):
            raise ValueError(
                "回測統計必須是 dict"
            )

        stored_result = {
            "strategy": deepcopy(strategy),
            "trades": deepcopy(trades),
            "stats": deepcopy(stats),
            "df_json": df.to_json(
                orient="records",
                date_format="iso",
                date_unit="ms",
            ),
        }

    payload = {
        "schema_version": 1,
        "confirmed_strategy": deepcopy(
            confirmed_strategy
        ),
        "previous_confirmed_strategy": deepcopy(
            previous_confirmed_strategy
        ),
        "last_result": stored_result,
    }

    # 使用既有 web_storage 的清理規則：
    # 處理 datetime、numpy、NaN 等資料型態。
    return json.loads(clean_json(payload))


def load_state(mode=None):
    """讀取指定模式的策略與回測。

    回傳：
    {
        "mode": "local" 或 "cloud",
        "state": {
            "confirmed_strategy": ...,
            "previous_confirmed_strategy": ...,
            "last_result": ...
        },
        "baseline": 雲端原始 payload 或 None
    }
    """

    selected = get_storage_mode(mode)

    if selected == "local":
        return {
            "mode": "local",
            "state": load_web_state(),
            "baseline": None,
        }

    record = load_cloud_web_state()

    if record is None:
        raise RuntimeError(
            "Supabase 尚無 web_state id=1；"
            "為避免覆蓋，不能自動建立資料"
        )

    state = restore_cloud_web_state(record)

    return {
        "mode": "cloud",
        "state": state,
        "baseline": deepcopy(record["payload"]),
    }


def save_state(
    confirmed_strategy,
    previous_confirmed_strategy,
    last_result,
    *,
    mode=None,
    baseline=None,
    dry_run=False,
):
    """依照指定模式保存。

    雲端：
      必須使用原先讀取的 baseline。
      回傳新的 baseline，供下一次更新使用。

    本機：
      使用已通過測試的 save_web_state。
    """

    selected = get_storage_mode(mode)

    if selected == "local":
        if dry_run:
            raise StorageModeError(
                "本機模式不支援 dry_run"
            )

        save_web_state(
            confirmed_strategy,
            previous_confirmed_strategy,
            last_result,
        )

        return {
            "mode": "local",
            "status": "saved",
            "message": "SQLite 保存成功",
            "baseline": None,
        }

    if not isinstance(baseline, dict):
        raise StorageModeError(
            "雲端保存需要先前載入的 baseline"
        )

    payload = build_payload(
        confirmed_strategy,
        previous_confirmed_strategy,
        last_result,
    )

    result = save_cloud_web_state(
        payload=payload,
        expected_payload=deepcopy(baseline),
        dry_run=dry_run,
    )

    return {
        "mode": "cloud",
        "status": result["status"],
        "message": result["message"],
        "baseline": (
            deepcopy(payload)
            if result["status"] in ("saved", "unchanged")
            else deepcopy(baseline)
        ),
    }
