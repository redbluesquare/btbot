# uscgc gold trader

import time
from datetime import datetime, time as dt_time, timezone
import pandas as pd
import numpy as np
from trading_ig import IGService
import os
from dotenv import load_dotenv
import models.user as user
import models.indicators as indicators
import models.prices as prices
import models.setup as setup
import models.trade_executor as trade_executor
import models.trades as trades

load_dotenv()

# Constants
EPIC = 'CS.D.USCGC.TODAY.IP'
BUY_SIZE = '0.05'
SELL_SIZE = '0.05'
FIXED_STOP = 12  # points
FIXED_TARGET = 18  # points
MAX_BARS_IN_TRADE = 20

# Time windows for trading (UTC)
TRADING_WINDOWS = [
    (dt_time(13,30), dt_time(16,0)),  # US open
    (dt_time(18,0), dt_time(20,0))    # Post-settlement drift
]

usr = user.User()
price = prices.Prices()
ind = indicators.Indicators()
te = trade_executor.TradeExecutor()
trades_model = trades.Trades()

# DB setup
setup.create_trades_table()
setup.create_trading_check_table()
setup.update_trades_table()


def is_within_trading_windows(ts):
    """Check if given UTC datetime is within allowed trading windows."""
    t = ts.time()
    return any(start <= t < end for start, end in TRADING_WINDOWS)


def last_trade_time(epic: str):
    import sqlite3
    db = sqlite3.connect('streamed_prices.db')
    c = db.cursor()
    c.execute("""
        SELECT trade_date
        FROM trade_data
        WHERE epic = ?
        ORDER BY datetime(trade_date) DESC
        LIMIT 1
    """, (epic,))
    row = c.fetchone()
    db.close()

    if not row:
        return None

    return datetime.fromisoformat(row[0]).replace(tzinfo=timezone.utc)


def candle_has_long_lower_wick(row):
    """Detect if candle has a long lower wick relative to body."""
    body = abs(row['close'] - row['open'])
    lower_wick = row['open'] - row['low'] if row['close'] >= row['open'] else row['close'] - row['low']
    return lower_wick > 1.5 * body and lower_wick > 0.5


def candle_has_long_upper_wick(row):
    """Detect if candle has a long upper wick relative to body."""
    body = abs(row['close'] - row['open'])
    upper_wick = row['high'] - row['close'] if row['close'] >= row['open'] else row['high'] - row['open']
    return upper_wick > 1.5 * body and upper_wick > 0.5


def process_epic(ig_service, positions):
    open_pos = None
    for p in positions:
        if p['epic'] == EPIC:
            open_pos = p
            break

    now_utc = datetime.now(timezone.utc)
    lt = last_trade_time(EPIC)

    df = price.load_ohlc(EPIC, '5MINUTE')
    df = df.sort_values(by='date', ascending=True)

    # Calculate indicators
    df = ind.calculate_rsi(df, 14)
    df = ind.add_bollinger_bands(df, 20, 2)  # Assuming this method exists

    last = df.iloc[-1]

    in_window = is_within_trading_windows(last['date'])

    atr = last['atr'] if 'atr' in last else None
    if atr is not None and (atr > 15 or atr < 3):
        # Skip trading if volatility too high or too low
        return

    buy_signal = (
        last['rsi'] < 30 and
        last['close'] < last['bb_lower'] and
        candle_has_long_lower_wick(last)
    )

    sell_signal = (
        last['rsi'] > 70 and
        last['close'] > last['bb_upper'] and
        candle_has_long_upper_wick(last)
    )

    if open_pos is None:
        can_trade = lt is None or (now_utc - lt).total_seconds() > 30 * 60  # 30 min cooldown

        if in_window and can_trade and (buy_signal or sell_signal):
            direction = 'BUY' if buy_signal else 'SELL'
            size = BUY_SIZE if direction == 'BUY' else SELL_SIZE

            trade = te.open_trade(
                ig_service,
                EPIC,
                expiry='DFB',
                direction=direction,
                size=size,
                order_type='MARKET',
                currency_code='GBP',
                guaranteed_stop=False,
                force_open=True,
                stop_distance=FIXED_STOP
            )

            import sqlite3
            db = sqlite3.connect('streamed_prices.db')
            c = db.cursor()
            c.execute("""
                INSERT INTO trade_data
                (epic, trade_date, trade_type, dealId, dealStatus, price, stake, rsi, pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade['epic'], trade['date'], trade['direction'], trade['dealId'],
                trade['dealStatus'], trade['level'], trade['size'],
                last['rsi'], 0
            ))
            db.commit()
            db.close()

        return

    # Manage open position
    df_recent = price.load_ohlc(EPIC, '5MINUTE', records=100)
    df_recent = df_recent.sort_values(by='date', ascending=True)

    entry = open_pos['level']
    stop = open_pos['stopLevel']
    current = df_recent.iloc[-1]['close']

    bars_held = open_pos.get('bars_held', 0)  # You may need to track this externally

    # Move stop to break-even after +8 points
    if open_pos['direction'] == 'BUY':
        if current - entry >= 8 and stop < entry:
            new_stop = entry
            ig_service.update_open_position(
                limit_level=None,
                stop_level=new_stop,
                deal_id=open_pos['dealId']
            )

    elif open_pos['direction'] == 'SELL':
        if entry - current >= 8 and stop > entry:
            new_stop = entry
            ig_service.update_open_position(
                limit_level=None,
                stop_level=new_stop,
                deal_id=open_pos['dealId']
            )

    # Hard exit after max bars
    if bars_held >= MAX_BARS_IN_TRADE:
        te.close_trade(ig_service, open_pos['dealId'])


def main_loop():
    ig_service = usr.login_ig(
        IGService,
        os.getenv('IDENTIFIER'),
        os.getenv('PASSWORD'),
        os.getenv('API_KEY'),
        acc_type=os.getenv('ACC_TYPE')
    )
    ig_service.create_session()

    while True:
        try:
            positions = ig_service.fetch_open_positions()
            pos_list = positions.to_dict(orient='records')

            process_epic(ig_service, pos_list)

            time.sleep(30)

        except Exception as e:
            print(f"[GOLD TRADER] Error: {e}")
            time.sleep(10)


if __name__ == '__main__':
    main_loop()