from trading_ig import IGService
from dotenv import load_dotenv
import os
import models.user as user
from datetime import datetime, timedelta, timezone
load_dotenv()  # take environment variables

class Trades():

    def __init__(self):
        self.user = user.User()
        self.API_KEY = os.getenv('API_KEY')
        self.username = os.getenv('IDENTIFIER')
        self.user_pw = os.getenv('PASSWORD')
        self.acc_type = os.getenv('ACC_TYPE')
        pass
    
    def prev_day_range(self, tz=timezone.utc):
        now = datetime.now(tz)
        prev = (now - timedelta(days=10)).replace(hour=0, minute=0, second=0, microsecond=0)
        next_day = prev + timedelta(days=10)
        return prev, next_day

    def getPreviousTrades(self):
        ig_service = self.user.login_ig(IGService, self.username, self.user_pw, self.API_KEY, acc_type=self.acc_type)
        ig_service.create_session()
        from_dt, to_dt = self.prev_day_range()
        activities = ig_service.fetch_transaction_history(from_date=str(from_dt)[:10], to_date=str(to_dt)[:10], page_size=999)
        return activities
    
class Account():
    def __init__(self):
        self.user = user.User()
        self.API_KEY = os.getenv('API_KEY')
        self.username = os.getenv('IDENTIFIER')
        self.user_pw = os.getenv('PASSWORD')
        self.acc_type = os.getenv('ACC_TYPE')
        pass
    def getAccountDetails(self):
        ig_service = self.user.login_ig(IGService, self.username, self.user_pw, self.API_KEY, acc_type=self.acc_type)
        ig_service.create_session()
        accounts = ig_service.fetch_accounts()
        return accounts