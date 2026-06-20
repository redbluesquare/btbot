# ftse_trader.py

import os
import time
import sqlite3
import logging
from datetime import datetime, timezone, time as dt_time

from dotenv import load_dotenv
from trading_ig import IGService

import models.user as user
import models.indicators as indicators
import models.prices as prices
import models.setup as setup
import models.trade_executor as trade_executor
import models.trades as trades
import app

load_dotenv()

# --- Logging setup ---

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [FTSE] %(levelname)s: %(message)s",
)
logger = logging.getLogger("ftse_trader")

# --- Constants specific to this service (FTSE) ---

EPIC = "IX.D.FTSE.DAILY.IP"
BUY_SIZE = "0.05"
SELL_SIZE = "0.05"
COOLDOWN_MINUTES = 30  # min time between trades on this epic

# ATR / stop logic
ATR_MIN_TRADE = 8.0          # ATR filter: skip trades if ATR < 8
ATR_STOP_MULTIPLIER = 2.0    # wider ATR stops
MIN_STOP_DISTANCE = 12.0     # minimum stop distance in points

# Time-of-day filter (UTC hours)
ACTIVE_WINDOWS = [
    (8, 10),   # 08:00–10:00
    (14, 17),  # 14:00–16:00
]

API_KEY = os.getenv("API_KEY")
USERNAME = os.getenv("IDENTIFIER")
USER_PW = os.getenv("PASSWORD")
ACC_TYPE = os.getenv("ACC_TYPE")

# --- Model instances ---

usr = user.User()
price = prices.Prices()
ind = indicators.Indicators()
trdes = trades.Trades()
te = trade_executor.TradeExecutor()

# --- DB setup (run once at startup) ---

setup.create_trades_table()
setup.create_trading_check_table()
setup.update_trades_table()


def last_trade_time(epic: str):
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


def in_active_window(ts) -> bool:
    """
    Time-of-day filter: only trade in the defined FTSE windows.
    ts is assumed UTC.
    """
    hour = ts.hour
    for start, end in ACTIVE_WINDOWS:
        if start <= hour < end:
            return True
    return False


def is_big_candle(row) -> bool:
    """
    Big candle filter: skip exhaustion candles.
    Here we define a 'big candle' as a range > 2 * ATR.
    """
    candle_range = row["high"] - row["low"]
    atr = row["atr"]
    if atr <= 0:
        return False
    return candle_range > 3.0 * atr


