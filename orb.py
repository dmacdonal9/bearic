from datetime import datetime, timedelta
from ibstrat.ib_instance import ib
from ibstrat.market_data import get_current_mid_price, get_bag_prices
from ibstrat.dteutil import get_today_expiry
from ibstrat.options import find_options_by_target_strikes, find_option_by_target_delta
from ibstrat.orders import create_bag, submit_limit_order, adj_price_for_order
from ibstrat.trclass import get_trading_class_for_symbol
from ibstrat.adaptive import submit_adaptive_order
from ibstrat.chain import fetch_option_chain
from ibstrat.positions import check_positions
from ibstrat.ticksize import get_tick_size, adjust_to_tick_size
from ibstrat.pushover import send_notification
from zoneinfo import ZoneInfo
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
    - Two short puts at a delta defined by cfg.orb_params['short_put_delta']
    - One long put below the center puts by cfg.orb_params['lower_long_put_offset']
    - One long put above the center puts by cfg.orb_params['higher_long_put_offset']

    Accepts an already qualified contract instead of just a symbol.
    """
    logger.info(
        f"Entering submit_ic_combo with parameters: und_contract={und_contract}, current_price={current_price}, is_live={is_live}")

    # Check if the ORB combo is already open
    expiry = get_today_expiry()

    try:
        # Retrieve parameters for the fly
        orb_params = cfg.orb_ic_params[und_contract.symbol]
        quantity = orb_params['quantity']
        opt_exchange = orb_params['opt_exchange']
        sec_type = orb_params['sec_type']
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

        if cfg.pushover_alerts:
            send_notification("BEARORB opened")
        return trade

    except Exception as e:
        logger.exception("Error in submit_orb_combo")
        return None


def check_orb(contract, orb_seconds, orb_type):
    """
    Dynamically handles time zone for the contract and checks ORB breakout.
    Opening range is based on 9:30 AM Eastern, converted to contract's native time zone.
    """
    try:
        contract = ib.qualifyContracts(contract)[0]
        contract_details = ib.reqContractDetails(contract)[0]
        contract_tz = ZoneInfo(contract_details.timeZoneId)

        logger.info(f"Checking ORB for contract: {contract}, orb_seconds: {orb_seconds}, orb_type: {orb_type}")

        # Define 9:30 AM Eastern
        eastern = ZoneInfo("America/New_York")
        market_open_eastern = datetime.now(eastern).replace(hour=9, minute=30, second=0, microsecond=0)
        range_end_eastern = market_open_eastern + timedelta(seconds=orb_seconds)

        # Convert to contract's time zone
        range_end_local = range_end_eastern.astimezone(contract_tz)
        end_str = f"{range_end_local.strftime('%Y%m%d %H:%M:%S')} {contract_details.timeZoneId}"

        logger.debug(f"Market open (EST): {market_open_eastern}, range end (local): {range_end_local}, end_str: {end_str}")

        hist_data = ib.reqHistoricalData(
            contract,
            endDateTime=end_str,
            durationStr=f"{orb_seconds} S",
            barSizeSetting="1 min",
            whatToShow="TRADES",
            useRTH=True
        )

        if not hist_data:
            logger.error("No historical data received.")
            return False

        orb_high = max(bar.high for bar in hist_data)
        orb_low = min(bar.low for bar in hist_data)
        logger.debug(f"Opening range high: {orb_high}, Opening range low: {orb_low}")

        current_price = get_current_mid_price(contract, 2, 1, False)
        logger.debug(f"Current price: {current_price}")

        if (orb_type == "high" and current_price > orb_high) or (orb_type == "low" and current_price < orb_low):
            logger.info(f"ORB breakout detected: type={orb_type}, current_price={current_price}, orb_high={orb_high}, orb_low={orb_low}")
            return True

        logger.info("No ORB breakout detected.")
        return False

    except Exception:
        logger.exception("Error in check_orb")
        return False


def check_orb_for_date(contract, date_str, orb_seconds: int = 3600):
    """
    Determine and print the Opening Range (high and low) for a given date.
    Opening range is based on 9:30–10:30 AM Eastern, converted to the contract's native time zone.

    :param contract: IB contract object
    :param date_str: Date string in 'YYYYMMDD' format
    :param orb_seconds: Number of seconds for the opening range (default: 3600 = 1 hour)
    """
    try:
        contract_details = ib.reqContractDetails(contract)[0]
        contract_tz = ZoneInfo(contract_details.timeZoneId)

        logger.info(f"Checking ORB for contract: {contract}, date: {date_str}, orb_seconds: {orb_seconds}")
        eastern = ZoneInfo("America/New_York")

        # Define opening range in Eastern time
        market_open_eastern = datetime.strptime(date_str, '%Y%m%d').replace(
            hour=9, minute=30, second=0, microsecond=0, tzinfo=eastern)
        range_end_eastern = market_open_eastern + timedelta(seconds=orb_seconds)

        # Convert to contract's local time zone for IBKR
        range_end_local = range_end_eastern.astimezone(contract_tz)
        end_str = f"{range_end_local.strftime('%Y%m%d %H:%M:%S')} {contract_details.timeZoneId}"

        logger.debug(f"Market open (EST): {market_open_eastern}, range end (local): {range_end_local}, end_str: {end_str}")

        hist_data = ib.reqHistoricalData(
            contract,
            endDateTime=end_str,
            durationStr=f"{orb_seconds} S",
            barSizeSetting="1 min",
            whatToShow="TRADES",
            useRTH=True
        )

        if not hist_data:
            logger.error("No historical data received.")
            return

        orb_high = max(bar.high for bar in hist_data)
        orb_low = min(bar.low for bar in hist_data)

        logger.info(f"Opening Range for {date_str}: HIGH={orb_high}, LOW={orb_low}")
        print(f"Opening Range for {date_str}: HIGH={orb_high}, LOW={orb_low}")

    except Exception:
        logger.exception("Error in check_orb_for_date")