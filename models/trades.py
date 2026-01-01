from trading_ig import IGService
from dotenv import load_dotenv
import os
import models.user as user
from datetime import datetime, timedelta, timezone
import pandas as pd
load_dotenv()  # take environment variables

class Trades():

    def __init__(self):
        self.user = user.User()
        self.API_KEY = os.getenv('API_KEY')
        self.username = os.getenv('IDENTIFIER')
        self.user_pw = os.getenv('PASSWORD')
        self.acc_type = os.getenv('ACC_TYPE')
        pass
    
    def prev_day_range(self, tz=timezone.utc, days=10):
        now = datetime.now(tz)
        prev = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        next_day = prev + timedelta(days=days)
        return prev, next_day

    def getPreviousTrades(self, days=10):
        ig_service = self.user.login_ig(IGService, self.username, self.user_pw, self.API_KEY, acc_type=self.acc_type)
        ig_service.create_session()
        from_dt, to_dt = self.prev_day_range(days=days)
        activities = ig_service.fetch_transaction_history(from_date=str(from_dt)[:10], to_date=str(to_dt)[:10], page_size=999)
        return activities

    def getTradeByOpenDatePrice(self, db, c, data):
        query = """SELECT epic, trade_date, trade_type, dealId, dealStatus, price, stake, macd, rsi, pnl 
                    FROM trade_data 
                    WHERE trade_date LIKE ? AND price = ? AND stake = ? AND pnl <> '0'
                    ORDER BY trade_date DESC"""
        for row in data.to_dict(orient='records'):
            
            c.execute(query, (row['openDateUtc']+'%', row['openLevel'], row['size'][1:]))
            rows = c.fetchall()
            if rows != []:
                #Update the record
                update_query = """
                                    UPDATE trade_data
                                    SET pnl = ?
                                    WHERE trade_date LIKE ? AND price = ? AND stake = ?
                                """
                print((row['instrumentName'],row['openDateUtc']+'%', row['openLevel'], row['size'][1:]))
                c.execute(update_query, (row['profitAndLoss'][1:],row['openDateUtc']+'%', row['openLevel'], row['size'][1:]))
                db.commit()
        return 'updates completed'

    def get_trades(self, db, c, epic, limit=200):
        query = """SELECT *
                    FROM trade_data 
                    WHERE epic = ?
                    ORDER BY trade_date DESC LIMIT ?"""
        c.execute(query, (epic, limit,))
        rows = c.fetchall()
        results = [dict(row) for row in rows]
        df = pd.DataFrame(results)
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        return df.sort_values(by="trade_date",ascending=False)

    def save_ig_trades_to_db(self, db, c, days:int=10):
        response = self.getPreviousTrades(days=days)
        for row in response.to_dict(orient='records'):
            result = self.upsert_trade_history(db, c, row)
            
        
    def upsert_trade_history(self, db, c, row):
        sql = """
        INSERT INTO trade_history (
            reference, date, dateUtc, openDateUtc, instrumentName,
            period, profitAndLoss, transactionType, openLevel,
            closeLevel, size, currency, cashTransaction
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(reference) DO UPDATE SET
            date = excluded.date,
            dateUtc = excluded.dateUtc,
            openDateUtc = excluded.openDateUtc,
            instrumentName = excluded.instrumentName,
            period = excluded.period,
            profitAndLoss = excluded.profitAndLoss,
            transactionType = excluded.transactionType,
            openLevel = excluded.openLevel,
            closeLevel = excluded.closeLevel,
            size = excluded.size,
            currency = excluded.currency,
            cashTransaction = excluded.cashTransaction;
        """
        c.execute(sql, (
            row["reference"],
            row["date"],
            row["dateUtc"],
            row["openDateUtc"],
            row["instrumentName"],
            row["period"],
            row["profitAndLoss"].replace("£", "").replace(",", ""),
            row["transactionType"],
            row["openLevel"].replace("£", "").replace(",", ""),
            row["closeLevel"].replace("£", "").replace(",", ""),
            row["size"].replace("£", "").replace(",", ""),
            row["currency"],
            row["cashTransaction"]
        ))
        db.commit()
        return row

            



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