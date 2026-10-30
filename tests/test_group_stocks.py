"""👥📈 Group stocks: every group is also a stock (#Name). Its price moves toward a target made of its bank,
its members and how busy it was in the last hour. A group that grew since yesterday pays its shareholders a small
daily dividend from its bank. A disbanded group's shares are paid out at the last price."""
import pytest

from chatserver import config, economy, group_stocks, market, state

pytestmark = pytest.mark.integration


def group(owner, name="Potatoes"):
    owner.line(f"/create {name}")
    owner.expect_text("Created")


def test_a_group_gets_a_stock_and_its_price_follows_bank_and_activity(user):
    adi = user("Adi")
    group(adi)
    with state.lock:
        group_stocks.tick()
    assert "#potatoes" in state.stocks
    before = state.stocks["#potatoes"]["price"]
    state.groups["potatoes"]["bank"] = 2000
    for _ in range(10):
        with state.lock:
            group_stocks.tick()
    assert state.stocks["#potatoes"]["price"] > before
    assert group_stocks.target("potatoes") >= config.GROUP_STOCK_BASE + 2000 // config.GROUP_STOCK_BANK_PER_POINT


def test_buy_and_sell_a_group_stock(user):
    adi, ben = user("Adi"), user("Ben")
    group(adi)
    with state.lock:
        group_stocks.tick()
    state.accounts["ben"]["tokens"] = 1000
    ben.line("/buy #Potatoes 3")
    ben.expect_text("You bought 3 #POTATOES")
    assert state.accounts["ben"]["portfolio"] == {"#potatoes": 3}
    ben.line("/sell #potatoes 1")
    ben.expect_text("You sold 1 #POTATOES")
    ben.line("/stocks")
    assert "#Potatoes" in ben.expect_text("📈 Stocks")["text"]


def test_a_growing_group_pays_a_dividend_from_its_bank(user):
    adi, ben = user("Adi"), user("Ben")
    group(adi)
    with state.lock:
        group_stocks.tick()
    state.accounts["ben"]["tokens"] = 5000
    ben.line("/buy #Potatoes 10")
    ben.expect_text("You bought")
    state.groups["potatoes"]["bank"] = 1000
    state.economy_extra["group_size"] = {"potatoes": [1, 0]}     # yesterday: 1 member, empty bank
    tokens = state.accounts["ben"]["tokens"]
    with state.lock:
        group_stocks.pay_dividends()
    paid = state.accounts["ben"]["tokens"] - tokens
    assert paid > 0 and state.groups["potatoes"]["bank"] == 1000 - paid
    ben.expect_text("dividend")


def test_no_dividend_when_the_group_didnt_grow(user):
    adi, ben = user("Adi"), user("Ben")
    group(adi)
    with state.lock:
        group_stocks.tick()
    state.accounts["ben"]["tokens"] = 5000
    ben.line("/buy #Potatoes 10")
    ben.expect_text("You bought")
    state.economy_extra["group_size"] = {"potatoes": [5, 99999]}
    tokens = state.accounts["ben"]["tokens"]
    with state.lock:
        group_stocks.pay_dividends()
    assert state.accounts["ben"]["tokens"] == tokens


def test_disbanding_pays_shareholders_and_removes_the_stock(user):
    adi, ben = user("Adi"), user("Ben")
    group(adi)
    with state.lock:
        group_stocks.tick()
    state.accounts["ben"]["tokens"] = 5000
    ben.line("/buy #Potatoes 4")
    ben.expect_text("You bought")
    price = state.stocks["#potatoes"]["price"]
    tokens = state.accounts["ben"]["tokens"]
    adi.line("/disband")
    ben.expect_text("paid out")
    assert "#potatoes" not in state.stocks and state.accounts["ben"]["portfolio"] == {}
    assert state.accounts["ben"]["tokens"] == tokens + 4 * price
    assert market is not None and economy is not None


# ---------------------------------------------------------------- code review: no pumping, no minted profit

def test_one_person_spamming_their_group_counts_only_a_little(user):
    adi = user("Adi")
    group(adi)
    for i in range(40):
        adi.line(f"spam {i}")
    adi.line("/users")
    adi.expect_text("Online now")
    assert group_stocks.busy("potatoes") == config.GROUP_STOCK_MSGS_PER_MEMBER


def test_a_group_stocks_profit_comes_from_the_fund(user):
    adi = user("Adi")
    group(adi)
    with state.lock:
        group_stocks.tick()
    state.accounts["adi"]["tokens"] = 1000
    state.stocks["#potatoes"]["price"] = 10
    adi.line("/buy #Potatoes 10")
    adi.expect_text("You bought")
    state.stocks["#potatoes"]["price"] = 50          # pushed up
    state.public_fund = 0
    before = state.accounts["adi"]["tokens"]
    adi.line("/sell #Potatoes 10")
    adi.expect_text("could only pay 0")
    assert state.accounts["adi"]["tokens"] == before + 100   # only what it cost
