# dow_trader.py

import os
import time
import sqlite3
import logging
from datetime import datetime, timezone, time as dt_time

from dotenv import load_dotenv
from trading_ig import IGService

# Local modules
import models.user as user
import models.indicators as indicators
import models.prices as prices
import models.setup as setup
import models.trade_executor as trade_executor
import models.trades as trades
import app

# -------------------------------------------------------------------
# Setup
# -------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [DOW] %(levelname)s: %(message)s",
)
logger = logging.getLogger("dow_trader")

usr = user.User()
price = prices.Prices()
ind = indicators.Indicators()
trdes = trades.Trades()
te = trade_executor.TradeExecutor()

setup.create_trades_table()
setup.create_trading_check_table()
setup.update_trades_table()

API_KEY = os.getenv("API_KEY")
USERNAME = os.getenv("IDENTIFIER")
USER_PW = os.getenv("PASSWORD")
ACC_TYPE = os.getenv("ACC_TYPE")

EPIC = "IX.D.DOW.DAILY.IP"
BUY_SIZE = "0.01"
SELL_SIZE = "0.01"
COOLDOWN_MINUTES = 30

# Stop / volatility config
ATR_MIN_TRADE = 25.0          # skip low-volatility DOW
STOP_ATR_MULTIPLIER = 2.5     # stop = ATR * multiplier
MIN_STOP_DISTANCE = 80.0      # minimum stop distance in points

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def last_trade_time(epic: str):
    """Return last trade time for this epic as timezone-aware UTC."""
    db = sqlite3.connect("streamed_prices.db")
    c = db.cursor()
    c.execute(
        """
        SELECT trade_date
        FROM trade_data
        WHERE epic = ?
        ORDER BY datetime(trade_date) DESC
        LIMIT 1
    """,
        (epic,),
    )
    row = c.fetchone()
    db.close()

    if not row:
        return None

    return datetime.fromisoformat(row[0]).replace(tzinfo=timezone.utc)


def in_us_session(ts) -> bool:
    """
    DOW trades only in US session:
    13:30–17:00 UTC (approx UK time in your setup).a
    """
    hour = ts.hour
    minute = ts.minute
    return ((hour == 8 and minute >= 30) or (9 <= hour < 18))


