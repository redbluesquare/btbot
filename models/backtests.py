import pandas as pd
import matplotlib.pyplot as plt
import models.indicators as indicators
import models.prices as prices

class Backtests():

    def __init__(self):
        self.ind = indicators.Indicators()
        self.price = prices.Prices()
        pass
    
    def backtest(self, epic, scale):
        #filename = 'media\/output\/gold_hour_2'
        # 📂 Load the CSV file
        #df = pd.read_csv(filename+'.csv', parse_dates=['date'])
        # 📁 load the db
        df = self.price.load_ohlc(epic, scale)
        #cci = self.ind.calculate_cci(df)
        df = self.ind.calculate_macd(df)
        df = self.ind.calculate_rsi(df)
        df = self.ind.calculate_ratcheting_trailing_stop(df, 6, 8)
        df = self.ind.generate_signals(df, 2)

        #df, trades = self.backtest_macd_rsi_buy_sell(df, shares=10)
        df, trades = self.backtest_spreadbet(df, stake_per_point=1)

        # View trades
        for t in trades:
            print(t)

        plt.figure(figsize=(12,6))
        plt.plot(df['date'], df['running_pnl'], label='Cumulative PnL', color='green')
        plt.title('Backtest: Cumulative Profit/Loss '+epic)
        plt.xlabel('Date')
        plt.ylabel('PnL (£)')
        plt.legend()
        plt.grid(True)
        plt.show()

    def backtest_macd_rsi_buy_sell(self, df, shares=10):
        trades = []
        position_open = False
        entry_price = 0
        pnl = 0
        running_pnl = []
        for i, row in df.iterrows():
            if row['buy_signal'] and not position_open:
                entry_price = row['close']
                position_open = True
                trades.append({'epic':row['epic'],'type': 'BUY', 'date': row['date'], 'price': entry_price})
            
            elif row['sell_signal'] and position_open:
                exit_price = row['close']
                trade_pnl = (exit_price - entry_price) * shares
                pnl += trade_pnl
                position_open = False
                trades.append({'epic':row['epic'],'type': 'SELL', 'date': row['date'], 'price': exit_price, 'pnl': trade_pnl})
            
            running_pnl.append(pnl)

        df['running_pnl'] = running_pnl
        return df, trades
    
    def backtest_spreadbet(self, df, stake_per_point=0.10):
        trades = []
        position_open = False
        entry_price = 0
        pnl = 0
        running_pnl = []

        for i, row in df.iterrows():
            if row['buy_signal'] and not position_open:
                entry_price = row['close']
                position_open = True
                trades.append({'epic':row['epic'],'type': 'BUY', 'date': row['date'], 'price': entry_price,'macd':row['macd']})
            elif row['sell_signal'] and position_open:
                exit_price = row['close']
                trade_pnl = (exit_price - entry_price) * stake_per_point
                pnl += trade_pnl
                position_open = False
                trades.append({'epic':row['epic'],'type': 'SELL', 'date': row['date'], 'price': exit_price,'macd':row['macd'], 'pnl': trade_pnl})
            running_pnl.append(pnl)
        df['running_pnl'] = running_pnl
        return df, trades