def get_position_age_bars(open_pos, last_bar_time, timeframe_minutes=5) -> int:
    """
    Approximate number of bars since entry using IG position created date.
    Assumes open_pos has 'createdDateUTC' or 'createdDate'.
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

    if last_bar_time.tzinfo is None:
        last_bar_time = last_bar_time.replace(tzinfo=timezone.utc)

    delta_minutes = (last_bar_time - created_dt).total_seconds() / 60.0
    return max(0, int(delta_minutes // timeframe_minutes))


def process_epic(ig_service, positions):
    """
    Core logic for FTSE epic only, with performance-based improvements.
    """
    # Check if there is an open position for this epic
    open_pos = None
    for p in positions:
        if p["epic"] == EPIC:
            open_pos = p
            break

    now_utc = datetime.now(timezone.utc)
    lt = last_trade_time(EPIC)

    # --- Load and prepare indicator data ---

    df = price.load_ohlc(EPIC, "5MINUTE")
    df = df.sort_values(by="date", ascending=True)

    # Slower MACD: 12,26,9
    df = ind.calculate_macd(df, 8, 21, 5)
    # MACD slope
    df["macd_slope"] = df["macd"].diff()

    # RSI, CCI, EMA20, ATR
    df = ind.calculate_rsi(df, 21)
    df = ind.calculate_cci(df, 90)
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df = ind.add_atr(df, 14)

    last = df.iloc[-1]

    # Time-of-day filter
    if not in_active_window(last["date"]):
        logger.debug("Outside active FTSE window, skipping.")
        return

    # ATR filter
    if last["atr"] < ATR_MIN_TRADE:
        logger.debug(f"ATR {last['atr']:.2f} < {ATR_MIN_TRADE}, skipping trade.")
        return

    # Big candle filter
    if is_big_candle(last):
        logger.debug("Big candle detected, skipping trade.")
        return

    # Trend filter: EMA20
    price_above_ema = last["close"] > last["ema20"]
    price_below_ema = last["close"] < last["ema20"]

    # MACD slope direction
    macd_slope_up = last["macd_slope"] > 0
    macd_slope_down = last["macd_slope"] < 0

    # RSI filters: avoid 50–60 band
    buy_signal = (
        last["bullish_crossover"]
        and macd_slope_up
        and price_above_ema
        and last["rsi"] > 55
    )

    sell_signal = (
        last["bearish_crossover"]
        and macd_slope_down
        and price_below_ema
        and last["rsi"] < 45
    )

    # --- No open position: look for entries ---

    if open_pos is None:
        can_trade = lt is None or (now_utc - lt).total_seconds() > COOLDOWN_MINUTES * 60

        if not can_trade:
            logger.debug("Cooldown active, no new trade.")
            return

        if not (buy_signal or sell_signal):
            logger.debug("No valid entry signal.")
            return

        atr = last["atr"]
        stop_distance = max(MIN_STOP_DISTANCE, ATR_STOP_MULTIPLIER * atr)

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

    # --- Open position exists: manage it ---

    df_recent = price.load_ohlc(EPIC, "5MINUTE", records=100)
    df_recent = df_recent.sort_values(by="date", ascending=True)
    df_recent = ind.add_atr(df_recent, 14)
    last_r = df_recent.iloc[-1]
    atr = last_r["atr"]

    entry = open_pos["level"]
    stop = open_pos["stopLevel"]
    current = last_r["close"]

    risk = abs(entry - stop)
    if risk < 1e-6:
        risk = ATR_STOP_MULTIPLIER * atr

    bars_since_entry = get_position_age_bars(open_pos, last_r["date"])

    if open_pos["direction"] == "BUY":
        r = (current - entry) / risk

        # Break-even after 15 bars (not 30)
        if bars_since_entry >= 15 and stop < entry:
            new_stop = entry

        # Move stop to BE at R >= 0.5 (FTSE rarely hits R=1 early)
        elif r >= 0.5 and stop < entry:
            new_stop = entry

        # Trail at R >= 1.5
        elif r >= 1.5:
            new_stop = current - 1.0 * atr

        else:
            new_stop = stop

        if new_stop > stop:
            logger.info(
                f"Updating BUY stop {EPIC}: old={stop:.2f}, new={new_stop:.2f}, "
                f"R={r:.2f}, bars={bars_since_entry}"
            )
            ig_service.update_open_position(
                limit_level=None,
                stop_level=new_stop,
                deal_id=open_pos["dealId"],
            )

    elif open_pos["direction"] == "SELL":
        r = (entry - current) / risk

        # Break-even after 15 bars
        if bars_since_entry >= 15 and stop > entry:
            new_stop = entry

        # Move stop to BE at R >= 0.5
        elif r >= 0.5 and stop > entry:
            new_stop = entry

        # Trail at R >= 1.5
        elif r >= 1.5:
            new_stop = current + 1.0 * atr

        else:
            new_stop = stop

        if new_stop < stop:
            logger.info(
                f"Updating SELL stop {EPIC}: old={stop:.2f}, new={new_stop:.2f}, "
                f"R={r:.2f}, bars={bars_since_entry}"
            )
            ig_service.update_open_position(
                limit_level=None,
                stop_level=new_stop,
                deal_id=open_pos["dealId"],
            )


def main_loop():
    ig_service = usr.login_ig(
        IGService,
        USERNAME,
        USER_PW,
        API_KEY,
        acc_type=ACC_TYPE,
    )
    ig_service.create_session()
    logger.info("FTSE trading service started.")

    while True:
        try:
            positions = ig_service.fetch_open_positions()
            pos_list = positions.to_dict(orient="records")

            process_epic(ig_service, pos_list)

            time.sleep(30)

            now = datetime.now().time()

            if dt_time(21, 1) <= now < dt_time(21, 3):
                logger.info("Running app.main() end-of-day task.")
                app.main()
                time.sleep(180)

            if dt_time(21, 12) <= now < dt_time(21, 14):
                #logger.info("Saving IG trades to DB.")
                #db = sqlite3.connect("streamed_prices.db")
                #c = db.cursor()
                #trdes.save_ig_trades_to_db(db, c, days=3)
                #db.close()
                time.sleep(60)

        except Exception as e:
            logger.exception(f"Error in FTSE service loop: {e}")
            time.sleep(10)


if __name__ == "__main__":
    main_loop()
