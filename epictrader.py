from trading_ig import IGService
import sqlite3
from dotenv import load_dotenv
import time
import os
import models.user as user
import models.indicators as indicators
import models.prices as prices
import models.setup as setup
import models.trade_executor as trade_executor
import models.trades as trades
from datetime import datetime, timezone, time as dt_time
import app

load_dotenv()
usr = user.User()
price = prices.Prices()
ind = indicators.Indicators()
trdes = trades.Trades()
te = trade_executor.TradeExecutor()

setup.create_trades_table()
setup.create_trading_check_table()
setup.update_trades_table()

API_KEY = os.getenv('API_KEY')
username = os.getenv('IDENTIFIER')
user_pw = os.getenv('PASSWORD')
acc_type = os.getenv('ACC_TYPE')

cooldown_minutes = 30


def last_trade_time(db, c, epic):
    c.execute("""
        SELECT trade_date
        FROM trade_data
        WHERE epic = ?
        ORDER BY datetime(trade_date) DESC
        LIMIT 1
    """, (epic,))
    row = c.fetchone()
    if not row:
        return None

    # Parse and force UTC timezone
    return datetime.fromisoformat(row[0]).replace(tzinfo=timezone.utc)


def traderbt():
    ig_service = usr.login_ig(IGService, username, user_pw, API_KEY, acc_type=acc_type)
    ig_service.create_session()

    positions = ig_service.fetch_open_positions()
    pos_list = positions.to_dict(orient='records')

    epics = ['IX.D.DOW.DAILY.IP', 'IX.D.FTSE.DAILY.IP', 'CS.D.USCGC.TODAY.IP']
    buy_size = ['0.01', '0.05', '0.05']
    sell_size = ['0.01', '0.05', '0.05']
    max_stop = [30, 15, 10]

    trading_hours = [
        {'open': 2, 'close': 19},
        {'open': 2, 'close': 19},
        {'open': 2, 'close': 19},
    ]

    for index, epic in enumerate(epics):
        open_pos = None
        for p in pos_list:
            if p['epic'] == epic:
                open_pos = p
                break

        db = sqlite3.connect('streamed_prices.db')
        c = db.cursor()
        lt = last_trade_time(db, c, epic)
        db.close()

        now_utc = datetime.now(timezone.utc)

        df = price.load_ohlc(epic, '5MINUTE')
        df = df.sort_values(by='date', ascending=True)
        df = ind.calculate_macd(df, 5, 35, 5)
        df = ind.calculate_rsi(df, 21)
        df = ind.calculate_cci(df, 90)
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df = ind.add_atr(df, 14)

        last = df.iloc[-1]

        in_hours = (
            ind.is_within_trading_hours(last['date'], trading_hours[index]['open'], trading_hours[index]['close'])
        )

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

        if open_pos is None:
            if lt is None or (now_utc - lt).total_seconds() > cooldown_minutes * 60:
                if in_hours and buy_signal:
                    atr = last['atr']
                    stop_distance = min(max_stop[index], 2.0 * atr)

                    trade = te.open_trade(
                        ig_service, epic, expiry='DFB', direction='BUY',
                        size=buy_size[index], order_type='MARKET',
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
                    stop_distance = min(max_stop[index], 2.0 * atr)

                    trade = te.open_trade(
                        ig_service, epic, expiry='DFB', direction='SELL',
                        size=sell_size[index], order_type='MARKET',
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

        else:
            df_recent = price.load_ohlc(epic, '5MINUTE', records=100)
            df_recent = df_recent.sort_values(by='date', ascending=True)
            df_recent = ind.add_atr(df_recent, 14)
            last_r = df_recent.iloc[-1]
            atr = last_r['atr']

            entry = open_pos['level']
            stop = open_pos['stopLevel']
            current = last_r['close']

            if open_pos['direction'] == 'BUY':
                #r = (current - entry) / (entry - stop) if entry != stop else 0
                risk = abs(entry - stop)
                # If risk is zero or tiny, rebuild it using ATR
                if risk < 1e-6:
                    risk = 2.0 * atr
                r = (current - entry) / risk
                print(open_pos['epic'], entry, current, stop, r)
                if r >= 1.0 and stop < entry:
                    new_stop = entry
                elif r >= 2.0:
                    new_stop = current - 1.5 * atr
                else:
                    new_stop = stop

                if new_stop > stop:
                    response = ig_service.update_open_position(
                        limit_level=None, stop_level=new_stop, deal_id=open_pos['dealId']
                    )
                    print(response)

            if open_pos['direction'] == 'SELL':
                #r = (entry - current) / (stop - entry) if entry != stop else 0
                risk = abs(entry - stop)
                # If risk is zero or tiny, rebuild it using ATR
                if risk < 1e-6:
                    risk = 2.0 * atr
                r = (entry - current) / risk
                print(open_pos['epic'], entry, current, stop, r)
                if r >= 1.0 and stop > entry:
                    new_stop = entry
                elif r >= 2.0:
                    new_stop = current + 1.5 * atr
                else:
                    new_stop = stop

                if new_stop < stop:
                    response = ig_service.update_open_position(
                        limit_level=None, stop_level=new_stop, deal_id=open_pos['dealId']
                    )
                    print(response)

    time.sleep(30)

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


while True:
    traderbt()
