
class TradeExecutor():
    def __init__(self):
        pass
        
    def open_trade(ig, epic, expiry='-1', direction='BUY', size='0.1', order_type='MARKET', currency_code='GBP'
               ,guaranteed_stop=True, force_open=True, limit_distance='-1', stop_distance=20):
        response = ig.create_open_position(
            epic=epic,
            expiry=expiry,
            direction=direction.upper(),
            size=size,
            order_type=order_type,
            currency_code=currency_code,
            guaranteed_stop=guaranteed_stop,
            force_open=force_open,
            limit_distance=limit_distance,
            stop_distance=stop_distance)