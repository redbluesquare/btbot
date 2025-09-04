import pandas as pd
import numpy as np

class Indicators():

    def __init__(self):
        pass

    # Manual MAD calculation
    def mad(self, x):
        return np.mean(np.abs(x - np.mean(x)))

    def calculate_cci(self, df, period=90):
        tp = (df['high'] + df['low'] + df['close']) / 3
        sma = tp.rolling(window=period).mean()
        #mad = tp.rolling(window=period).apply(lambda x: pd.Series(x).mad(skipna=True))
        mad = tp.rolling(window=period).apply(self.mad, raw=True)
        cci = (tp - sma) / (0.015 * mad)
        df['CCI'] = cci
        return df

    def calculate_macd(self, df, short=5, long=35, signal=5):
        close = df['close']
        ema_short = close.ewm(span=short, adjust=False).mean()
        ema_long = close.ewm(span=long, adjust=False).mean()
        macd_line = ema_short - ema_long
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        df['macd'] = macd_line
        df['signal'] = signal_line
        df['histogram'] = histogram
        df['macd_prev'] = df['macd'].shift(1)
        df['signal_prev'] = df['signal'].shift(1)
        df['bullish_crossover'] = (df['macd_prev'] < df['signal_prev']) & (df['macd'] > df['signal'])
        df['bc'] = np.where(df['bullish_crossover'], df['macd'], np.nan)
        return df

    def calculate_rsi(self, df, period=21):
        close = df['close']
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        df['rsi'] = rsi
        # RSI crossing above 50
        df['rsi_prev'] = df['rsi'].shift(1)
        df['rsi_cross_above_50'] = (df['rsi_prev'] < 50) & (df['rsi'] > 50)
        df['rsi_c'] = np.where(df['rsi_cross_above_50'], df['rsi'], np.nan)
        return df
    
    def find_combined_signals(self, df):
        # Combined condition
        df['combined_signal'] = df['bullish_crossover'] & df['rsi_cross_above_50']
        # Return price at those points
        return df[df['combined_signal']][['date', 'close', 'macd', 'rsi']]
    
    def show_cci(self, plt, df):
        plt.figure(figsize=(12,6))
        plt.plot(df['CCI'], label='CCI (90)')
        plt.axhline(100, color='green', linestyle='--')
        plt.axhline(-100, color='red', linestyle='--')
        plt.title('Commodity Channel Index (CCI) - 90 Period')
        plt.legend()
        plt.show()

    def show_macd(self, plt, df):
        plt.figure(figsize=(12,6))
        plt.plot(df['macd'], label='MACD Line')
        plt.plot(df['signal'], label='Signal Line')
        plt.bar(df.index, df['histogram'], label='Histogram', color='gray')
        # Plot bullish crossover points
        plt.scatter(df.index, df['bc'], color="green", label="Bullish Crossover", zorder=5)
        plt.scatter(df.index, df['rsi_c'], color="red", label="RSI above 50", zorder=5)
        plt.legend()
        plt.title('MACD (5, 35, 5)')
        plt.show()

    def show_rsi(self, plt, df):
        plt.figure(figsize=(12,6))
        plt.plot(df['rsi'], label='RSI (21)', color='blue')
        plt.scatter(df.index, df['rsi_c'], color="red", label="RSI above 50", zorder=5)
        plt.axhline(50, color='grey', linestyle='--')
        plt.title('RSI - 21 Period')
        plt.xlabel('Date')
        plt.ylabel('RSI')
        plt.legend()
        plt.show()
    
    def calculate_ratcheting_trailing_stop(self, df, window=0, buffer=10):
        # Calculate raw trailing stop based on lowest of last 10 OCHL bars
        df['min_price_10'] = df[['open', 'high', 'low', 'close']].rolling(window=window).min().min(axis=1)
        df['raw_trailing_stop'] = df['min_price_10'] - buffer
        # Initialize ratcheting stop
        ratcheting_stop = []
        current_stop = np.nan
        for i in range(len(df)):
            raw_stop = df['raw_trailing_stop'].iloc[i]
            if np.isnan(raw_stop):
                ratcheting_stop.append(np.nan)
                continue
            if np.isnan(current_stop):
                current_stop = raw_stop
            else:
                current_stop = max(current_stop, raw_stop)
            ratcheting_stop.append(current_stop)
        df['trailing_stop'] = ratcheting_stop
        df['sell_signal_trailing'] = df['close'] < df['trailing_stop']
        return df
    
    def is_within_trading_hours(self, timestamp, start_hour=9, end_hour=19):
        return start_hour <= timestamp.hour < end_hour

    def calculate_trailing_stop(self, df, window=10, buffer=4):
        df['min_price_10'] = df[['open', 'high', 'low', 'close']].rolling(window=window).min().min(axis=1)
        df['trailing_stop'] = df['min_price_10'] - buffer
        df['sell_signal_trailing'] = df['low'] < df['trailing_stop']
        return df

    def generate_signals(self, df, strategy = 1):
        #df = self.calculate_macd(df)
        #df = self.calculate_rsi(df)
        df['buy_signal'] = False
        df['sell_signal'] = False
        holding = False  # Tracks whether a position is open
        i = 0
        while i < len(df) - 3:
            if not holding:
                # Look ahead 3 days for buy condition
                window = df.iloc[i:i+3]
                for j in window.index:
                    ts = df.at[j, 'date']
                    if self.is_within_trading_hours(ts):
                        buy_condition = (window['macd'] > window['signal']) & (window['rsi'] > 50)
                        if buy_condition.any():
                            buy_index = window[buy_condition].index[0]
                            df.at[buy_index, 'buy_signal'] = True
                            holding = True
                            i = df.index.get_loc(buy_index) + 1  # Move to next index after buy
                            continue
            if holding:
                if strategy == 1:
                    # Check for sell condition
                    if df.at[df.index[i], 'rsi'] < 50 or df.at[df.index[i], 'macd'] < df.at[df.index[i], 'signal']:
                        df.at[df.index[i], 'sell_signal'] = True
                        holding = False
                if strategy == 2:
                    if df.at[df.index[i], 'sell_signal_trailing']:
                        df.at[df.index[i], 'sell_signal'] = True
                        holding = False
            i += 1
        return df
