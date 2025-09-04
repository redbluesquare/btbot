import sqlite3

def create_trades_table():
    db = sqlite3.connect('streamed_prices.db')
    c = db.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS trade_data (
            epic TEXT,
            trade_date TEXT,
            trade_type TEXT,
            price REAL,
            macd REAL,
            rsi REAL,
            stake REAL,
            pnl REAL,
            PRIMARY KEY (epic, date, trade_type)
        )
    ''')
    db.commit()
    db.close()

def create_trading_check_table():
    db = sqlite3.connect('streamed_prices.db')
    c = db.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS trading_position (
            epic TEXT,
            position REAL,
            check_date TEXT,
            PRIMARY KEY (epic)
        )
    ''')
    db.commit()
    db.close()