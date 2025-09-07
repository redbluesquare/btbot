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
import schedule
from datetime import datetime

load_dotenv()  # take environment variables
usr = user.User()
price = prices.Prices()
ind = indicators.Indicators()
btest = backtests.Backtests()
te = trade_executor.TradeExecutor()

API_KEY = os.getenv('API_KEY')
username = os.getenv('IDENTIFIER')
user_pw = os.getenv('PASSWORD')
acc_type = os.getenv('ACC_TYPE')

def traderbt():
    ig_service = usr.login_ig(IGService, username, user_pw, API_KEY, acc_type=acc_type)
    ig_service.create_session()
    res = ig_service.fetch_open_positions()
    if res.empty:
        # No trade is open, continue and check if ready to open a new trade
        epics = ['CS.D.USCGC.TODAY.IP','IX.D.DOW.DAILY.IP']
        df = price.load_ohlc(epics[1], '5MINUTE')
        df = ind.calculate_macd(df)
        df = ind.calculate_rsi(df)
        df['buy_signal'] = False
        df['sell_signal'] = False
        window = df.iloc[len(df)-4:len(df)-1]
        buy_condition = window['bullish_crossover'].any() & window['rsi_cross_above_50'].any()
        if buy_condition and ind.is_within_trading_hours(window.iloc[-1]['date']):
            buy_index = window.index[-1]
            df.at[buy_index, 'buy_signal'] = True
            # create an order
            epic=window.iloc[-1]['epic']
            expiry='DFB'
            direction='BUY'
            size='0.10'
            order_type='MARKET'
            currency_code='GBP'
            guaranteed_stop=True
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
        else:
            for i, row in window.iterrows():
                print(row)
            print('Buy condition:', buy_condition)
    else:
        print(res)
    time.sleep(1*60)

while True:
    traderbt()


