from trading_ig import IGService
from trading_ig.stream import IGStreamService, Subscription
import time, pandas as pd
import os
import sqlite3
from dotenv import load_dotenv
from collections import defaultdict
import signal
import threading

stop_event = threading.Event()

def handle_sigint(sig, frame):
    print("Shutting down...")
    stop_event.set()

signal.signal(signal.SIGINT, handle_sigint)

load_dotenv()

# ---------------------------------------
# DB STORAGE (simplified schema)
# ---------------------------------------
def store_to_db(ohlc):
    db = sqlite3.connect('btbot.db')
    c = db.cursor()
    try:
        c.execute('''
            CREATE TABLE IF NOT EXISTS price_data (
                epic TEXT,
                date TEXT,
                scale TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                PRIMARY KEY (epic, date, scale)
            )
        ''')

        c.execute('''
            INSERT OR REPLACE INTO price_data 
            (epic, date, scale, open, high, low, close)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            ohlc['epic'], ohlc['date'], ohlc['scale'],
            ohlc['open'], ohlc['high'], ohlc['low'], ohlc['close']
        ))

        db.commit()
    except Exception as e:
        print("DB error:", e)
    finally:
        db.close()


# ---------------------------------------
# TICK → CANDLE AGGREGATOR
# ---------------------------------------
class TickAggregator:
    """
    Builds 1-minute and 5-minute candles from MARKET ticks.
    """

    def __init__(self, store_func):
        self.store = store_func
        self.current_1m = {}
        self.current_5m = {}
        self.last_5m_bucket = {}

    def process_tick(self, epic, bid, offer, ts):
        mid = (bid + offer) / 2
        minute_ts = ts.replace(second=0, microsecond=0)


        # -------------------------
        # 1-MINUTE CANDLE
        # -------------------------
        if epic not in self.current_1m:
            # Start new candle
            self.current_1m[epic] = {
                "epic": epic,
                "date": minute_ts.strftime("%Y-%m-%d %H:%M:%S"),
                "scale": "1MINUTE",
                "open": mid,
                "high": mid,
                "low": mid,
                "close": mid
            }
        else:
            c = self.current_1m[epic]
            if c["date"] != minute_ts.strftime("%Y-%m-%d %H:%M:%S"):
                # Close previous candle
                self.store(c)
                # Start new candle
                self.current_1m[epic] = {
                    "epic": epic,
                    "date": minute_ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "scale": "1MINUTE",
                    "open": mid,
                    "high": mid,
                    "low": mid,
                    "close": mid
                }
            else:
                # Update candle
                c["high"] = max(c["high"], mid)
                c["low"] = min(c["low"], mid)
                c["close"] = mid

        # -------------------------
        # 5-MINUTE CANDLE
        # -------------------------
        bucket_minute = ts.minute - (ts.minute % 5)
        bucket_ts = ts.replace(minute=bucket_minute, second=0, microsecond=0)

        if epic not in self.current_5m:
            self.current_5m[epic] = {
                "epic": epic,
                "date": bucket_ts.strftime("%Y-%m-%d %H:%M:%S"),
                "scale": "5MINUTE",
                "open": mid,
                "high": mid,
                "low": mid,
                "close": mid
            }
            self.last_5m_bucket[epic] = bucket_ts
        else:
            if bucket_ts != self.last_5m_bucket[epic]:
                # Close previous 5m candle
                self.store(self.current_5m[epic])
                # Start new bucket
                self.current_5m[epic] = {
                    "epic": epic,
                    "date": bucket_ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "scale": "5MINUTE",
                    "open": mid,
                    "high": mid,
                    "low": mid,
                    "close": mid
                }
                self.last_5m_bucket[epic] = bucket_ts
            else:
                c = self.current_5m[epic]
                c["high"] = max(c["high"], mid)
                c["low"] = min(c["low"], mid)
                c["close"] = mid


# ---------------------------------------
# MARKET STREAM LISTENER
# ---------------------------------------
class MarketListener:
    def __init__(self, aggregator):
        self.agg = aggregator

    def onSubscription(self):
        print("📡 MARKET subscription active")

    def onItemUpdate(self, update):
        item_name = update.getItemName()
        try:
            _, epic = item_name.split(":")
        except ValueError:
            print("Bad item:", item_name)
            return

        bid = float(update.getValue("BID"))
        offer = float(update.getValue("OFFER"))
        ts_raw = update.getValue("UPDATE_TIME")

        if bid is None or offer is None or ts_raw is None:
            print("⚠️ Missing fields in tick:", update.getFields())
            return

        bid = float(bid)
        offer = float(offer)

        # Convert UPDATE_TIME (string like "2025-01-01T12:34:56.789")
        ts = pd.to_datetime(ts_raw)

        self.agg.process_tick(epic, bid, offer, ts)

    def onItemLostUpdates(self, item, lost, key):
        print(f"⚠️ Lost {lost} updates for {item}")


# ---------------------------------------
# IG LOGIN + STREAM SETUP
# ---------------------------------------
ig_service = IGService(
    username=os.getenv("IDENTIFIER"),
    password=os.getenv("PASSWORD"),
    api_key=os.getenv("API_KEY"),
    acc_type=os.getenv("ACC_TYPE")
)

ig_service.lightstreamer_endpoint = os.getenv("LIGHTSTREAM_URL")

stream_svc = IGStreamService(ig_service)
stream_svc.create_session()
stream_svc.ls_client.connect()

# MARKET subscription
epics = ['IX.D.FTSE.DAILY.IP', 'CS.D.USCGC.TODAY.IP', 'IX.D.DOW.DAILY.IP']
items = [f"MARKET:{epic}" for epic in epics]

fields = ["BID", "OFFER", "UPDATE_TIME"]

sub = Subscription("MERGE", items, fields)
sub.addListener(MarketListener(TickAggregator(store_to_db)))

stream_svc.ls_client.subscribe(sub)

stop_event.wait()

stream_svc.ls_client.disconnect()
print("Disconnected cleanly")
