
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