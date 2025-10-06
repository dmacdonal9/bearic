symbol_list = ['SPX']

myStrategyTag = 'bearic'
pushover_alerts = True
check_min_vix = True
min_vix_pct = 0
min_move_down = -0.1
adaptive_priority= 'Normal'

#tradelog
trade_fill_timeout = 120
log_trade_fills = True
trade_log_sheet_id = "1y9hYBzSA4g8n92VkEgQp_JKu_F-XyI02RmbGjXin0hU"

sleep_after_order = 4

# IBKR Connection Parameters
ib_host = '127.0.0.1'
ib_port = 7496  # Port should be an integer
ib_clientid = 15  # Client ID should also be an integer

# Testing configuration
test_ib_host = '127.0.0.1'
test_ib_port = 7500  # Port for test TWS
test_ib_clientid = 15  # Client ID for test TWS

ic_params = {
    'SPX': {
        "quantity": 1,
        "max_open_trades": 1,
        "exchange": 'CBOE',
        "opt_exchange": 'CBOE',
        "trading_class": 'SPXW',
        "sec_type": 'IND',
        "mult": '100',
        "use_adaptive_on_combo": True,
        "short_put_delta": 40,
        "short_call_delta": 40,
        "long_put_offset": 35,
        "long_call_offset": 35
    },
    'ES': {
        "quantity": 1,
        "max_open_trades": 1,
        "exchange": 'CME',
        "opt_exchange": 'CME',
        "trading_class": '',
        "sec_type": 'FUT',
        "mult": '50',
        "use_adaptive_on_combo": False,
        "short_put_delta": 40,
        "short_call_delta": 40,
        "long_put_offset": 35,
        "long_call_offset": 35
    },
    'NQ': {
        "quantity": 1,
        "max_open_trades": 1,
        "exchange": 'CME',
        "opt_exchange": 'CME',
        "trading_class": '',
        "sec_type": 'FUT',
        "mult": '20',
        "use_adaptive_on_combo": False,
        "short_put_delta": 40,
        "short_call_delta": 40,
        "long_put_offset": 100,
        "long_call_offset": 100
    }
}