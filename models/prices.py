import json
import requests
import models.user as user
import models.indicators as indicators
import os
import sqlite3
import pandas as pd

class Prices():

    def __init__(self):
        self.user = user.User()
        
        pass
    
    def get_ohlc(self, db, c, epic, scale='1MINUTE', records=100):
        ind = indicators.Indicators()
        query = """
            SELECT epic, date, open
            ,high
            ,low
            ,close
            FROM price_data
            WHERE epic = ? AND scale = ?
            ORDER BY date DESC LIMIT ?
        """
        c.execute(query, (epic, scale, records))
        rows = c.fetchall()
        results = [dict(row) for row in rows]
        df = pd.DataFrame(results)
        df["open"]  = pd.to_numeric(df["open"], errors="coerce")
        df["high"]  = pd.to_numeric(df["high"], errors="coerce")
        df["low"]   = pd.to_numeric(df["low"], errors="coerce")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        # Convert date to datetime and set index
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values(by='date',ascending=True)
        df = ind.calculate_cci(df)
        df = ind.calculate_macd(df)
        df = ind.calculate_rsi(df)
        df = df.sort_values(by='date',ascending=False)
        return df
    
    def load_ohlc(self, epic, scale='1MINUTE', db_path="btbot.db", records=100):
        """
        Load OHLC data for a given epic and timeframe from SQLite.
        Returns a pandas DataFrame indexed by datetime.
        """
        conn = sqlite3.connect(db_path)
        query = """
            SELECT epic, date, open
            ,high
            ,low
            ,close
            FROM price_data
            WHERE epic = ? AND scale = ?
            ORDER BY date DESC LIMIT ?
        """
        df = pd.read_sql_query(query, conn, params=(epic, scale, records))
        conn.close()
        df["open"]  = pd.to_numeric(df["open"], errors="coerce")
        df["high"]  = pd.to_numeric(df["high"], errors="coerce")
        df["low"]   = pd.to_numeric(df["low"], errors="coerce")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        # Convert date to datetime and set index
        df["date"] = pd.to_datetime(df["date"])
        #df.set_index("date", inplace=True)
        return df
    
    def get_prices(self, base_url, api_key, cst, x_sec_token, epic, resolution, start_time, end_time):
        #Get market data
        headers = {'Accept': 'application/json',
                    'Content-Type': 'application/json', 
                    'X-IG-API-KEY': api_key,
                    'CST': cst,
                    'X-SECURITY-TOKEN':x_sec_token,
                    'Version':'3'
                    }
        r = requests.get(base_url + 'prices/' + epic + '?resolution=' + resolution + '&from='+start_time+'&to='+end_time+'&max=19999&pageSize=0', headers=headers)
        w_str_data = json.loads(r.text)
        return w_str_data
    
    def get_x_prices(self, base_url, api_key, cst, x_sec_token, epic, resolution, numPoints:int = 100):
        #Get market data
        headers = {'Accept': 'application/json',
                    'Content-Type': 'application/json', 
                    'X-IG-API-KEY': api_key,
                    'CST': cst,
                    'X-SECURITY-TOKEN':x_sec_token,
                    'Version':'3'
                    }
        url = base_url + 'prices/' + epic + '?resolution=' + resolution + '&max='+str(numPoints)
        r = requests.get(url, headers=headers)
        w_str_data = json.loads(r.text)
        return w_str_data