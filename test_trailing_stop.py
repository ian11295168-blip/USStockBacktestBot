
from trailing_stop import TrailingStop


# 測試一：股價上漲後，追蹤停損價提高
stop = TrailingStop(
    entry_price=100,
    percent=8
)

assert round(stop.stop_price, 2) == 92

result = stop.check_day(
    day_open=100,
    day_high=110,
    day_low=99
)

assert result["triggered"] is False
assert round(stop.stop_price, 2) == 101.20

print("✅ 股價上漲，追蹤停損價提高")


# 測試二：最高價沒有創新高，停損價不下降
result = stop.check_day(
    day_open=108,
    day_high=109,
    day_low=105
)

assert result["triggered"] is False
assert round(stop.stop_price, 2) == 101.20

print("✅ 股價回落，停損價不降低")


# 測試三：盤中跌破追蹤停損價
result = stop.check_day(
    day_open=104,
    day_high=105,
    day_low=100
)

assert result["triggered"] is True
assert result["reason"] == "追蹤停損"
assert round(result["price"], 2) == 101.20

print("✅ 盤中觸及追蹤停損，正確出場")


# 測試四：跳空下跌，按開盤價出場
stop2 = TrailingStop(
    entry_price=100,
    percent=8
)

stop2.check_day(
    day_open=100,
    day_high=120,
    day_low=99
)

result = stop2.check_day(
    day_open=105,
    day_high=107,
    day_low=103
)

assert result["triggered"] is True
assert result["reason"] == "跳空追蹤停損"
assert result["price"] == 105

print("✅ 跳空跌破停損價，使用開盤價")


# 測試五：不合法的百分比應拒絕
try:
    TrailingStop(
        entry_price=100,
        percent=-8
    )
except ValueError:
    print("✅ 不合法追蹤停損參數已拒絕")
else:
    raise AssertionError(
        "未拒絕不合法的追蹤停損參數"
    )


print("\n✅ 追蹤停損基礎測試全部通過")
