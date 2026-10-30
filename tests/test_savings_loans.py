"""🏦 Savings and 💳 loans. /save and /withdraw move tokens into savings (at most SAVINGS_MAX); once a day savings
earn SAVINGS_INTEREST_PERCENT (at most SAVINGS_INTEREST_MAX), paid by the public fund (empty fund, no interest).
/loan N (up to LOAN_MAX, accounts older than a day, one at a time) adds LOAN_INTEREST_PERCENT and is due in
LOAN_DAYS; /repay pays it back into the fund. Missed the deadline: your income repays it first."""
import time

import pytest

from chatserver import background, config, savings, state

pytestmark = pytest.mark.integration


def old(key, tokens=1000):
    """An account that may borrow: older than a day, chatted enough; and a fund that can lend."""
    state.accounts[key]["created"] = 0
    state.accounts[key]["tokens"] = tokens
    state.accounts[key]["messages"] = config.LOAN_MIN_MESSAGES
    state.public_fund = max(state.public_fund, 1000)


def test_save_withdraw_and_show(user):
    adi = user("Adi")
    old("adi")
    adi.line("/save 300")
    adi.expect_text("saved 300")
    assert (state.accounts["adi"]["tokens"], state.accounts["adi"]["savings"]) == (700, 300)
    adi.line("/withdraw 100")
    adi.expect_text("took 100")
    adi.line("/savings")
    assert "200" in adi.expect_text("🏦 Savings")["text"]
    adi.line("/withdraw 999")
    adi.expect_text("only have 200", kind="error")


def test_savings_have_a_ceiling(user):
    adi = user("Adi")
    old("adi", 100000)
    adi.line(f"/save {config.SAVINGS_MAX + 1}")
    adi.expect_text(f"at most {config.SAVINGS_MAX}", kind="error")


def test_daily_interest_from_the_fund_with_a_cap(user):
    adi = user("Adi")
    old("adi", 100000)
    state.accounts["adi"]["savings"] = 1000
    state.public_fund = 1000
    with state.lock:
        savings.pay_interest()
    assert state.accounts["adi"]["savings"] == 1000 + 1000 * config.SAVINGS_INTEREST_PERCENT // 100
    state.accounts["adi"]["savings"] = config.SAVINGS_MAX
    before = state.accounts["adi"]["savings"]
    with state.lock:
        savings.pay_interest()
    assert state.accounts["adi"]["savings"] - before <= config.SAVINGS_INTEREST_MAX


def test_no_interest_when_the_fund_is_empty(user):
    adi = user("Adi")
    old("adi")
    state.accounts["adi"]["savings"] = 1000
    state.public_fund = 0
    with state.lock:
        savings.pay_interest()
    assert state.accounts["adi"]["savings"] == 1000


def test_a_loan_with_interest_and_paying_it_back(user):
    adi = user("Adi")
    old("adi", 0)
    fund_start = state.public_fund
    adi.line("/loan 200")
    adi.expect_text("You borrowed 200")
    assert state.public_fund == fund_start - 200        # lent by the fund: no new tokens
    loan = state.accounts["adi"]["loan"]
    assert state.accounts["adi"]["tokens"] == 200 and loan["owed"] == 200 + 200 * config.LOAN_INTEREST_PERCENT // 100
    adi.line("/loan 50")
    adi.expect_text("already have a loan", kind="error")
    state.accounts["adi"]["tokens"] = 1000
    fund_before = state.public_fund
    adi.line("/repay all")
    adi.expect_text("paid it all back")
    assert state.accounts["adi"]["loan"] is None and state.public_fund == fund_before + loan["owed"]


@pytest.mark.parametrize("line, error", [("/loan 0", "Use: /loan"), (f"/loan {config.LOAN_MAX + 1}", "at most")])
def test_loan_limits(user, line, error):
    adi = user("Adi")
    old("adi")
    adi.line(line)
    adi.expect_text(error, kind="error")


def test_new_accounts_cant_borrow(user):
    adi = user("Adi")
    adi.line("/loan 100")
    adi.expect_text("first 24 hours", kind="error")


def test_a_late_loan_takes_your_income_first(user):
    adi = user("Adi")
    old("adi", 0)
    adi.line("/loan 100")
    adi.expect_text("You borrowed")
    state.accounts["adi"]["loan"]["due"] = time.time() - 1
    state.accounts["adi"]["tokens"] = 0
    owed = state.accounts["adi"]["loan"]["owed"]
    background.income_tick()
    assert state.accounts["adi"]["tokens"] == 0
    assert state.accounts["adi"]["loan"]["owed"] == owed - config.TOKENS_PER_MINUTE



# ---------------------------------------------------------------- security review

def test_loans_only_lend_what_the_fund_has(user):
    adi = user("Adi")
    old("adi", 0)
    state.public_fund = 50
    adi.line("/loan 100")
    adi.expect_text("can lend 50", kind="error")


def test_quiet_accounts_cant_borrow(user):
    adi = user("Adi")
    old("adi", 0)
    state.accounts["adi"]["messages"] = 0
    adi.line("/loan 100")
    adi.expect_text("Chat a bit first", kind="error")


def test_a_late_loan_takes_tokens_and_savings_at_login(user):
    adi = user("Adi")
    old("adi", 0)
    adi.line("/loan 100")
    adi.expect_text("You borrowed")
    state.accounts["adi"]["loan"]["due"] = time.time() - 1
    state.accounts["adi"]["savings"] = 500
    adi.close()
    back = user("Adi", action="login")
    back.expect_text("Your loan is late")
    assert state.accounts["adi"]["loan"] is None
