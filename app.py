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
import models.backtests as backtests
import schedule
from datetime import datetime

load_dotenv()  # take environment variables
usr = user.User()
price = prices.Prices()
ind = indicators.Indicators()
btest = backtests.Backtests()

API_KEY = os.getenv('API_KEY')
username = os.getenv('IDENTIFIER')
user_pw = os.getenv('PASSWORD')
acc_type = os.getenv('ACC_TYPE')

#ig_service = usr.login_ig(IGService, username, user_pw, API_KEY, acc_type=acc_type)
#ig_service.create_session()
#res = ig_service.fetch_open_positions()
#if res.empty:

# No trade is open, continue and check if ready to open a new trade
epics = ['CS.D.USCGC.TODAY.IP','IX.D.DOW.DAILY.IP']
df = price.load_ohlc(epics[1], '5MINUTE')
df = ind.calculate_macd(df)
df = ind.calculate_rsi(df)
df['buy_signal'] = False
df['sell_signal'] = False
window = df.iloc[len(df)-4:len(df)-1]
buy = (window['macd'] > window['signal']) & (window['rsi'] > 50)
for j in window.index:
    ts = df.at[j, 'date']
    if ind.is_within_trading_hours(ts):
        buy_condition = (window['macd'] > window['signal']) & (window['rsi'] > 50)
        if buy_condition.any():
            buy_index = window[buy_condition].index[0]
            df.at[buy_index, 'buy_signal'] = True

window = df.iloc[len(df)-4:len(df)-1]
for i, row in df.iterrows():
    print(row)

#  Check epic 

#epics = ['IX.D.FTSE.DAILY.IP','CS.D.USCGC.TODAY.IP','IX.D.DOW.DAILY.IP']


