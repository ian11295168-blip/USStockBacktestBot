
"""v1.8 — Supabase 唯讀模組測試。"""

from supabase_reader import (
    get_cloud_counts,
    get_cloud_telegram_states,
    get_cloud_web_state,
)


def main():
    print("US Stock Strategy Lab v1.8")
    print("Supabase 雲端資料讀取測試")
    print("=" * 42)

    try:
        counts = get_cloud_counts()

        print("📊 雲端資料筆數")

        for name, count in counts.items():
            print(f"✅ {name}: {count} 筆")

        states = get_cloud_telegram_states()

        if len(states) != counts[
            "telegram_strategy_state"
        ]:
            raise RuntimeError(
                "Telegram 策略筆數不一致"
            )

        print("✅ Telegram 策略狀態讀取成功")

        for state in states:
            if not isinstance(
                state.get("last_strategy"),
                (dict, type(None)),
            ):
                raise RuntimeError(
                    "Telegram 策略 JSONB 格式錯誤"
                )

        print("✅ Telegram JSONB 格式正常")

        web = get_cloud_web_state()

        if web is None:
            if counts["web_state"] != 0:
                raise RuntimeError(
                    "找不到預期的網頁狀態"
                )
            print("ℹ️ 雲端目前沒有網頁狀態")

        else:
            if not isinstance(
                web.get("payload"), dict
            ):
                raise RuntimeError(
                    "網頁 JSONB 格式錯誤"
                )

            print("✅ 網頁狀態讀取成功")
            print("✅ 網頁 JSONB 格式正常")

        print()
        print("🎉 v1.8 雲端唯讀測試通過！")
        print("沒有修改任何雲端資料。")

    except Exception as exc:
        print()
        print("❌ 測試失敗")
        print("錯誤類型：", type(exc).__name__)


if __name__ == "__main__":
    main()