def bars_since_entry(open_pos, last_timestamp, timeframe_minutes=5) -> int:
    """
    Approximate number of bars since entry using IG position created date.
    """
    created_str = (
        open_pos.get("createdDateUTC")
        or open_pos.get("createdDate")
        or open_pos.get("created_date")
    )
    if not created_str:
        return 0

    try:
        created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=timezone.utc)
    except Exception:
        return 0

    if last_timestamp.tzinfo is None:
        last_timestamp = last_timestamp.replace(tzinfo=timezone.utc)

    delta_minutes = (last_timestamp - created_dt).total_seconds() / 60.0
    return max(0, int(delta_minutes // timeframe_minutes))


# -------------------------------------------------------------------
# Main trading logic
# -------------------------------------------------------------------

def trade_epic():
    ig_service = usr.login_ig(
        IGService, USERNAME, USER_PW, API_KEY, acc_type=ACC_TYPE
    )
    ig_service.create_session()

    positions = ig_service.fetch_open_positions()
    pos_list = positions.to_dict(orient="records")

    open_pos = next((p for p in pos_list if p["epic"] == EPIC), None)

    now_utc = datetime.now(timezone.utc)
    lt = last_trade_time(EPIC)

    # Load indicators
    df = price.load_ohlc(EPIC, "5MINUTE")
    df = df.sort_values(by="date")
    df = ind.calculate_macd(df, 8, 21, 5)
    df = ind.calculate_rsi(df, 21)
    df = ind.calculate_cci(df, 90)
    df["macd_slope"] = df["macd"].diff()
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df = ind.add_atr(df, 14)

    last = df.iloc[-1]

    # Time-of-day filter
    if not in_us_session(last["date"]):
        logger.debug("Outside US session, skipping DOW.")
        return

    # ATR filter
    if last["atr"] < ATR_MIN_TRADE:
        logger.debug(f"DOW ATR {last['atr']:.2f} < {ATR_MIN_TRADE}, skipping.")
        return

    # Big candle / momentum filter
    candle_range = last["high"] - last["low"]
    if candle_range <= 0.8 * last["atr"]:
        logger.debug("DOW candle not strong enough, skipping.")
        return

    # Signals
    buy_signal = (
        last["bullish_crossover"]
        and last["macd_slope"] > 0
        and last["close"] > last["ema20"]
        and last["rsi"] > 55
    )

    sell_signal = (
        last["bearish_crossover"]
        and last["macd_slope"] < 0
        and last["close"] < last["ema20"]
        and last["rsi"] < 45
    )

    # ---------------------------------------------------------
    # ENTRY LOGIC
    # ---------------------------------------------------------
    if open_pos is None:
        can_trade = lt is None or (now_utc - lt).total_seconds() > COOLDOWN_MINUTES * 60

        if not can_trade:
            logger.debug("Cooldown active, no new DOW trade.")
            return

        if not (buy_signal or sell_signal):
            logger.debug("No valid DOW entry signal.")
            return

        atr = last["atr"]
        stop_distance = max(MIN_STOP_DISTANCE, STOP_ATR_MULTIPLIER * atr)

        direction = "BUY" if buy_signal else "SELL"
        size = BUY_SIZE if direction == "BUY" else SELL_SIZE

        logger.info(
            f"Opening {direction} on {EPIC} | ATR={atr:.2f}, stop={stop_distance:.2f}, "
            f"RSI={last['rsi']:.2f}, MACD_slope={last['macd_slope']:.5f}"
        )

        trade = te.open_trade(
            ig_service,
            EPIC,
            expiry="DFB",
            direction=direction,
            size=size,
            order_type="MARKET",
            currency_code="GBP",
            guaranteed_stop=False,
            force_open=True,
            stop_distance=stop_distance,
        )

        db = sqlite3.connect("streamed_prices.db")
        c = db.cursor()
        c.execute(
            """
            INSERT INTO trade_data
            (epic, trade_date, trade_type, dealId, dealStatus, price, stake, macd, rsi, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                trade["epic"],
                trade["date"],
                trade["direction"],
                trade["dealId"],
                trade["dealStatus"],
                trade["level"],
                trade["size"],
                last["macd"],
                last["rsi"],
                0,
            ),
        )
        db.commit()
        db.close()

        return

    # ---------------------------------------------------------
    # EXIT / STOP MANAGEMENT
    # ---------------------------------------------------------
    df_recent = price.load_ohlc(EPIC, "5MINUTE", records=100)
    df_recent = df_recent.sort_values(by="date")
    df_recent = ind.add_atr(df_recent, 14)

    last_r = df_recent.iloc[-1]
    atr = last_r["atr"]

    entry = open_pos["level"]
    stop = open_pos["stopLevel"]
    current = last_r["close"]

    risk = abs(entry - stop)
    if risk < 1e-6:
        risk = STOP_ATR_MULTIPLIER * atr

    bars = bars_since_entry(open_pos, last_r["date"])

    # Break-even after 10 bars
    new_stop = stop
    if bars >= 10:
        if open_pos["direction"] == "BUY" and stop < entry:
            new_stop = entry
        elif open_pos["direction"] == "SELL" and stop > entry:
            new_stop = entry

    # Hard exit after 20 bars
    if bars >= 20:
        logger.info(
            f"Closing DOW position due to time limit: bars={bars}, entry={entry:.2f}, current={current:.2f}"
        )
        ig_service.close_open_position(open_pos["dealId"])
        return

    # BUY POSITION MANAGEMENT
    if open_pos["direction"] == "BUY":
        r = (current - entry) / risk

        if r >= 1.0 and stop < entry:
            new_stop = max(new_stop, current - 1.5 * atr)
        elif r >= 2.0:
            new_stop = max(new_stop, current - 1.5 * atr)

        if new_stop > stop:
            logger.info(
                f"Updating BUY stop {EPIC}: old={stop:.2f}, new={new_stop:.2f}, "
                f"R={r:.2f}, bars={bars}"
            )
            ig_service.update_open_position(
                limit_level=None, stop_level=new_stop, deal_id=open_pos["dealId"]
            )

    # SELL POSITION MANAGEMENT
    elif open_pos["direction"] == "SELL":
        r = (entry - current) / risk

        if r >= 1.0 and stop > entry:
            new_stop = min(new_stop, current + 1.5 * atr)
        elif r >= 2.0:
            new_stop = min(new_stop, current + 1.5 * atr)

        if new_stop < stop:
            logger.info(
                f"Updating SELL stop {EPIC}: old={stop:.2f}, new={new_stop:.2f}, "
                f"R={r:.2f}, bars={bars}"
            )
            ig_service.update_open_position(
                limit_level=None, stop_level=new_stop, deal_id=open_pos["dealId"]
            )

    # ---------------------------------------------------------
    # NIGHTLY TASKS
    # ---------------------------------------------------------
    now = datetime.now().time()

    if dt_time(21, 1) <= now < dt_time(21, 3):
        #logger.info("Running app.main() end-of-day task.")
        #app.main()
        time.sleep(180)

    if dt_time(23, 11) <= now < dt_time(23, 13):
        logger.info("Saving IG trades to DB.")
        db = sqlite3.connect("streamed_prices.db")
        c = db.cursor()
        trdes.save_ig_trades_to_db(db, c, days=5)
        db.close()
        time.sleep(60)


# -------------------------------------------------------------------
# Main loop
# -------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("DOW trading service started.")
    while True:
        try:
            trade_epic()
            time.sleep(30)
        except Exception as e:
            logger.exception(f"Error in DOW service loop: {e}")
            time.sleep(10)
