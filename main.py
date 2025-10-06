import logging
from ibstrat.ib_instance import connect_to_ib
from ibstrat.qualify import qualify_contract, get_front_month_contract_date
from ibstrat.dteutil import get_today_expiry
from ibstrat.orders import adj_price_for_order
from ibstrat.market_data import get_current_mid_price, get_pct_move_from_open
from ibstrat.indicators import calc_vix_pct_move_from_open
from ibstrat.positions import load_positions
from ibstrat.tradecount import get_trade_counter
from condor import check_orb, submit_ic_combo
import cfg
import argparse
import sys
from math import isnan

# Configure global logging level
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Set custom log levels for specific modules
logging.getLogger("ib_async").setLevel(logging.CRITICAL)
logging.getLogger("indicators").setLevel(logging.ERROR)
logging.getLogger("ib_instance").setLevel(logging.ERROR)
logging.getLogger("dteutil").setLevel(logging.ERROR)
logging.getLogger("market_data").setLevel(logging.ERROR)
logging.getLogger("options").setLevel(logging.DEBUG)
logging.getLogger("chain").setLevel(logging.ERROR)
logging.getLogger("orders").setLevel(logging.DEBUG)
logging.getLogger("orb").setLevel(logging.DEBUG)
logging.getLogger("ibstrat.qualify").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Options trading script')
    parser.add_argument('-l', action='store_true', help='Enable live trading')
    parser.add_argument('-t', action='store_true', help='Use test TWS configuration')
    parser.add_argument('-o', action='store_true', help='Override checks for RSI, SMA, and ORB')
    args = parser.parse_args()

    live_orders = args.l
    use_test_tws = args.t
    override_checks = args.o

    logger.info(f"Live trading mode: {'Enabled' if live_orders else 'Disabled'}")
    logger.info(f"Test TWS mode: {'Enabled' if use_test_tws else 'Disabled'}")
    logger.info(f"Override checks mode: {'Enabled' if override_checks else 'Disabled'}")

    if use_test_tws:
        ib = connect_to_ib(cfg.test_ib_host, cfg.test_ib_port, cfg.test_ib_clientid, 2)
        logger.info("Connected to test TWS configuration.")
    else:
        ib = connect_to_ib(cfg.ib_host, cfg.ib_port, cfg.ib_clientid, 2)
        logger.info("Connected to live TWS configuration.")

    if cfg.check_min_vix:
        vix_move = calc_vix_pct_move_from_open()
        if vix_move is None:
            logger.error("Can't get VIX move, exiting...")
            sys.exit(-1)

        if vix_move < cfg.min_vix_pct:
            logger.info("VIX move is negative, not trading Bear IC today, exiting...")
            sys.exit(0)
        else:
            logger.info(f"VIX move is positive at {vix_move}%, proceeding...")

    load_positions()

    for symbol in cfg.symbol_list:
        try:
            params = cfg.ic_params.get(symbol)
            use_adaptive_on_combo = params['use_adaptive_on_combo']
            max_open_trades = params['max_open_trades']

            if not params:
                logger.warning(f"No ORB parameters found for symbol {symbol}. Skipping.")
                continue

            current_trade_count = get_trade_counter(symbol)
            if current_trade_count >= max_open_trades:
                logger.info(f"Skipping {symbol} due to {current_trade_count} open trades of max {max_open_trades}.")
                continue
            else:
                logger.info(f"We have {current_trade_count} open trades of max {max_open_trades} for {symbol}.")

            und_sec_type = params['sec_type']
            exchange = params['exchange']

            if und_sec_type == 'FUT':
                fut_date = get_front_month_contract_date(symbol, exchange, params["mult"], get_today_expiry(), 1)
            else:
                fut_date = ''

            und_contract = qualify_contract(symbol, und_sec_type, fut_date, exchange, currency="USD",
                                            tradingClass=params['trading_class'])
            current_price = get_current_mid_price(und_contract, 2, 1, False)

            if not override_checks:

                id_move = get_pct_move_from_open(und_contract)
                if id_move > cfg.min_move_down:
                    logger.info(f"Move down is not sufficient, aborting...")
                    continue
                else:
                    logger.info(f"Move down is sufficient, continuing...")

            trade = submit_ic_combo(und_contract, current_price, live_orders)
            if trade:
                logger.info(f"Successfully submitted ORB combo for {symbol} at price {current_price}")
            else:
                logger.error(f"Failed to submit ORB combo for {symbol} at price {current_price}.")

            if trade and live_orders and not use_adaptive_on_combo:
                logger.info(f"Adjusting limit price for order for {symbol}")
                adj_price_for_order(trade.order.orderId, 75,2)

        except Exception as e:
            logger.error(f"Error processing symbol {symbol}: {e}", exc_info=True)