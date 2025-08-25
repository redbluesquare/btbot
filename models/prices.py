import json
import requests
import models.user as user
import os

class Prices():

    def __init__(self):
        self.user = user.User()
        
        pass
        
    def add_prices(self, pd, epic, resolution, filename):
        loggedIn = False
        base_url = os.getenv('BASE_URL')
        API_KEY = os.getenv('API_KEY')
        username = os.getenv('IDENTIFIER')
        user_pw = os.getenv('PASSWORD')
        encrypted = os.getenv('ENCRYPTED_PASSWORD')
        print("logged in:", loggedIn)
        loggedIn, CST, X_SEC_TOKEN, ACCOUNT_ID, API_KEY = self.user.login(base_url, API_KEY, username, user_pw, encrypted) 
        print("logged in:", loggedIn)
        #ws_data = price.get_x_prices(base_url, API_KEY, CST, X_SEC_TOKEN, epic, resolution,100)['prices']
        ws_data = self.get_prices(base_url, API_KEY, CST, X_SEC_TOKEN, epic, resolution, '2025-07-15','2025-08-31')['prices']
        #ws_data = price.get_prices(base_url, API_KEY, CST, X_SEC_TOKEN, epic, resolution, '2024-01-01','2025-08-31')['prices']
        print(len(ws_data))
        df = pd.DataFrame(ws_data)
        print(df.head)
        # 🧹 Clean and format
        df['date'] = pd.to_datetime(df['snapshotTime'])
        df['open'] = df['openPrice'].apply(lambda x: x['bid'])
        df['close'] = df['closePrice'].apply(lambda x: x['bid'])  # Use bid or mid depending on preference 
        df['high'] = df['highPrice'].apply(lambda x: x['bid'])  # Use bid or mid depending on preference 
        df['low'] = df['lowPrice'].apply(lambda x: x['bid'])  # Use bid or mid depending on preference 
        df = df[['date', 'open', 'high', 'low', 'close']]
        # 💾 Save to CSV
        df.to_csv(filename+'.csv', index=False)
        print("✅ Price data saved to "+filename+".csv")
    
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