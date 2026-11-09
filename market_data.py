
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed, Adjustment

load_dotenv()

client = StockHistoricalDataClient(
    os.getenv("ALPACA_API_KEY"),
    os.getenv("ALPACA_SECRET_KEY")
)


def get_stock_data(symbol, years=5):
    symbol = symbol.strip().upper()

    if not 1 <= years <= 10:
        raise ValueError("目前支援回測1至10年")

    end_date = datetime.now(timezone.utc)

    # 額外取得300天，用來預熱技術指標
    start_date = end_date - timedelta(
        days=365 * years + 300
    )

    request = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Day,
        start=start_date,
        end=end_date,
        feed=DataFeed.IEX,
        adjustment=Adjustment.SPLIT
    )

    bars = client.get_stock_bars(request)
    df = bars.df

    if df.empty:
        raise ValueError(f"找不到 {symbol} 的歷史資料")

    return df.sort_index()


if __name__ == "__main__":
    data = get_stock_data("AAPL", 5)
    print(data.tail())
