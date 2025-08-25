from trading_ig import IGService
from lightstreamer.client import LightstreamerClient, Subscription, SubscriptionListener  # ← raw Subscription
import time, pandas as pd
import os
import models.user as user
from dotenv import load_dotenv

load_dotenv()

usr = user.User()

# — 4) Add debug + price listeners
class DebugSubListener(SubscriptionListener):
    def onSubscription(self):
        print("✅ Subscription OK")
    def onSubscriptionError(self, code, msg):
        print("❌ Subscription error:", code, msg)

class PriceListener(SubscriptionListener):
    def onItemUpdate(self, update):
        print("🔄 Incoming update")  # you’ll see this now
        if update.getValue("CONS_END") == "1":
            ts   = pd.to_datetime(int(update.getValue("UTM")), unit="ms")
            ohlc = {
                "epic":  epic,
                "date":  ts.strftime("%Y-%m-%d %H:%M:%S"),
                "open":  float(update.getValue("BID_OPEN")),
                "high":  float(update.getValue("BID_HIGH")),
                "low":   float(update.getValue("BID_LOW")),
                "close": float(update.getValue("BID_CLOSE"))
            }
            print("✅ 5-min bar:", ohlc)
            # store_to_db(ohlc)

# 1) Login + fetch tokens
ig_svc = IGService(username=os.getenv("IDENTIFIER"),password=os.getenv("PASSWORD"),
                            api_key=os.getenv("API_KEY"),acc_type=os.getenv("ACC_TYPE"))
ig_svc.create_session()
cst  = ig_svc.session.headers["CST"]
xsec = ig_svc.session.headers["X-SECURITY-TOKEN"]
#host = ig_svc.lightstreamer_endpoint   # e.g. https://push.lightstreamer-demo.ig.com
host = 'https://push.lightstreamer-demo.ig.com'

# 2) Build raw client & connect
client = LightstreamerClient(host, "CHARTING")
client.connectionDetails.user     = cst
client.connectionDetails.password = xsec
client.connect()

# 3) Build raw Subscription
epic   = "IX.D.FTSE.DAILY.IP"
scale  = "1MINUTE"
item   = f"CHART:{epic}:{scale}"
fields = ["BID_OPEN","BID_HIGH","BID_LOW","BID_CLOSE","CONS_END","UTM"]
sub  = Subscription("MERGE",[item], fields)
sub.setDataAdapter("CHART_ADAPTER")
sub.setRequestedSnapshot("yes")

# 4) Attach raw listeners
sub.addListener(DebugSubListener())   # extends lightstreamer.client.SubscriptionListener
sub.addListener(PriceListener())

# 5) Subscribe on the raw client
client.subscribe
while True:
    time.sleep(1)