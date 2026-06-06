# ftse_trader.py
from trading_ig import IGService
import sqlite3
from dotenv import load_dotenv
import time
import os
from datetime import datetime, timezone, time as dt_time

# Local modules
import models.user as user
import models.indicators as indicators
import models.prices as prices
import models.setup as setup
import models.trade_executor as trade_executor
import models.trades as trades
import app

# Load environment
load_dotenv()
usr = user.User()
price = prices.Prices()
ind = indicators.Indicators()
trdes = trades.Trades()
te = trade_executor.TradeExecutor()

# Ensure DB tables exist
setup.create_trades_table()
setup.create_trading_check_table()
setup.update_trades_table()

API_KEY = os.getenv('API_KEY')
username = os.getenv('IDENTIFIER')
user_pw = os.getenv('PASSWORD')
acc_type = os.getenv('ACC_TYPE')

# FTSE-specific configuration
EPIC = 'IX.D.DOW.DAILY.IP'
BUY_SIZE = '0.01'
SELL_SIZE = '0.01'
MAX_STOP = 40
COOLDOWN_MINUTES = 30
TRADING_OPEN = 13
TRADING_CLOSE = 18


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def last_trade_time(epic):
    """Return last trade time for this epic as timezone-aware UTC."""
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

    # Ensure timezone-aware
    return datetime.fromisoformat(row[0]).replace(tzinfo=timezone.utc)


# ---------------------------------------------------------
# Main Trading Logic
# ---------------------------------------------------------

def trade_epic():
    ig_service = usr.login_ig(IGService, username, user_pw, API_KEY, acc_type=acc_type)
    ig_service.create_session()

    # Fetch open positions
    positions = ig_service.fetch_open_positions()
    pos_list = positions.to_dict(orient='records')

    open_pos = next((p for p in pos_list if p['epic'] == EPIC), None)

    now_utc = datetime.now(timezone.utc)
    lt = last_trade_time(EPIC)

    # Load indicators
    df = price.load_ohlc(EPIC, '5MINUTE')
    df = df.sort_values(by='date')
    df = ind.calculate_macd(df, 8, 21, 5)
    df = ind.calculate_rsi(df, 21)
    df = ind.calculate_cci(df, 90)
    df['macd_slope'] = df['macd'].diff()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    df = ind.add_atr(df, 14)

    last = df.iloc[-1]

    # Trading hours
    in_hours = ind.is_within_trading_hours(
        last['date'], TRADING_OPEN, TRADING_CLOSE
    )

    candle_range = last['high'] - last['low']
    if candle_range < 1.2 * last['atr']:
        return  # only trade strong momentum candles


    # Signals
    buy_signal = (
        last['bullish_crossover'] and
        last['macd_slope'] > 0 and
        last['close'] > last['ema20'] and
        last['rsi'] > 60
    )

    sell_signal = (
        last['bearish_crossover'] and
        last['macd_slope'] < 0 and
        last['close'] < last['ema20'] and
        last['rsi'] < 40
    )

    # ---------------------------------------------------------
    # ENTRY LOGIC
    # ---------------------------------------------------------
    if open_pos is None:

        # Cooldown check
        if lt is None or (now_utc - lt).total_seconds() > COOLDOWN_MINUTES * 60:

            if in_hours and buy_signal:
                atr = last['atr']
                stop_distance = min(MAX_STOP, 4.0 * atr)

                trade = te.open_trade(
                    ig_service, EPIC, expiry='DFB', direction='BUY',
                    size=BUY_SIZE, order_type='MARKET',
                    currency_code='GBP', guaranteed_stop=False,
                    force_open=True, stop_distance=stop_distance
                )

                db = sqlite3.connect('streamed_prices.db')
                c = db.cursor()
                c.execute("""
                    INSERT INTO trade_data
                    (epic, trade_date, trade_type, dealId, dealStatus, price, stake, macd, rsi, pnl)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trade['epic'], trade['date'], trade['direction'], trade['dealId'],
                    trade['dealStatus'], trade['level'], trade['size'],
                    last['macd'], last['rsi'], 0
                ))
                db.commit()
                db.close()

            elif in_hours and sell_signal:
                atr = last['atr']
                stop_distance = min(MAX_STOP, 2.0 * atr)

                trade = te.open_trade(
                    ig_service, EPIC, expiry='DFB', direction='SELL',
                    size=SELL_SIZE, order_type='MARKET',
                    currency_code='GBP', guaranteed_stop=False,
                    force_open=True, stop_distance=stop_distance
                )

                db = sqlite3.connect('streamed_prices.db')
                c = db.cursor()
                c.execute("""
                    INSERT INTO trade_data
                    (epic, trade_date, trade_type, dealId, dealStatus, price, stake, macd, rsi, pnl)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trade['epic'], trade['date'], trade['direction'], trade['dealId'],
                    trade['dealStatus'], trade['level'], trade['size'],
                    last['macd'], last['rsi'], 0
                ))
                db.commit()
                db.close()

    # ---------------------------------------------------------
    # EXIT / STOP MANAGEMENT
    # ---------------------------------------------------------
    else:
        df_recent = price.load_ohlc(EPIC, '5MINUTE', records=100)
        df_recent = df_recent.sort_values(by='date')
        df_recent = ind.add_atr(df_recent, 14)

        last_r = df_recent.iloc[-1]
        atr = last_r['atr']

        entry = open_pos['level']
        stop = open_pos['stopLevel']
        current = last_r['close']

        bars = len(df_recent)
        if bars > 20:
            if open_pos['direction'] == 'BUY' and stop < entry:
                new_stop = entry
            elif open_pos['direction'] == 'SELL' and stop > entry:
                new_stop = entry

        # BUY POSITION MANAGEMENT
        if open_pos['direction'] == 'BUY':
            risk = abs(entry - stop)
            if risk < 1e-6:
                risk = 2.0 * atr

            r = (current - entry) / risk

            if r >= 1.0 and stop < entry:
                new_stop = entry * 1.0001
            elif r >= 2.0:
                new_stop = current - 1.5 * atr
            else:
                new_stop = stop

            if new_stop > stop:
                ig_service.update_open_position(
                    limit_level=None, stop_level=new_stop, deal_id=open_pos['dealId']
                )

        # SELL POSITION MANAGEMENT
        if open_pos['direction'] == 'SELL':
            risk = abs(entry - stop)
            if risk < 1e-6:
                risk = 2.0 * atr

            r = (entry - current) / risk

            if r >= 1.0 and stop > entry:
                new_stop = entry
            elif r >= 2.0:
                new_stop = current + 1.5 * atr
            else:
                new_stop = stop

            if new_stop < stop:
                ig_service.update_open_position(
                    limit_level=None, stop_level=new_stop, deal_id=open_pos['dealId']
                )

    # ---------------------------------------------------------
    # NIGHTLY TASKS
    # ---------------------------------------------------------
    now = datetime.now().time()

    if dt_time(21, 1) <= now < dt_time(21, 3):
        app.main()
        time.sleep(180)

    if dt_time(21, 12) <= now < dt_time(21, 14):
        db = sqlite3.connect('streamed_prices.db')
        c = db.cursor()
        trdes.save_ig_trades_to_db(db, c, days=3)
        db.close()
        time.sleep(60)


# ---------------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------------

if __name__ == "__main__":
    while True:
        trade_epic()
        time.sleep(30)