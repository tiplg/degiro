# IMPORTATIONS
import json
from datetime import datetime, date, timezone
import logging
import degiro_connector.core.helpers.pb_handler as pb_handler
import exchange_calendars as xcals

from degiro_connector.trading.api import API as TradingAPI
from degiro_connector.trading.models.trading_pb2 import Credentials, Update, Order, TransactionsHistory

#SETUP checks
fee_check = False
muney_check = False

# SETUP CONFIG DICT
with open("config/config.json") as config_file:
    config_dict = json.load(config_file)

# SETUP CREDENTIALS
int_account = config_dict.get("degiro_int_account")
username = config_dict.get("degiro_username")
password = config_dict.get("degiro_password")

credentials = Credentials(
    int_account=int_account,
    username=username,
    password=password,
)

# SETUP TRADING API
trading_api = TradingAPI(credentials=credentials)

#check trading hours calander
xams = xcals.get_calendar("XAMS")
tradingHours_check = xams.is_trading_minute(datetime.now(timezone.utc))

# CONNECT trading api
trading_api.connect()

# SETUP PORTFOLIO and pending orders REQUEST
request_list = Update.RequestList()
request_list.values.extend(
    [
        Update.Request(option=Update.Option.PORTFOLIO, last_updated=0),
        Update.Request(option=Update.Option.ORDERS, last_updated=0),
    ]
)

# FETCH PORTFOLIO DATA
update = trading_api.get_update(request_list=request_list, raw=False)
update_dict = pb_handler.message_to_dict(message=update)

vwrl_dict = next(item for item in update_dict["portfolio"]["values"] if item["id"] == "4586985")
flatex_eur_dict = next(item for item in update_dict["portfolio"]["values"] if item["id"] == "FLATEX_EUR")

#Check pending orders
total_orders_value = 0.5
orders_check = True

if "orders" in update_dict:
    for order in update_dict["orders"]["values"]:
        total_orders_value += order["total_order_value"]
        if order["product_id"] == 4586985:
            orders_check = False

# SETUP HISTORY REQUEST
today = date.today()
from_date = TransactionsHistory.Request.Date(
    year=today.year,
    month=today.month,
    day=1,
)
to_date = TransactionsHistory.Request.Date(
    year=today.year,
    month=today.month,
    day=today.day,
)
request = TransactionsHistory.Request(
    from_date=from_date,
    to_date=to_date,
)

# FETCH DATA
transactions_history = trading_api.get_transactions_history(
    request=request,
    raw=False,
)

#check if traded this month
history_check = True
for transaction in transactions_history.values:
    if transaction["productId"] == 4586985:
        history_check = False


#Setup order
buy_price = vwrl_dict["price"] + 0.20
vrije_ruimte = flatex_eur_dict["value"] - total_orders_value
buy_amount = int(vrije_ruimte / buy_price)

if(buy_amount > 0):
    muney_check = True

    order = Order(
        action=Order.Action.BUY,
        order_type=Order.OrderType.LIMIT,
        price=buy_price,
        product_id=4586985,
        size=buy_amount,
        time_type=Order.TimeType.GOOD_TILL_DAY,
    )

    #check order
    try:
        checking_response = trading_api.check_order(order=order)
    except TimeoutError:
        logging.warning("TradingAPI session did timeout, reconnecting for new session ID...")
        trading_api.connect()
        checking_response = trading_api.check_order(order=order)

    #check transaction cost
    try:
        transaction_fee = checking_response.transaction_fee
        if transaction_fee == 0:
            fee_check = True
    except Exception as e:
        logging.error(e)


if (muney_check & fee_check & orders_check & history_check & tradingHours_check):
    
    confirmation_id = checking_response.confirmation_id

    
    confirmation_response = trading_api.confirm_order(
        confirmation_id=confirmation_id, order=order
    )
    
    logstr = "{} - ORDER PLACED FOR {} @ {} = {}\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"),buy_amount,buy_price,buy_price*buy_amount)
    print(logstr)
    f = open("log.txt", "a")
    f.write(logstr)
    f.close()
else:
    logstr = "{} - NO ORDER PLACED - CHECKS muney/fee/order/history/hours: {} {} {} {} {}\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"),muney_check,fee_check,orders_check,history_check,tradingHours_check)
    print(logstr)
    f = open("log.txt", "a")
    f.write(logstr)
    f.close()

trading_api.logout()