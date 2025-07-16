symbol_list = ['SPX']

myStrategyTag = 'bearorb'
pushover_alerts = True
check_min_vix = True
max_vix_pct = 0 #
adaptive_priority= 'Normal'

sleep_after_order = 4

# IBKR Connection Parameters
ib_host = '127.0.0.1'
ib_port = 7496  # Port should be an integer
ib_clientid = 10  # Client ID should also be an integer

# Testing configuration
test_ib_host = '127.0.0.1'
test_ib_port = 7500  # Port for test TWS
test_ib_clientid = 10  # Client ID for test TWS

orb_ic_params = {
    'SPX': {
        "quantity": 1,
        "exchange": 'CBOE',
        "opt_exchange": 'CBOE',
        "trading_class": 'SPXW',
        "sec_type": 'IND',
        "mult": '100',
        "use_adaptive_on_combo": True,
        "short_put_delta": 50,
        "short_call_delta": 50,
        "long_put_offset": 50,
        "long_call_offset": 50
    },
    'ES': {
        "quantity": 1,
        "exchange": 'CME',
        "opt_exchange": 'CME',
        "trading_class": '',
        "sec_type": 'FUT',
        "mult": '50',
        "use_adaptive_on_combo": False,
        "short_put_delta": 50,
        "short_call_delta": 50,
        "long_put_offset": 50,
        "long_call_offset": 50
    },
    'NQ': {
        "quantity": 1,
        "exchange": 'CME',
        "opt_exchange": 'CME',
        "trading_class": '',
        "sec_type": 'FUT',
        "mult": '20',
        "use_adaptive_on_combo": False,
        "short_put_delta": 50,
        "short_call_delta": 50,
        "long_put_offset": 150,
        "long_call_offset": 150
    }
}