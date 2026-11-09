
import math


class TrailingStop:
    """多頭持倉的追蹤停損計算器。"""

    def __init__(self, entry_price, percent):
        if (
            type(entry_price) not in (int, float)
            or not math.isfinite(entry_price)
            or entry_price <= 0
        ):
            raise ValueError("買進價格必須大於0")

        if (
            type(percent) not in (int, float)
            or not math.isfinite(percent)
            or not 0 < percent < 100
        ):
            raise ValueError(
                "追蹤停損百分比必須介於0至100之間"
            )

        self.percent = percent
        self.highest_price = entry_price
        self.active = True

    @property
    def stop_price(self):
        return self.highest_price * (
            1 - self.percent / 100
        )

    def check_day(self, day_open, day_high, day_low):
        """
        使用日K資料檢查是否觸及追蹤停損。

        當日停損價只根據前一交易日結束前
        已知的最高價決定。

        若未出場，才更新當日最高價，
        供下一交易日使用。
        """

        if not self.active:
            raise ValueError("這筆持倉已經出場")

        prices = (day_open, day_high, day_low)

        if any(
            type(x) not in (int, float)
            or not math.isfinite(x)
            or x <= 0
            for x in prices
        ):
            raise ValueError("價格資料不合法")

        if not (
            day_low <= day_open <= day_high
        ):
            raise ValueError("OHLC價格範圍不合理")

        stop = self.stop_price

        # 開盤已跌破停損價，使用開盤價成交
        if day_open <= stop:
            self.active = False
            return {
                "triggered": True,
                "price": day_open,
                "reason": "跳空追蹤停損"
            }

        # 當日最低價觸及停損
        if day_low <= stop:
            self.active = False
            return {
                "triggered": True,
                "price": stop,
                "reason": "追蹤停損"
            }

        # 當日未出場，收盤後更新最高價
        self.highest_price = max(
            self.highest_price,
            day_high
        )

        return {
            "triggered": False,
            "price": None,
            "reason": None
        }
