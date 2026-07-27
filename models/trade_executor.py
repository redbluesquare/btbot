
class TradeExecutor():
    def __init__(self):
        pass
        
    def open_trade(self, ig, epic, expiry='DFB', direction='BUY', size='1', order_type='MARKET', currency_code='GBP'
               ,guaranteed_stop=True, force_open=False, stop_distance=20):
        response = ig.create_open_position(
            epic=epic,
            expiry=expiry,
            direction=direction.upper(),
            size=size, 
            order_type=order_type,
            currency_code=currency_code,
            guaranteed_stop=guaranteed_stop,
            force_open=force_open,
            stop_distance=stop_distance,
            level=None,
            limit_distance=None,
            limit_level=None,
            quote_id=None,
            stop_level=None,
            trailing_stop=False,
            trailing_stop_increment=None)
        return response

    def fixed_trailing_stop(self, current_stop, current_price, direction, trail_distance):
        """
        Fixed trailing stop that NEVER moves the stop backwards.
        
        BUY  → stop trails below price, but never decreases
        SELL → stop trails above price, but never increases
        """
        if direction == "BUY":
            # Proposed new stop
            proposed = current_price - trail_distance
            # Only move stop UP (never down)
            if proposed > current_stop:
                return proposed
            else:
                return current_stop
        elif direction == "SELL":
            proposed = current_price + trail_distance
            # Only move stop DOWN (never up)
            if proposed < current_stop:
                return proposed
            else:
                return current_stop
        else:
            raise ValueError("Direction must be 'BUY' or 'SELL'")
