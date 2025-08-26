import json
import requests

class User():

    def __init__(self):
        pass
        
    def login(self, base_url, api_key, username, user_pw, encrypted):
        loggedIn = False
        user_details = {"identifier": username,
                        "password": user_pw,
                        "encryptedPassword": encrypted}
        headers = {'Accept': 'application/json',
                    'Content-Type': 'application/json', 
                    'X-IG-API-KEY': api_key}
        r = requests.post(base_url + "session", json=user_details, headers=headers)
        if r.status_code == 200:
            loggedIn = True
        CST = r.headers['CST']
        X_SEC_TOKEN = r.headers['X-SECURITY-TOKEN']
        body = json.loads(str(r.text))
        ACCOUNT_ID = body['currentAccountId']
        return [loggedIn, CST, X_SEC_TOKEN, ACCOUNT_ID, api_key]