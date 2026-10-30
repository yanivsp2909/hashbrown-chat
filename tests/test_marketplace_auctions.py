"""🛒 The player marketplace: /sell badge 🔥 300 lists a badge you own; /market shows the listings; /market buy N buys
one (MARKETPLACE_FEE_PERCENT to the public fund, the rest to the seller); /market cancel N takes it back.
🔨 Auctions: a rare badge (config.RARE_BADGES) is auctioned in the Lobby; /bid N (your tokens are held, and given
back if someone bids more); the highest bid when AUCTION_SECONDS are up wins the badge; the money goes to the fund."""
import time

import pytest

from chatserver import auctions, config, state

pytestmark = pytest.mark.integration


def owns(key, badge, tokens=1000):
    state.accounts[key]["badges"] = [badge]
    state.accounts[key]["badge"] = badge
    state.accounts[key]["tokens"] = tokens


def test_list_buy_with_a_fee(user):
    adi, ben = user("Adi"), user("Ben")
    owns("adi", "🔥")
    state.accounts["ben"]["tokens"] = 1000
    adi.line("/sell badge 🔥 300")
    adi.expect_text("listed 🔥 for 300")
    assert "🔥" not in state.accounts["adi"]["badges"] and state.accounts["adi"]["badge"] == ""
    ben.line("/market")
    listing = ben.expect_text("🛒 Marketplace")["text"]
    assert "🔥" in listing and "300" in listing and "Adi" in listing
    ben.line("/market buy 1")
    ben.expect_text("You bought 🔥")
    fee = 300 * config.MARKETPLACE_FEE_PERCENT // 100
    assert "🔥" in state.accounts["ben"]["badges"] and state.accounts["ben"]["tokens"] == 700
    assert state.accounts["adi"]["tokens"] == 1000 + 300 - fee and state.public_fund == fee
    adi.expect_text("sold 🔥")


def test_cancel_gives_the_badge_back(user):
    adi = user("Adi")
    owns("adi", "😎")
    adi.line("/sell badge 😎 50")
    adi.expect_text("listed")
    adi.line("/market cancel 1")
    adi.expect_text("back")
    assert "😎" in state.accounts["adi"]["badges"] and state.economy_extra.get("listings") == []


@pytest.mark.parametrize("line, error", [
    ("/sell badge 🐐 100", "don't own"), ("/sell badge 🔥 0", "Use: /sell badge"), ("/market buy 9", "No listing"),
])
def test_marketplace_mistakes(user, line, error):
    adi = user("Adi")
    owns("adi", "🔥")
    adi.line(line)
    adi.expect_text(error, kind="error")


def test_you_cant_buy_your_own_or_one_you_have(user):
    adi, ben = user("Adi"), user("Ben")
    owns("adi", "🔥")
    adi.line("/sell badge 🔥 10")
    adi.expect_text("listed")
    adi.line("/market buy 1")
    adi.expect_text("your own", kind="error")
    owns("ben", "🔥")
    ben.line("/market buy 1")
    ben.expect_text("already have", kind="error")


def start(badge="🦄"):
    with state.lock:
        auctions.start(badge)


def test_an_auction_bids_refunds_and_a_winner(user):
    adi, ben = user("Adi"), user("Ben")
    state.accounts["adi"]["tokens"] = state.accounts["ben"]["tokens"] = 1000
    start()
    ben.expect_text("🔨 Auction")
    adi.line(f"/bid {config.AUCTION_START_PRICE}")
    adi.expect_text("top bid")
    assert state.accounts["adi"]["tokens"] == 1000 - config.AUCTION_START_PRICE
    ben.line(f"/bid {config.AUCTION_START_PRICE}")
    ben.expect_text("at least", kind="error")
    ben.line("/bid 300")
    adi.expect_text("outbid")
    assert state.accounts["adi"]["tokens"] == 1000                      # held tokens back
    state.economy_extra["auction"]["until"] = time.time() - 1
    with state.lock:
        auctions.tick()
    adi.expect_text("Ben won the auction")
    assert "🦄" in state.accounts["ben"]["badges"] and state.accounts["ben"]["tokens"] == 700
    assert state.public_fund == 300 and "auction" not in state.economy_extra


def test_no_bids_no_winner_and_bids_need_an_auction(user):
    adi = user("Adi")
    adi.line("/bid 200")
    adi.expect_text("No auction", kind="error")
    start()
    state.economy_extra["auction"]["until"] = time.time() - 1
    with state.lock:
        auctions.tick()
    adi.expect_text("Nobody bid")


def test_a_bid_held_over_a_restart_is_given_back(user):
    adi = user("Adi")
    state.accounts["adi"]["tokens"] = 1000
    start()
    adi.line("/bid 150")
    adi.expect_text("top bid")
    with state.lock:
        auctions.refund_after_restart()
    assert state.accounts["adi"]["tokens"] == 1000 and "auction" not in state.economy_extra
