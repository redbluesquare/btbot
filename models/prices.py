import json
import requests
import models.user as user
import os
import sqlite3
import pandas as pd

class Prices():

    def __init__(self):
        self.user = user.User()
        
        pass
    
    def load_ohlc(self, epic, scale='1MINUTE', db_path="streamed_prices.db"):
        """
        Load OHLC data for a given epic and timeframe from SQLite.
        Returns a pandas DataFrame indexed by datetime.
        """
        conn = sqlite3.connect(db_path)
        query = """
            SELECT epic, date, (bid_open+offer_open)/2 open
            ,(bid_high+offer_high)/2 high
            ,(bid_low+offer_low)/2 low
            ,(bid_close+offer_close)/2 close
            FROM ohlc_data
            WHERE epic = ? AND scale = ?
            ORDER BY date ASC
        """
        df = pd.read_sql_query(query, conn, params=(epic, scale))
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