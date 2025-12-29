from trading_ig import IGService
import sqlite3
from dotenv import load_dotenv
import time
import os
import models.user as user
import models.indicators as indicators
import models.prices as prices
import models.trade_executor as trade_executor
import models.setup as setup
from datetime import datetime, time as dt_time
import app

load_dotenv()  # take environment variables
usr = user.User()
price = prices.Prices()
ind = indicators.Indicators()

te = trade_executor.TradeExecutor()
setup.create_trades_table()
setup.create_trading_check_table

API_KEY = os.getenv('API_KEY')
username = os.getenv('IDENTIFIER')
user_pw = os.getenv('PASSWORD')
acc_type = os.getenv('ACC_TYPE')

def traderbt():
    ig_service = usr.login_ig(IGService, username, user_pw, API_KEY, acc_type=acc_type)
    ig_service.create_session()
    positions = ig_service.fetch_open_positions()
    
    epics = ['CS.D.USCGC.TODAY.IP','IX.D.DOW.DAILY.IP','IX.D.FTSE.DAILY.IP']
    buffer = [4,8,4]
    buy_size = ['0.5', '0.1', '0.2']
    sell_size = ['0.25', '0.05', '0.1']
    trading_hours = [
        {'open':5,'close':20},
        {'open':7,'close':20},
        {'open':6,'close':19},
    ]
    new_trade = [0,0,0]
    for index, epic in enumerate(epics):
        p = positions.to_dict(orient='records')
        details = None
        for item in p:
            if item['epic'] == epic:
                details = item
                break
        if details == None:
            # No trade is open, continue and check if ready to open a new trade
            df = price.load_ohlc(epic, '5MINUTE')
            df = df.sort_values(by='date',ascending=True)
            df = ind.calculate_macd(df, 5, 35, 5)
            df = ind.calculate_rsi(df, 21)
            df = ind.calculate_cci(df, 90)
            df['buy_signal'] = False
            df['sell_signal'] = False
            window = df.iloc[len(df)-4:]
            buy_condition1 = window['bullish_crossover'].any() & window['rsi_cross_above_50'].any()
            buy_condition2 = window['bullish_crossover'].any() & window['rsi_bullish'].any()
            sell_condition = window['bearish_crossover'].any() & window['rsi_bearish'].any()
            if (buy_condition1 or buy_condition2 or window['cci_bullish_crossover'].any()) and ind.is_within_trading_hours(window.iloc[-1]['date'], trading_hours[index]['open'], trading_hours[index]['close']):
                buy_index = window.index[-1]
                df.at[buy_index, 'buy_signal'] = True
                # create an order
                epic=window.iloc[-1]['epic']
                expiry='DFB'
                direction='BUY'
                size=buy_size[index]
                order_type='MARKET'
                currency_code='GBP'
                guaranteed_stop=False
                force_open=True
                stop_distance=window.iloc[-1]['close']-window['low'].min()+buffer[index]
                trade = te.open_trade(ig_service, epic, expiry=expiry, direction=direction, size=size,order_type=order_type,currency_code=currency_code
                            ,guaranteed_stop=guaranteed_stop, force_open=force_open, stop_distance=stop_distance)
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
                new_trade[index] = 30
            elif sell_condition and ind.is_within_trading_hours(window.iloc[-1]['date'], trading_hours[index]['open'], trading_hours[index]['close']):
                sell_index = window.index[-1]
                df.at[sell_index, 'sell_signal'] = True
                # create an order
                epic=window.iloc[-1]['epic']
                expiry='DFB'
                direction='SELL'
                size=sell_size[index]
                order_type='MARKET'
                currency_code='GBP'
                guaranteed_stop=False
                force_open=True
                stop_distance=window['high'].max()-window.iloc[-1]['close']+buffer[index]
                trade = te.open_trade(ig_service, epic, expiry=expiry, direction=direction, size=size,order_type=order_type,currency_code=currency_code
                            ,guaranteed_stop=guaranteed_stop, force_open=force_open, stop_distance=stop_distance)
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
                new_trade[index] = 30
        else:
            df = price.load_ohlc(epics[1], '5MINUTE')
            df = df.sort_values(by='date',ascending=True)
            if details['direction'] == 'BUY' and new_trade[index] == 0:
                window = df.iloc[len(df)-2:]
                #Check the stop level and update if it rises
                low = window['low'].min()-buffer[index]
                stopLevel = details['stopLevel']
                if low > stopLevel:
                    # update the open position
                    response = ig_service.update_open_position(limit_level=None, stop_level=low, deal_id=details['dealId'])
                    # Check if it updates
                    db = sqlite3.connect('streamed_prices.db')
                    c = db.cursor()
                    c.execute('''   UPDATE trade_data 
                                    SET stopLevel = ?
                                    where dealId = ?
                                ''',(response['stopLevel'],  response['dealId']))
                    db.commit()
                    db.close()
            if details['direction'] == 'SELL':
                window = df.iloc[len(df)-1:]
                #Check the stop level and update if it rises
                high = window['high'].max()+buffer[index]
                stopLevel = details['stopLevel']
                if high < stopLevel:
                    # update the open position
                    response = ig_service.update_open_position(limit_level=None, stop_level=high, deal_id=details['dealId'])
                    db = sqlite3.connect('streamed_prices.db')
                    c = db.cursor()
                    c.execute('''   UPDATE trade_data 
                                    SET stopLevel = ?
                                    WHERE dealId = ?
                                ''',(response['stopLevel'],  response['dealId']))
                    db.commit()
                    db.close()
        if new_trade[index] > 0:
            new_trade[index] = new_trade[index]-1
    print('sleeping...')
    time.sleep(30)
    now = datetime.now().time()
    if dt_time(21, 2) <= now < dt_time(21, 3):
        app.main()
        time.sleep(60*2)
while True:
    traderbt()
    