from flask import Flask, request, g, jsonify, make_response, render_template
from flask_restful import Resource, Api
from flask_cors import CORS
import models.prices as prices
import models.trades as trades
import sqlite3
import pandas as pd
import os
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
CORS(app)
api = Api(app)

DB_PATH = os.getenv('DB_PATH')

class Db_connect():
    def __init__(self):
        super().__init__()
        
    def get_db(self):
        
        db = getattr(g, '_database', None)
        if db is None:
            db = g._database = sqlite3.Connection(database=DB_PATH)
            db.row_factory = sqlite3.Row
        return db
    
    @app.teardown_appcontext
    def close_connection(exception):
        db = getattr(g, '_database', None)
        if db is not None:
            db.close()

class igTrades(Resource):
    def delete(self):
        pass

    def get(self, days = 10):
        db = Db_connect().get_db()
        c = db.cursor()
        t = trades.Trades()
        results = t.getPreviousTrades(days=days)
        result = t.getTradeByOpenDatePrice(db, c, results)
        return result

class TradePrices(Resource):
    def delete(self, epic):
        pass

    def get(self, epic = None, scale = None):
        db = Db_connect().get_db()
        c = db.cursor()
        p = prices.Prices()
        if epic == None:
            return []
        results = p.get_ohlc(db=db, c=c, epic=epic, scale=scale, records=1000).fillna(0)
        return jsonify(results.to_dict(orient='records'))

class Trades(Resource):
    def delete(self, epic):
        pass

    def get(self, epic = None):
        db = Db_connect().get_db()
        c = db.cursor()
        t = trades.Trades()
        if epic == None:
            return []
        results = t.get_trades(db=db, c=c, epic=epic, limit=1000).fillna(0)
        return jsonify(results.to_dict(orient='records'))

@app.route("/")
def index():
    return render_template("index.html")

api.add_resource(igTrades, '/api/ig-trades/','/api/ig-trades/<int:days>')
api.add_resource(TradePrices, '/api/prices/', '/api/prices/<string:epic>/<string:scale>')
api.add_resource(Trades, '/api/trades/', '/api/trades/<string:epic>')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
