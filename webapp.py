from flask import Flask, render_template, jsonify
import sqlite3
import pandas as pd
import os
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
DB_FILE = "streamed_prices.db"
DB_PATH = os.getenv('DB_PATH')

def fetch_ohlc(limit=100):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""SELECT date, (bid_open+offer_open)/2 AS open, (bid_high+offer_high)/2 AS high
                            ,(bid_low+offer_low)/2 AS low, (bid_close+offer_close)/2 AS close 
                            FROM ohlc_data 
                            WHERE epic = ?
                            ORDER BY date DESC LIMIT ? """,
                            conn, params=('IX.D.DOW.DAILY.IP',limit,), parse_dates=["date"])
    conn.close()
    df = df.sort_values("date")
    records = df.to_dict(orient="records")
    return records

def fetch_trades(limit=200):
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    df = pd.read_sql_query(
        "SELECT epic, trade_date, trade_type, dealId, dealStatus, price, stake, macd, rsi, pnl "
        "FROM trade_data ORDER BY trade_date DESC LIMIT ?",
        conn, params=(limit,), parse_dates=["trade_date"]
    )
    conn.close()
    return df.sort_values("trade_date")

@app.route("/api/ohlc")
def api_ohlc():
    return jsonify(fetch_ohlc(500))

@app.route("/api/trades")
def api_trades():
    df = fetch_trades()
    # Convert for JSON: timestamps to ISO, numeric types preserved
    records = []
    for _, r in df.iterrows():
        records.append({
            "epic": r["epic"],
            "trade_date": r["trade_date"].isoformat(),
            "trade_type": r["trade_type"],
            "dealId": r["dealId"],
            "dealStatus": r["dealStatus"],
            "price": float(r["price"]),
            "stake": float(r["stake"]) if r["stake"] is not None else None,
            "macd": float(r["macd"]) if r["macd"] is not None else None,
            "rsi": float(r["rsi"]) if r["rsi"] is not None else None,
            "pnl": float(r["pnl"]) if r["pnl"] is not None else None
        })
    return jsonify(records)

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
