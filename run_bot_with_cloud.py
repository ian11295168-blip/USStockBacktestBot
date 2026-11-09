
"""US Stock Strategy Lab v2.6
Telegram Bot + Supabase 自動同步啟動器。

啟動：
    python run_bot_with_cloud.py

功能：
- 保留 bot_confirm.py 原有功能
- 每15秒檢查 SQLite 資料變化
- 自動同步至 Supabase
- 同步失敗後自動重試
- 遇到雲端版本衝突時禁止覆蓋
- 不修改本機 SQLite

注意：
- 同一時間只啟動一個 Telegram Bot
- 仍需讓這支程式持續運行
- 目前是本機單人版本
"""

import hashlib
import json
import logging
import threading
from datetime import datetime

from telegram_cloud_sync import (
    read_local,
    synchronize,
    ConflictError,
)


CHECK_INTERVAL = 15

logger = logging.getLogger("telegram_cloud_watcher")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def snapshot_hash():
    """計算 Telegram SQLite 已保存內容的指紋。"""

    states, backtests = read_local()

    content = json.dumps(
        {
            "states": sorted(
                states,
                key=lambda row: str(row["user_id"]),
            ),
            "backtests": sorted(
                backtests,
                key=lambda row: int(row["id"]),
            ),
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )

    return hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()


def sync_worker(stop_event):
    """背景同步監控，與 Telegram 主程式分開。"""

    last_successful_snapshot = None
    last_error_type = None

    logger.info("Supabase 自動同步監控已啟動")

    while not stop_event.is_set():

        try:
            current = snapshot_hash()

            if current != last_successful_snapshot:

                logger.info(
                    "偵測到 Telegram 資料需要檢查同步"
                )

                synchronize()

                # 同步成功後重新讀取，
                # 若同步期間有新資料，下一輪會再處理。
                latest = snapshot_hash()

                # 只有同步前後快照相同，
                # 才視為本輪資料已完成同步。
                if latest == current:
                    last_successful_snapshot = current

                    logger.info(
                        "Telegram / Supabase 同步檢查完成"
                    )

                else:
                    logger.info(
                        "同步期間偵測到新資料，"
                        "下一輪繼續同步"
                    )

                last_error_type = None

        except ConflictError:
            # 遇到版本衝突，只報錯，不強行覆蓋。
            if last_error_type != "conflict":
                logger.error(
                    "雲端版本衝突："
                    "已停止本輪更新，"
                    "請手動檢查資料差異"
                )

            last_error_type = "conflict"

        except Exception as exc:
            error_type = type(exc).__name__

            if last_error_type != error_type:
                logger.error(
                    "Supabase 同步失敗：%s。"
                    "本機資料仍保留，稍後重試。",
                    error_type,
                )

            last_error_type = error_type

        stop_event.wait(CHECK_INTERVAL)

    logger.info("Supabase 自動同步監控已停止")


def main():
    print("=" * 52)
    print("US Stock Strategy Lab v2.6")
    print("Telegram Bot + Supabase 自動同步")
    print("=" * 52)
    print("同步檢查間隔：15秒")
    print("本機 SQLite 優先保存")
    print("雲端同步失敗不會取消 Telegram 回測")
    print()

    stop_event = threading.Event()

    worker = threading.Thread(
        target=sync_worker,
        args=(stop_event,),
        name="SupabaseSyncWorker",
        daemon=True,
    )

    worker.start()

    try:
        # Telegram Bot 必須在主執行緒執行，
        # 避免 asyncio 事件迴圈與訊號處理問題。
        from bot_confirm import main as bot_main

        print("正在啟動 Telegram Bot...")
        bot_main()

    except KeyboardInterrupt:
        print("\n收到停止指令")

    finally:
        stop_event.set()
        worker.join(timeout=5)
        print("Telegram 自動同步啟動器已結束")


if __name__ == "__main__":
    main()
