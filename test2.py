from trading_ig import IGService
from trading_ig.stream import IGStreamService, Subscription 
import time, pandas as pd
import os
import sqlite3
import models.user as user
from dotenv import load_dotenv

load_dotenv()

usr = user.User()

class DebugSubListener:
    def onSubscription(self):
        # Called when Lightstreamer has accepted your subscription
        print("✅ Subscription OK")

    def onSubscriptionError(self, code, message):
        # Called if LS rejects your sub (e.g. invalid epic, wrong adapter, out-of-hours…)
        print(f"❌ Subscription error ({code}): {message}")

    def onItemLostUpdates(self, item, lostUpdates, key):
        # Called whenever LS had to drop updates (buffer overflow, network hiccup…)
        print(f"⚠️ Lost {lostUpdates} updates for item {item}")

    def onUnsubscription(self):
        # Called when you or LS tear down the subscription
        print("🚫 Unsubscribed")

class PriceListener:
    def __init__(self, epic, scale, store_to_db):
        self.epic = epic
        self.scale = scale
        self.store_to_db = store_to_db

    def onSubscription(self):
        # Fires once your sub goes live
        print(f"✅ Subscribed to {self.epic} @ {self.scale}")

    def onItemUpdate(self, update):
        # Fires on *every* tick or merge update
        # Only act on completed candles
        if update.getValue("CONS_END") == "1":
            ts = pd.to_datetime(int(update.getValue("UTM")), unit="ms")
            ohlc = {
                "epic":  self.epic,
                "date":  ts.strftime("%Y-%m-%d %H:%M:%S"),
                "scale": self.scale,
                "open":  float(update.getValue("BID_OPEN")),
                "high":  float(update.getValue("BID_HIGH")),
                "low":   float(update.getValue("BID_LOW")),
                "close": float(update.getValue("BID_CLOSE"))
            }
            self.store_to_db(ohlc)

    def onItemLostUpdates(self, item, lost, key):
        # Optional- but great for catching dropped packets
        print(f"⚠️ Lost {lost} updates for {item}")

def store_to_db( ohlc):
        db = sqlite3.connect('streamed_prices.db')
        c = db.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS ohlc_data (
                epic TEXT,
                date TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                PRIMARY KEY (epic, date)
            )
        ''')
        c.execute('''
            INSERT OR REPLACE INTO ohlc_data (epic, date, open, high, low, close)
            VALUES (?, ?, ?, ?, ?)
        ''', (ohlc['epic'], ohlc['date'], ohlc['open'], ohlc['high'], ohlc['low'], ohlc['close']))
        db.commit()
        db.close()

# 1) Login + fetch tokens
ig_service = IGService(username=os.getenv("IDENTIFIER"),password=os.getenv("PASSWORD"),
                            api_key=os.getenv("API_KEY"),acc_type=os.getenv("ACC_TYPE"))
ig_service.lightstreamer_endpoint = os.getenv('LIGHTSTREAM_URL')  
stream_svc = IGStreamService(ig_service)
stream_svc.create_session()
stream_svc.ls_client.connect()

# 3) Build raw Subscription
epic   = "IX.D.FTSE.DAILY.IP"
scale  = "1MINUTE"
item   = f"CHART:{epic}:{scale}"
fields = ["BID_OPEN","BID_HIGH","BID_LOW","BID_CLOSE","CONS_END","UTM"]
sub  = Subscription("MERGE",[item], fields)
sub.addListener(DebugSubListener())       # wrapper listener
sub.addListener(PriceListener(epic, scale, store_to_db))

# 3) Subscribe on the wrapper’s client
stream_svc.ls_client.subscribe(sub)

while True: time.sleep(1)