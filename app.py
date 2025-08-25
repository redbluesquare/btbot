from trading_ig import IGService
from trading_ig.stream import IGStreamService
from trading_ig.stream import Subscription
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
# Start Lightstreamer stream
ig_stream_service = IGStreamService(ig_service)
ig_stream_service.create_session()

#epic = ['CS.D.GBPEUR.TODAY.IP','CS.D.USCGC.TODAY.IP','IX.D.DOW.DAILY.IP']

epic = 'IX.D.FTSE.DAILY.IP'  # Replace with your instrument
scale = '1MINUTE'
item = f"CHART:{epic}:{scale}"

fields = [
    'BID_OPEN',
    'BID_HIGH',
    'BID_LOW',
    'BID_CLOSE',
    'CONS_END',     # Marks candle completion
    'UTM'           # Timestamp in milliseconds
]

# Create the subscription object
subscription = Subscription(
    mode="MERGE",
    items=[item],
    fields=fields
)

def safe_listener(update):
    try:
        price.on_price_update(update, epic)
    except Exception as e:
        print(f"❌ Listener error: {e}")

# Attach the listener function (don't call it!)
subscription.addListener(safe_listener)

# Subscribe using the Lightstreamer client
ig_stream_service.ls_client.subscribe(subscription)


def run_strategy():
    now = datetime.now()
    hour = now.hour
    weekday = now.weekday()  # Monday = 0, Sunday = 6

    if 0 <= weekday <= 4 and 4 <= hour < 23:
        print(f"✅ Running strategy at {now.strftime('%Y-%m-%d %H:%M:%S')}")
        # Your strategy logic here: fetch price, update CSV, run backtest, etc.
    else:
        print(f"⏸️ Skipped at {now.strftime('%Y-%m-%d %H:%M:%S')} (outside trading hours)")

# Schedule to run every minute
#schedule.every(1).minutes.do(run_strategy)

# Keep the scheduler running
#while True:
#    schedule.run_pending()
#    time.sleep(1)