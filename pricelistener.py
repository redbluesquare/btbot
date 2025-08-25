import os, time, sqlite3, pandas as pd, logging
from dotenv import load_dotenv
from trading_ig import IGService
from models.user import User
from lightstreamer.client import (
    LightstreamerClient,
    Subscription,
    SubscriptionListener
)

logging.basicConfig(level=logging.DEBUG)
load_dotenv()

# — 1) Log in to IG (DEMO or LIVE must match)
usr = User()
ig_svc = usr.login_ig(
    IGService,
    os.getenv("IDENTIFIER"),
    os.getenv("PASSWORD"),
    os.getenv("API_KEY"),
    acc_type=os.getenv("ACC_TYPE")  # DEMO or LIVE
)
ig_svc.create_session()
cst   = ig_svc.session.headers["CST"]
xsec  = ig_svc.session.headers["X-SECURITY-TOKEN"]
ls_host = 'https://push.lightstreamer-demo.ig.com'

# — 2) Wire up the raw LightstreamerClient
client = LightstreamerClient(ls_host, "CHARTING")
client.connect()
client.connectionDetails.user     = cst
client.connectionDetails.password = xsec
print("🔗 Connecting to Lightstreamer…")

# — 3) Build & configure your 5-min CHART subscription
epic   = "CS.D.EURUSD.MINI.IP"
scale  = "1MINUTE"
item   = f"CHART:{epic}:{scale}"
fields = ["BID_OPEN","BID_HIGH","BID_LOW","BID_CLOSE","CONS_END","UTM"]

sub = Subscription("MERGE", [item], fields)
sub.setDataAdapter("QUOTE_ADAPTER")
sub.setRequestedSnapshot("yes")

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

# attach
sub.addListener(DebugSubListener())
sub.addListener(PriceListener())

print("▶️ Subscribing…")
client.subscribe(sub)

# — 5) Keep alive
while True:
    time.sleep(0.5)
    #print('...')
