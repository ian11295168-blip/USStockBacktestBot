"""Telegram Bot + safe Railway bootstrap (v5.3)."""
import hashlib
import json
import logging
import os
import threading

from railway_telegram_bootstrap import ensure_ready
from telegram_cloud_sync import read_local, synchronize, ConflictError

CHECK_INTERVAL = 15
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("telegram_cloud_watcher")


def snapshot_hash():
    states, backtests = read_local()
    content = json.dumps({
        "states": sorted(states, key=lambda r: str(r["user_id"])),
        "backtests": sorted(backtests, key=lambda r: int(r["id"])),
    }, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
       allow_nan=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def sync_worker(stop_event):
    previous = None
    last_error = None
    logger.info("Supabase 同步監控已啟動")
    while not stop_event.is_set():
        try:
            current = snapshot_hash()
            if current != previous:
                synchronize()
                if snapshot_hash() == current:
                    previous = current
                    logger.info("Telegram / Supabase 同步檢查完成")
                else:
                    logger.info("同步期間有新資料，下輪再檢查")
            last_error = None
        except ConflictError:
            if last_error != "conflict":
                logger.error("雲端版本衝突，本輪沒有覆蓋雲端")
            last_error = "conflict"
        except Exception as exc:
            kind = type(exc).__name__
            if kind != last_error:
                logger.error("同步失敗：%s，下輪重試", kind)
            last_error = kind
        stop_event.wait(CHECK_INTERVAL)
    logger.info("同步監控停止")


def main():
    # 啟動 Bot 之前必須完成持久化/雲端快照安全檢查。
    ensure_ready()
    stop_event = threading.Event()
    worker = threading.Thread(target=sync_worker, args=(stop_event,),
        name="SupabaseSyncWorker", daemon=True)
    worker.start()
    try:
        from bot_confirm import main as bot_main
        logger.info("啟動 Telegram Bot")
        bot_main()
    except KeyboardInterrupt:
        logger.info("收到停止指令")
    finally:
        stop_event.set()
        worker.join(timeout=5)

if __name__ == "__main__":
    main()
