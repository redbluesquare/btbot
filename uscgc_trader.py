# ftse_service.py

from trading_ig import IGService
import sqlite3
from dotenv import load_dotenv
import time
import os
from datetime import datetime, timezone, time as dt_time

import models.user as user
import models.indicators as indicators
import models.prices as prices
import models.setup as setup
import models.trade_executor as trade_executor
import models.trades as trades
import app

load_dotenv()

# --- Constants specific to this service (FTSE) ---

EPIC = 'CS.D.USCGC.TODAY.IP'
BUY_SIZE = '0.05'
SELL_SIZE = '0.05'
MAX_STOP = 10          # max stop distance in points
COOLDOWN_MINUTES = 30  # min time between trades on this epic

TRADING_HOURS = {
    'open': 1,   # hour (UTC) market considered open
    'close': 21  # hour (UTC) market considered closed
}

API_KEY = os.getenv('API_KEY')
USERNAME = os.getenv('IDENTIFIER')
USER_PW = os.getenv('PASSWORD')
ACC_TYPE = os.getenv('ACC_TYPE')

# --- Model instances ---

usr = user.User()
price = prices.Prices()
ind = indicators.Indicators()
trdes = trades.Trades()
te = trade_executor.TradeExecutor()

# --- DB setup (run once at startup) ---

setup.create_trades_table()
setup.create_trading_check_table()
setup.update_trades_table()


def last_trade_time(epic: str):
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

    # Parse and force UTC timezone
    return datetime.fromisoformat(row[0]).replace(tzinfo=timezone.utc)


def within_trading_hours(ts) -> bool:
    """
    ts is assumed to be timezone-aware (UTC) or convertible.
    """
    # If your df['date'] is naive but UTC, you can treat it as UTC directly.
    hour = ts.hour
    return TRADING_HOURS['open'] <= hour < TRADING_HOURS['close']


def process_epic(ig_service, positions):
    """
    Core logic for FTSE epic only.
    """
    # Check if there is an open position for this epic
    open_pos = None
    for p in positions:
        if p['epic'] == EPIC:
            open_pos = p
            break

    now_utc = datetime.now(timezone.utc)
    lt = last_trade_time(EPIC)

    # --- Load and prepare indicator data ---

    df = price.load_ohlc(EPIC, '5MINUTE')
    df = df.sort_values(by='date', ascending=True)
    df = ind.calculate_macd(df, 5, 35, 5)
    df = ind.calculate_rsi(df, 21)
    df = ind.calculate_cci(df, 90)
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df = ind.add_atr(df, 14)

    last = df.iloc[-1]

    in_hours = within_trading_hours(last['date'])

    buy_signal = (
        last['bullish_crossover'] and
        (last['rsi_cross_above_50'] or last['rsi_bullish']) and
        last['close'] > last['ema50'] and
        last['rsi'] < 65
    )

    sell_signal = (
        last['bearish_crossover'] and
        last['rsi_bearish'] and
        last['close'] < last['ema50'] and
        last['rsi'] > 35
    )

    # --- No open position: look for entries ---

    if open_pos is None:
        can_trade = (
            lt is None or (now_utc - lt).total_seconds() > COOLDOWN_MINUTES * 60
        )

        if in_hours and can_trade and (buy_signal or sell_signal):
            atr = last['atr']
            stop_distance = min(MAX_STOP, 2.0 * atr)

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
                stop_distance=stop_distance
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

        return  # nothing else to do if no open position

    # --- Open position exists: manage it ---

    df_recent = price.load_ohlc(EPIC, '5MINUTE', records=100)
    df_recent = df_recent.sort_values(by='date', ascending=True)
    df_recent = ind.add_atr(df_recent, 14)
    last_r = df_recent.iloc[-1]
    atr = last_r['atr']

    entry = open_pos['level']
    stop = open_pos['stopLevel']
    current = last_r['close']

    # Rebuild risk if stop is missing or equal to entry
    risk = abs(entry - stop)
    if risk < 1e-6:
        risk = 2.0 * atr

    if open_pos['direction'] == 'BUY':
        r = (current - entry) / risk

        if r >= 1.0 and stop < entry:
            new_stop = entry * 1.0001
        elif r >= 2.0:
            new_stop = current - 1.5 * atr
        else:
            new_stop = stop

        if new_stop > stop:
            ig_service.update_open_position(
                limit_level=None,
                stop_level=new_stop,
                deal_id=open_pos['dealId']
            )

    elif open_pos['direction'] == 'SELL':
        r = (entry - current) / risk
        print(open_pos['epic'], entry, current, stop, r)

        if r >= 1.0 and stop > entry:
            new_stop = entry
        elif r >= 2.0:
            new_stop = current + 1.5 * atr
        else:
            new_stop = stop

        if new_stop < stop:
            ig_service.update_open_position(
                limit_level=None,
                stop_level=new_stop,
                deal_id=open_pos['dealId']
            )


def main_loop():
    ig_service = usr.login_ig(
        IGService,
        USERNAME,
        USER_PW,
        API_KEY,
        acc_type=ACC_TYPE
    )
    ig_service.create_session()

    while True:
        try:
            positions = ig_service.fetch_open_positions()
            pos_list = positions.to_dict(orient='records')

            process_epic(ig_service, pos_list)

            # --- Time-based tasks (end-of-day etc.) ---

            time.sleep(30)

            now = datetime.now().time()

            # Run app.main() once around 21:01–21:03
            if dt_time(21, 1) <= now < dt_time(21, 3):
                app.main()
                time.sleep(180)

            # Save IG trades to DB once around 21:12–21:14
            if dt_time(21, 12) <= now < dt_time(21, 14):
                db = sqlite3.connect('streamed_prices.db')
                c = db.cursor()
                trdes.save_ig_trades_to_db(db, c, days=3)
                db.close()
                time.sleep(60)

        except Exception as e:
            # Minimal logging; you can swap this for proper logging
            print(f"[{EPIC} SERVICE] Error: {e}")
            time.sleep(10)


if __name__ == '__main__':
    main_loop()
