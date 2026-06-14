from trading_ig import IGService
from dotenv import load_dotenv
import os
import models.user as user
from datetime import datetime, timedelta, timezone
import pandas as pd

load_dotenv()

class Trades:

    def __init__(self):
        self.user = user.User()
        self.API_KEY = os.getenv('API_KEY')
        self.username = os.getenv('IDENTIFIER')
        self.user_pw = os.getenv('PASSWORD')
        self.acc_type = os.getenv('ACC_TYPE')

    # ---------------------------------------------------------
    # Date helpers
    # ---------------------------------------------------------

    def prev_day_range(self, tz=timezone.utc, days=10):
        now = datetime.now(tz)
        prev = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        next_day = prev + timedelta(days=days)
        return prev, next_day

    # ---------------------------------------------------------
    # IG API fetch
    # ---------------------------------------------------------

    def getPreviousTrades(self, days=10):
        ig_service = self.user.login_ig(
            IGService, self.username, self.user_pw, self.API_KEY, acc_type=self.acc_type
        )
        ig_service.create_session()

        from_dt, to_dt = self.prev_day_range(days=days)

        activities = ig_service.fetch_transaction_history(
            from_date=str(from_dt)[:10],
            to_date=str(to_dt)[:10],
            page_size=999
        )
        return activities

    # ---------------------------------------------------------
    # PnL updater (corrected)
    # ---------------------------------------------------------

    def update_pnl_by_dealid(self, db, c, data):
        """
        Update pnl in trade_data using IG's unique dealId (reference).
        This is the ONLY reliable way to match trades.
        """
        for row in data.to_dict(orient='records'):

            deal_id = row["reference"]  # IG uses reference as dealId for closed trades
            pnl = row["profitAndLoss"].replace("£", "").replace(",", "")

            # Update matching trade_data row
            c.execute("""
                UPDATE trade_data
                SET pnl = ?
                WHERE dealId = ?
            """, (pnl, deal_id))

        db.commit()
        return "PnL updated"

    # ---------------------------------------------------------
    # Trade history fetch
    # ---------------------------------------------------------

    def get_trades(self, db, c, epic, limit=200):
        query = """
            SELECT epic, datetime(trade_date), stake, pnl, datetime('now'),
                   CAST((JULIANDAY('now') - JULIANDAY(trade_date)) * 24 * 60 AS INT)
            FROM trade_data
            WHERE epic = ?
            ORDER BY trade_date DESC
            LIMIT ?
        """
        c.execute(query, (epic, limit))
        return c.fetchall()

    # ---------------------------------------------------------
    # Save IG trades to DB (history + pnl)
    # ---------------------------------------------------------

    def save_ig_trades_to_db(self, db, c, days: int = 10):
        """
        1. Pull IG transaction history
        2. Upsert into trade_history
        3. Update pnl in trade_data using dealId
        """
        response = self.getPreviousTrades(days=days)

        # Upsert trade history
        for row in response.to_dict(orient='records'):
            self.upsert_trade_history(db, c, row)

        # Update pnl in trade_data
        self.update_pnl_by_dealid(db, c, response)

    # ---------------------------------------------------------
    # Upsert trade history (unchanged except for cleaning)
    # ---------------------------------------------------------

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