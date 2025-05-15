from ibstrat.ib_instance import connect_to_ib
from ibstrat.qualify import qualify_contract
from orb import is_orb_pcs_open, check_orb_for_date
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

connect_to_ib(
    '127.0.0.1',
    7500,
    1,
    2,)

und = qualify_contract("SPX","IND",exchange="CBOE",currency='USD')

check_orb_for_date(und,"20250414",3600)