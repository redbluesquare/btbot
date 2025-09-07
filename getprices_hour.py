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

class MultiEpicPriceListener:
    def __init__(self, scale, store_to_db):
        self.scale = scale
        self.store_to_db = store_to_db

    def onSubscription(self):
        print(f"✅ Subscription active for multiple epics @ {self.scale}")

    def onItemUpdate(self, update):
        item_name = update.getItemName()  # e.g. "CHART:CS.D.EURUSD.MINI.IP:1MINUTE"
        try:
            _, epic, _ = item_name.split(":")  # extract epic from item name
        except ValueError:
            print(f"⚠️ Unexpected item format: {item_name}")
            return
        if update.getValue("CONS_END") == "1":
            ts = pd.to_datetime(int(update.getValue("UTM")), unit="ms")
            ohlc = {
                "epic":  epic,
                "date":  ts.strftime("%Y-%m-%d %H:%M:%S"),
                "scale": self.scale,
                "bid_open":  float(update.getValue("BID_OPEN")),
                "bid_high":  float(update.getValue("BID_HIGH")),
                "bid_low":   float(update.getValue("BID_LOW")),
                "bid_close": float(update.getValue("BID_CLOSE")),
                "offer_open":  float(update.getValue("OFR_OPEN")),
                "offer_high":  float(update.getValue("OFR_HIGH")),
                "offer_low":   float(update.getValue("OFR_LOW")),
                "offer_close": float(update.getValue("OFR_CLOSE"))
            }
            self.store_to_db(ohlc)
    def onItemLostUpdates(self, item, lost, key):
        print(f"⚠️ Lost {lost} updates for {item}")


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
                "bid_open":  float(update.getValue("BID_OPEN")),
                "bid_high":  float(update.getValue("BID_HIGH")),
                "bid_low":   float(update.getValue("BID_LOW")),
                "bid_close": float(update.getValue("BID_CLOSE")),
                "offer_open":  float(update.getValue("OFR_OPEN")),
                "offer_high":  float(update.getValue("OFR_HIGH")),
                "offer_low":   float(update.getValue("OFR_LOW")),
                "offer_close": float(update.getValue("OFR_CLOSE"))
            }
            self.store_to_db(ohlc)

    def onItemLostUpdates(self, item, lost, key):
        # Optional- but great for catching dropped packets
        print(f"⚠️ Lost {lost} updates for {item}")

def store_to_db( ohlc):
        db = sqlite3.connect('streamed_prices.db')
        c = db.cursor()
        try:
            c.execute('''
                CREATE TABLE IF NOT EXISTS ohlc_data (
                    epic TEXT,
                    date TEXT,
                    scale TEXT,
                    bid_open REAL,
                    bid_high REAL,
                    bid_low REAL,
                    bid_close REAL,
                    offer_open REAL,
                    offer_high REAL,
                    offer_low REAL,
                    offer_close REAL,
                    PRIMARY KEY (epic, date, scale)
                )
            ''')
            c.execute('''
                INSERT OR REPLACE INTO ohlc_data (epic, date, scale, bid_open, bid_high, bid_low, bid_close, offer_open, offer_high, offer_low, offer_close)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ohlc['epic'], ohlc['date'], ohlc['scale'], ohlc['bid_open'], ohlc['bid_high'], ohlc['bid_low'], ohlc['bid_close'], ohlc['offer_open'], ohlc['offer_high'], ohlc['offer_low'], ohlc['offer_close']))
            db.commit()
        except Exception as e:
            print(str(e))
        db.close()

# 1) Login + fetch tokens
ig_service = IGService(username=os.getenv("IDENTIFIER"),password=os.getenv("PASSWORD"),
                            api_key=os.getenv("API_KEY"),acc_type=os.getenv("ACC_TYPE"))
ig_service.lightstreamer_endpoint = os.getenv('LIGHTSTREAM_URL')  
stream_svc = IGStreamService(ig_service)
stream_svc.create_session()
stream_svc.ls_client.connect()

# 3) Build raw Subscription
scale  = "HOUR"
epics = ['IX.D.FTSE.DAILY.IP', 'CS.D.USCGC.TODAY.IP','IX.D.DOW.DAILY.IP']
items = [f"CHART:{epic}:{scale}" for epic in epics]
#epic   = "IX.D.FTSE.DAILY.IP"
#item   = f"CHART:{epic}:{scale}"
fields = ["BID_OPEN","BID_HIGH","BID_LOW","BID_CLOSE","OFR_OPEN","OFR_HIGH","OFR_LOW","OFR_CLOSE","CONS_END","UTM"]
sub  = Subscription("MERGE",items, fields)
sub.addListener(DebugSubListener())       # wrapper listener
sub.addListener(MultiEpicPriceListener(scale, store_to_db))

# 3) Subscribe on the wrapper’s client
stream_svc.ls_client.subscribe(sub)

while True: time.sleep(1)