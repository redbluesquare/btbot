from trading_ig import IGService
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

# epic = 'CS.D.GBPEUR.TODAY.IP'
epic = 'CS.D.USCGC.TODAY.IP'
# epic = 'IX.D.DOW.DAILY.IP'

#resolution = 'DAY'
#resolution = 'HOUR_2'
resolution = 'MINUTE_5'

#filename = 'w_s_daily_prices'
#filename = 'gold_daily'
filename = 'gold_hour_2'
#filename = 'gold_minute_5'

#while True:
# 📂 Load the CSV file
df = pd.read_csv(filename+'.csv', parse_dates=['date'])
#cci = ind.calculate_cci(df)
df = ind.calculate_macd(df)
df = ind.calculate_rsi(df)
df = ind.calculate_ratcheting_trailing_stop(df, 1, 6)

df = ind.generate_signals(df, 2)

#df, trades = btest.backtest_macd_rsi_buy_sell(df, shares=10)
df, trades = btest.backtest_spreadbet(df, stake_per_point=1)

# View trades
for t in trades:
    print(t)

# Plot running PnL
import matplotlib.pyplot as plt

plt.figure(figsize=(12,6))
plt.plot(df['date'], df['running_pnl'], label='Cumulative PnL', color='green')
plt.title('Backtest: Cumulative Profit/Loss')
plt.xlabel('Date')
plt.ylabel('PnL (£)')
plt.legend()
plt.grid(True)
plt.show()

def run_strategy():
    print(f"Running strategy at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    # Your logic here: fetch price, update CSV, run backtest, etc.

# Schedule the task
schedule.every().monday.at("08:00").do(run_strategy)
schedule.every().tuesday.at("08:00").do(run_strategy)
schedule.every().wednesday.at("08:00").do(run_strategy)
schedule.every().thursday.at("08:00").do(run_strategy)
schedule.every().friday.at("08:00").do(run_strategy)

# Keep the scheduler running
while True:
    schedule.run_pending()
    time.sleep(20)