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

ig_service = usr.login_ig(IGService, username, user_pw, API_KEY, acc_type=acc_type)

#epics = ['IX.D.FTSE.DAILY.IP','CS.D.USCGC.TODAY.IP','IX.D.DOW.DAILY.IP']
epics = ['CS.D.USCGC.TODAY.IP','IX.D.DOW.DAILY.IP']

for epic in epics:
    df = price.load_ohlc(epic, '1MINUTE')
    #cci = self.ind.calculate_cci(df)
    df = ind.calculate_macd(df)
    df = ind.calculate_rsi(df)
    #print(df.head())
    btest.backtest(epic, '1MINUTE')

