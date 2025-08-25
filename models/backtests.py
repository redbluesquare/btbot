
class Backtests():

    def __init__(self):
        pass
    
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
                trades.append({'type': 'BUY', 'date': row['date'], 'price': entry_price})
            
            elif row['sell_signal'] and position_open:
                exit_price = row['close']
                trade_pnl = (exit_price - entry_price) * shares
                pnl += trade_pnl
                position_open = False
                trades.append({'type': 'SELL', 'date': row['date'], 'price': exit_price, 'pnl': trade_pnl})
            
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
                trades.append({'type': 'BUY', 'date': row['date'], 'price': entry_price})
            
            elif row['sell_signal'] and position_open:
                exit_price = row['close']
                trade_pnl = (exit_price - entry_price) * stake_per_point
                pnl += trade_pnl
                position_open = False
                trades.append({'type': 'SELL', 'date': row['date'], 'price': exit_price, 'pnl': trade_pnl})
            
            running_pnl.append(pnl)

        df['running_pnl'] = running_pnl
        return df, trades
