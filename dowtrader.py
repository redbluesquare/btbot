from trading_ig import IGService
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from dotenv import load_dotenv
import time
import os
import models.user as user
import models.indicators as indicators
import models.prices as prices
import models.trade_executor as trade_executor
import models.backtests as backtests
import models.setup as setup
import schedule
from datetime import datetime, time as dt_time
import app

load_dotenv()  # take environment variables
usr = user.User()
price = prices.Prices()
ind = indicators.Indicators()
btest = backtests.Backtests()
te = trade_executor.TradeExecutor()
setup.create_trades_table()
setup.create_trading_check_table

API_KEY = os.getenv('API_KEY')
username = os.getenv('IDENTIFIER')
user_pw = os.getenv('PASSWORD')
acc_type = os.getenv('ACC_TYPE')

def traderbt():
    ig_service = usr.login_ig(IGService, username, user_pw, API_KEY, acc_type=acc_type)
    ig_service.create_session()
    positions = ig_service.fetch_open_positions()
    if positions.empty:
        # No trade is open, continue and check if ready to open a new trade
        epics = ['CS.D.USCGC.TODAY.IP','IX.D.DOW.DAILY.IP']
        df = price.load_ohlc(epics[1], '5MINUTE')
        df = df.sort_values(by='date',ascending=True)
        df = ind.calculate_macd(df, 5, 35, 5)
        df = ind.calculate_rsi(df, 21)
        df = ind.calculate_cci(df, 90)
        df['buy_signal'] = False
        df['sell_signal'] = False
        window = df.iloc[len(df)-6:]
        buy_condition1 = window['bullish_crossover'].any() & window['rsi_cross_above_50'].any()
        buy_condition2 = window['bullish_crossover'].any() & window['rsi_bullish'].any()
        if (buy_condition1 or buy_condition2 or window['cci_bullish_crossover'].any()) and ind.is_within_trading_hours(window.iloc[-1]['date'], 9, 19):
            buy_index = window.index[-1]
            df.at[buy_index, 'buy_signal'] = True
            # create an order
            epic=window.iloc[-1]['epic']
            expiry='DFB'
            direction='BUY'
            size='0.1'
            order_type='MARKET'
            currency_code='GBP'
            guaranteed_stop=False
            force_open=True
            stop_distance=window.iloc[-1]['close']-window['low'].min()+8
            trade = te.open_trade(ig_service, epic, expiry=expiry, direction=direction, size=size,order_type=order_type,currency_code=currency_code
                        ,guaranteed_stop=guaranteed_stop, force_open=force_open, stop_distance=stop_distance)
            print(trade)
            db = sqlite3.connect('streamed_prices.db')
            c = db.cursor()
            c.execute(''' 
                            INSERT OR REPLACE INTO trade_data 
                            (epic, trade_date, trade_type, dealId, dealStatus, price, stake, macd, rsi, pnl)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''',(trade['epic'], trade['date'], trade['direction'], trade['dealId'], trade['dealStatus']
                            ,trade['level'], trade['size'], window.iloc[-1]['macd'], window.iloc[-1]['rsi'], 0))
            db.commit()
            db.close()
            time.sleep(60*15)
        else:
            for i, row in window.iterrows():
                print(row['epic'],row['date'],row['macd'],row['signal'],row['rsi'],row['bullish_crossover'],row['rsi_cross_above_50'], row['cci_bullish_crossover'])
            print('Buy condition:', buy_condition1, buy_condition2)
        time.sleep(30)
    else:
        epics = ['CS.D.USCGC.TODAY.IP','IX.D.DOW.DAILY.IP']
        df = price.load_ohlc(epics[1], '5MINUTE')
        df = df.sort_values(by='date',ascending=True)
        window = df.iloc[len(df)-2:]
        #Check the stop level and update if it rises
        low = window['low'].min()-8
        stopLevel = positions.iloc[-1]['stopLevel']
        if low > stopLevel:
            # update the open position
            response = ig_service.update_open_position(limit_level=None, stop_level=low, deal_id=positions.iloc[-1]['dealId'])
            print(response)
            db = sqlite3.connect('streamed_prices.db')
            c = db.cursor()
            c.execute(''' 
                            UPDATE trade_data 
                            SET stopLevel = ?
                            where dealId = ?
                        ''',(response['stopLevel'],  response['dealId']))
            db.commit()
            db.close()
        else:
            for i, row in window.iterrows():
                print(row)
        time.sleep(60)
    now = datetime.now().time()
    if dt_time(21, 0) <= now < dt_time(22, 0):
        app.main()
        time.sleep(60*61)
while True:
    traderbt()
    