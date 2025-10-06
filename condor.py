from datetime import datetime, timedelta
from ibstrat.ib_instance import ib
from ibstrat.market_data import get_current_mid_price, get_bag_prices
from ibstrat.dteutil import get_today_expiry
from ibstrat.options import find_options_by_target_strikes, find_option_by_target_delta
from ibstrat.orders import create_bag, submit_limit_order, adj_price_for_order
from ibstrat.tradelog import log_trade_details
from ibstrat.trclass import get_trading_class_for_symbol
from ibstrat.adaptive import submit_adaptive_order
from ibstrat.chain import fetch_option_chain
from ibstrat.positions import check_positions
from ibstrat.ticksize import get_tick_size, adjust_to_tick_size
from ibstrat.pushover import send_notification
from zoneinfo import ZoneInfo
from ibstrat.tradecount import *
from math import isnan
import logging
import cfg

logger = logging.getLogger(__name__)

PUT = 'P'
CALL = 'C'


from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

def submit_ic_combo(und_contract, current_price: float, is_live: bool = False):
    """
    Submit a 4-leg combo with:
    - Two short puts at a delta defined by cfg.params['short_put_delta']
    - One long put below the center puts by cfg.params['lower_long_put_offset']
    - One long put above the center puts by cfg.params['higher_long_put_offset']

    Accepts an already qualified contract instead of just a symbol.
    """
    logger.info(
        f"Entering submit_ic_combo with parameters: und_contract={und_contract}, current_price={current_price}, is_live={is_live}")

    # Check if the ORB combo is already open
    expiry = get_today_expiry()

    try:
        # Retrieve parameters for the fly
        orb_params = cfg.ic_params[und_contract.symbol]
        quantity = orb_params['quantity']
        opt_exchange = orb_params['opt_exchange']
        use_adaptive_on_combo = orb_params['use_adaptive_on_combo']
        tr_class = get_trading_class_for_symbol(und_contract.symbol)
        short_put_delta = orb_params['short_put_delta']
        short_call_delta = orb_params['short_call_delta']
        long_put_offset = orb_params['long_put_offset']
        long_call_offset = orb_params['long_call_offset']
        logger.debug(f"ORB ic params retrieved: {orb_params}")

        tickers = fetch_option_chain(
            my_contract=und_contract,
            opt_exchange=opt_exchange,
            my_expiry=expiry,
            last_price=current_price,
            trading_class=tr_class
        )

        short_put = find_option_by_target_delta(
            tickers=tickers,
            right=PUT,
            target_delta=short_put_delta,
            trading_class=tr_class
        ).contract

        short_call = find_option_by_target_delta(
            tickers=tickers,
            right=CALL,
            target_delta=short_call_delta,
            trading_class=tr_class
        ).contract

        target_strikes = [
            (CALL, short_call.strike + long_call_offset),
            (PUT, short_put.strike - long_put_offset)
        ]
        logger.debug(f"Target strikes for orb IC: {target_strikes}")

        long_options = find_options_by_target_strikes(und_contract,opt_exchange,expiry,target_strikes,tr_class)
        if not long_options or len(long_options) != 2:
            logger.error(f"Failed to find all two IC long legs. Expected 2, got {len(long_options) if long_options else 0}")
            return None
        logger.debug(f"Retrieved long legs for IC: {long_options}")
        long_call, long_put = long_options[0], long_options[1]

        # Prepare position check list
        pos_check_list = [
            {'strike': short_call.strike, 'right': CALL, 'expiry': expiry, 'position_type': 'long'},
            {'strike': short_put.strike, 'right': PUT, 'expiry': expiry, 'position_type': 'long'},
            {'strike': long_call.strike, 'right': 'C', 'expiry': expiry, 'position_type': 'short'},
            {'strike': long_put.strike, 'right': 'C', 'expiry': expiry, 'position_type': 'short'},
        ]
        logger.debug(f"Position check list: {pos_check_list}")

        # Check existing positions
        existing_pos_open = check_positions(und_contract.symbol, pos_check_list)
        if existing_pos_open:
            logger.warning(f"We have potential collisions on strikes, aborting trade")
            send_notification("BEARORB aborted due to strike collision")
            return None

        # Construct the combo legs
        ic_legs = [ short_call,  short_put, long_call, long_put ]
        leg_actions = ['BUY', 'BUY','SELL','SELL'] # flip later on action sell
        ratios = [1, 1, 1,1]
        logger.debug(f"Constructed legs: {ic_legs}, actions: {leg_actions}, ratios: {ratios}")

        # Create a bag contract
        bag_contract = create_bag(und_contract, ic_legs, leg_actions, ratios)
        bag_contract.exchange = 'SMART'
        logger.debug(f"Created bag contract: {bag_contract}")

        bid,mid,ask = get_bag_prices(bag_contract)
        if isnan(bid) or isnan(mid) or isnan(ask):
            logger.error("Invalid combo prices.")
            return None

        # Adjust to tick size
        min_tick = get_tick_size(und_contract.symbol, abs(mid))
        limit_price = adjust_to_tick_size(abs(mid), min_tick)
        logger.info(f"Adjusted limit price from {mid} to {limit_price} (Tick size was {min_tick})")

        if not use_adaptive_on_combo:
            trade = submit_limit_order(order_contract=bag_contract,
                                       limit_price=limit_price,
                                       action='SELL',
                                       is_live=is_live,
                                       quantity=quantity,
                                       strategy_tag=cfg.myStrategyTag)
            ib.sleep(cfg.sleep_after_order)
            if trade and is_live:
                adj_price_for_order(trade.order.orderId,40,2)
        else:
            # Submit the order
            trade = submit_adaptive_order(
                order_contract=bag_contract,
                order_type='MKT',  # Market order
                action='SELL',  # Direction
                is_live=is_live,
                quantity=quantity,
                order_ref=cfg.myStrategyTag,
                adaptive_priority=cfg.adaptive_priority
            )
            ib.sleep(cfg.sleep_after_order)
        if trade:
            logger.info(f"Order submitted: {trade.order.orderId}")
        else:
            logger.error("Order submission failed.")

        new_trade_count = increment_trade_counter(und_contract.symbol)
        logger.info(f"{und_contract.symbol} trade #{new_trade_count} opened.")
        if cfg.pushover_alerts:
            send_notification(f"Opened bearorb, trade #{new_trade_count}")

        if trade and is_live and cfg.log_trade_fills:
            logger.info("Calling log_trade_details()")
            log_trade_details(ib=ib,
                              und_contract=und_contract,
                              trade_contract=bag_contract,
                              mid_price=mid,
                              trade=trade,
                              timeout=cfg.trade_fill_timeout,
                              sheet_id=cfg.trade_log_sheet_id,
                              strategy_tag=cfg.myStrategyTag)

        return trade

    except Exception as e:
        logger.exception("Error in submit_orb_combo")
        return None