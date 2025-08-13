import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()  # take environment variables

test = True
loggedIn = False
API_KEY = ""
wall_street = 'IX.D.DOW.DAILY.IP'
trade_ready = False
open_position = False
CST = ""
X_SEC_TOKEN = ""
ACCOUNT_ID = ""
num = 0