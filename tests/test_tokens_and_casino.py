"""Economy behavior: /balance /top /give /daily /rob /shop /buy /badge and the casino games.

Every test plays as a real client against the real server. Randomness is replaced by
fixed values so wins and losses are predictable, and amounts come from config.
"""
import random
import time

import pytest

from chatserver import config, state

pytestmark = pytest.mark.integration

HOUR = 3600


def set_tokens(name, amount):
    with state.lock:
        state.accounts[name.lower()]["tokens"] = amount


def tokens(name):
    return state.accounts[name.lower()]["tokens"]


def set_account(name, **fields):
    with state.lock:
        state.accounts[name.lower()].update(fields)


def fix_coin(monkeypatch, side):
    monkeypatch.setattr(random, "choice", lambda options: side)


def fix_dice(monkeypatch, rolls):
    values = iter(rolls)  # your two dice first, then the house's two
    monkeypatch.setattr(random, "randint", lambda a, b: next(values))


def fix_reels(monkeypatch, reels):
    monkeypatch.setattr(random, "choices", lambda symbols, k: list(reels))


# ---------------------------------------------------------------- /balance and /top

def test_balance_shows_your_tokens(user):
    adi = user("Adi")
    set_tokens("Adi", 321)
    adi.line("/balance")
    adi.expect_text("Adi has 321 tokens", kind="money")


def test_balance_can_look_at_someone_else(user):
    adi, _ben = user("Adi"), user("Ben")
    set_tokens("Ben", 77)
    adi.line("/balance ben")
    adi.expect_text("Ben has 77 tokens", kind="money")


def test_balance_of_unknown_name_is_an_error(user):
    adi = user("Adi")
    adi.line("/balance Nobody")
    adi.expect_text("No one called Nobody", kind="error")


def test_top_lists_the_richest_first(user):
    adi, _ben = user("Adi"), user("Ben")
    set_tokens("Adi", 10)
    set_tokens("Ben", 900)
    adi.line("/top")
    message = adi.expect_text("Richest players", kind="money")
    assert message["text"].index("Ben") < message["text"].index("Adi")
    assert "🥇 Ben  900" in message["text"]


# ---------------------------------------------------------------- /give

def test_give_moves_tokens_to_the_other_person(user):
    adi, ben = user("Adi"), user("Ben")
    state.accounts["adi"]["created"] = 0   # an old account (new ones can't /give)
    adi.line("/give Ben 30")
    adi.expect_text("You gave 30", kind="money")
    ben.expect_text("Adi gave you 30", kind="money")
    assert tokens("Adi") == config.START_TOKENS - 30
    assert tokens("Ben") == config.START_TOKENS + 30


def test_give_all_empties_your_wallet(user):
    adi, _ben = user("Adi"), user("Ben")
    state.accounts["adi"]["created"] = 0   # an old account (new ones can't /give)
    adi.line("/give Ben all")
    adi.expect_text("You gave", kind="money")
    assert tokens("Adi") == 0
    assert tokens("Ben") == 2 * config.START_TOKENS


def test_cannot_give_more_than_you_have(user):
    adi, _ben = user("Adi"), user("Ben")
    adi.line(f"/give Ben {config.START_TOKENS + 1}")
    adi.expect_text(f"You only have {config.START_TOKENS}", kind="error")
    assert tokens("Adi") == config.START_TOKENS
    assert tokens("Ben") == config.START_TOKENS


@pytest.mark.parametrize("amount", ["0", "-5", "abc", "1.5"])
def test_cannot_give_a_bad_amount(user, amount):
    adi, _ben = user("Adi"), user("Ben")
    adi.line(f"/give Ben {amount}")
    adi.expect_text("amount must be", kind="error")
    assert tokens("Adi") == config.START_TOKENS
    assert tokens("Ben") == config.START_TOKENS


def test_cannot_give_to_yourself(user):
    adi = user("Adi")
    adi.line("/give Adi 10")
    adi.expect_text("Give to who?", kind="error")
    assert tokens("Adi") == config.START_TOKENS


def test_cannot_give_to_someone_who_does_not_exist(user):
    adi = user("Adi")
    adi.line("/give Ghost 10")
    adi.expect_text("Give to who?", kind="error")
    assert tokens("Adi") == config.START_TOKENS


def test_give_without_an_amount_shows_usage(user):
    adi, _ben = user("Adi"), user("Ben")
    adi.line("/give Ben")
    adi.expect_text("Usage: /give", kind="error")


# ---------------------------------------------------------------- /daily

def test_first_daily_gives_the_base_bonus(user):
    adi = user("Adi")
    adi.line("/daily")
    adi.expect_text(f"+{config.DAILY_BONUS}", kind="money")
    assert tokens("Adi") == config.START_TOKENS + config.DAILY_BONUS
    assert state.accounts["adi"]["streak"] == 1


def test_daily_can_only_be_claimed_once_a_day(user):
    adi = user("Adi")
    adi.line("/daily")
    adi.expect_text("daily bonus", kind="money")
    adi.line("/daily")
    adi.expect_text("Come back in", kind="error")
    assert tokens("Adi") == config.START_TOKENS + config.DAILY_BONUS


def test_daily_the_next_day_grows_the_streak_bonus(user):
    adi = user("Adi")
    set_account("Adi", last_daily=time.time() - 25 * HOUR, streak=1)
    adi.line("/daily")
    adi.expect_text("2 day streak", kind="money")
    assert tokens("Adi") == config.START_TOKENS + config.DAILY_BONUS + config.STREAK_BONUS


def test_daily_streak_resets_after_waiting_too_long(user):
    adi = user("Adi")
    set_account("Adi", last_daily=time.time() - 72 * HOUR, streak=5)
    adi.line("/daily")
    adi.expect_text("1 day streak", kind="money")
    assert tokens("Adi") == config.START_TOKENS + config.DAILY_BONUS


def test_daily_bonus_stops_growing_at_the_maximum(user):
    adi = user("Adi")
    set_account("Adi", last_daily=time.time() - 25 * HOUR, streak=9)  # day 10 would be 600 without the cap
    reward = config.DAILY_MAX
    adi.line("/daily")
    adi.expect_text(f"+{reward}", kind="money")
    on_fire_reward = config.ACHIEVEMENTS["on_fire"][3]  # streak 10 also earns the 7-day trophy
    assert tokens("Adi") == config.START_TOKENS + reward + on_fire_reward


def test_seven_day_streak_unlocks_on_fire(user):
    adi = user("Adi")
    set_account("Adi", last_daily=time.time() - 25 * HOUR, streak=6)
    adi.line("/daily")
    adi.expect_text("ACHIEVEMENT UNLOCKED: 🔥")
    assert "on_fire" in state.accounts["adi"]["achievements"]


# ---------------------------------------------------------------- /rob

def test_successful_rob_steals_a_share_of_their_tokens(user, monkeypatch):
    adi, ben = user("Adi"), user("Ben")
    monkeypatch.setattr(random, "random", lambda: 0.1)  # below 0.4 = success
    monkeypatch.setattr(random, "randint", lambda a, b: 10)  # steal 10 percent
    stolen = config.START_TOKENS * 10 // 100
    adi.line("/rob Ben")
    adi.expect_text(f"You stole {stolen}", kind="money")
    ben.expect_text(f"robbed you and got away with {stolen}", kind="error")
    bandit_reward = config.ACHIEVEMENTS["bandit"][3]
    assert tokens("Ben") == config.START_TOKENS - stolen
    assert tokens("Adi") == config.START_TOKENS + stolen + bandit_reward


def test_a_robbery_never_steals_more_than_500(user, monkeypatch):
    adi, _ben = user("Adi"), user("Ben")
    set_tokens("Ben", 100000)
    monkeypatch.setattr(random, "random", lambda: 0.1)
    monkeypatch.setattr(random, "randint", lambda a, b: 15)
    adi.line("/rob Ben")
    adi.expect_text("You stole 500", kind="money")
    assert tokens("Ben") == 100000 - 500


def test_failed_rob_costs_a_fine_paid_to_the_victim(user, monkeypatch):
    adi, ben = user("Adi"), user("Ben")
    monkeypatch.setattr(random, "random", lambda: 0.9)  # above 0.4 = caught
    adi.line("/rob Ben")
    adi.expect_text("Caught! You paid 50", kind="error")
    ben.expect_text("tried to rob you and failed", kind="money")
    assert tokens("Adi") == config.START_TOKENS - 50
    assert tokens("Ben") == config.START_TOKENS + 50


def test_fine_is_limited_to_what_the_robber_has(user, monkeypatch):
    adi, _ben = user("Adi"), user("Ben")
    set_tokens("Adi", 20)
    monkeypatch.setattr(random, "random", lambda: 0.9)
    adi.line("/rob Ben")
    adi.expect_text("You paid 20", kind="error")
    assert tokens("Adi") == 0


def test_cannot_rob_twice_in_a_row(user, monkeypatch):
    adi, _ben = user("Adi"), user("Ben")
    monkeypatch.setattr(random, "random", lambda: 0.9)
    adi.line("/rob Ben")
    adi.expect_text("Caught!", kind="error")
    adi.line("/rob Ben")
    adi.expect_text("Lay low", kind="error")
    assert tokens("Adi") == config.START_TOKENS - 50


def test_can_rob_again_after_the_cooldown(user, monkeypatch):
    adi, _ben = user("Adi"), user("Ben")
    monkeypatch.setattr(random, "random", lambda: 0.9)
    adi.line("/rob Ben")
    adi.expect_text("Caught!", kind="error")
    with state.lock:
        state.last_rob["adi"] = time.time() - 301
    adi.line("/rob Ben")
    adi.expect_text("Caught!", kind="error")
    assert tokens("Adi") == config.START_TOKENS - 100


def test_cannot_rob_someone_who_is_too_broke(user):
    adi, _ben = user("Adi"), user("Ben")
    set_tokens("Ben", 49)
    adi.line("/rob Ben")
    adi.expect_text("too broke to rob", kind="error")
    assert tokens("Adi") == config.START_TOKENS
    assert "adi" not in state.last_rob  # a refused rob doesn't start the cooldown


def test_cannot_rob_yourself(user):
    adi = user("Adi")
    adi.line("/rob Adi")
    adi.expect_text("Robbing yourself", kind="error")


def test_cannot_rob_someone_who_is_not_online(user):
    adi, ben = user("Adi"), user("Ben")
    ben.line("/quit")
    ben.wait_closed()
    adi.line("/rob Ben")
    adi.expect_text("isn't online", kind="error")


# ---------------------------------------------------------------- /shop, /buy, /badge

def test_shop_lists_every_badge_with_its_price(user):
    adi = user("Adi")
    adi.line("/shop")
    message = adi.expect_text("Badge shop", kind="money")
    for badge, price in config.SHOP.items():
        assert f"{badge}  {price}" in message["text"]


def test_buying_a_badge_costs_its_price_and_wears_it(user):
    adi = user("Adi")
    set_tokens("Adi", 500)
    price = config.SHOP["😎"]
    adi.line("/buy 😎")
    adi.expect_text("You bought 😎", kind="money")
    assert tokens("Adi") == 500 - price
    assert state.accounts["adi"]["badges"] == ["😎"]
    assert state.accounts["adi"]["badge"] == "😎"


def test_shop_marks_badges_you_own(user):
    adi = user("Adi")
    set_tokens("Adi", 500)
    adi.line("/buy 😎")
    adi.expect_text("You bought")
    adi.line("/shop")
    message = adi.expect_text("Badge shop")
    assert "😎  250 🪙  ✅ owned" in message["text"]
    assert "🎮  400 🪙\n" in message["text"]


def test_cannot_buy_a_badge_you_cannot_afford(user):
    adi = user("Adi")
    set_tokens("Adi", config.SHOP["😎"] - 1)
    adi.line("/buy 😎")
    adi.expect_text("costs", kind="error")
    assert tokens("Adi") == config.SHOP["😎"] - 1
    assert state.accounts["adi"]["badges"] == []


def test_cannot_buy_something_that_is_not_in_the_shop(user):
    adi = user("Adi")
    adi.line("/buy 🍕")
    adi.expect_text("not in the /shop", kind="error")


def test_buying_a_badge_twice_does_not_charge_twice(user):
    adi = user("Adi")
    set_tokens("Adi", 500)
    adi.line("/buy 🔥")
    adi.expect_text("You bought")
    adi.line("/buy 🔥")
    adi.expect_text("already own")
    assert tokens("Adi") == 500 - config.SHOP["🔥"]


def test_badge_shows_next_to_your_name(user):
    adi = user("Adi")
    set_tokens("Adi", 500)
    adi.line("/buy 🔥")
    adi.expect_text("You bought")
    adi.line("/balance")
    adi.expect_text("🔥 Adi has", kind="money")


def test_badge_switches_between_owned_badges_and_hides_with_off(user):
    adi = user("Adi")
    set_tokens("Adi", 500)
    for badge in ("🔥", "😎"):
        adi.line(f"/buy {badge}")
        adi.expect_text("You bought")
    adi.line("/badge 🔥")
    adi.expect_text("You're now 🔥 Adi")
    adi.line("/badge off")
    adi.expect_text("You're now Adi")
    assert state.accounts["adi"]["badge"] == ""


def test_cannot_wear_a_badge_you_do_not_own(user):
    adi = user("Adi")
    adi.line("/badge 👑")
    adi.expect_text("You don't own that", kind="error")
    assert state.accounts["adi"]["badge"] == ""


def test_expensive_badge_purchase_is_announced_to_others(user):
    adi, ben = user("Adi"), user("Ben")
    set_tokens("Adi", 1500)  # 💎 costs 1000
    adi.line("/buy 💎")
    adi.expect_text("You bought 💎", kind="money")
    ben.expect_text("just bought the 💎 badge")


# ---------------------------------------------------------------- /achievements

def test_achievements_shows_locked_and_unlocked_trophies(user):
    adi = user("Adi")
    set_account("Adi", achievements=["founder"])
    adi.line("/achievements")
    message = adi.expect_text("Achievements (1/", kind="money")
    assert f"/{len(config.ACHIEVEMENTS)})" in message["text"]
    assert "✅ 🏗️" in message["text"]
    assert "🔒 🥇" in message["text"]


# ---------------------------------------------------------------- /coinflip

def test_coinflip_win_doubles_the_bet(user, monkeypatch):
    adi = user("Adi")
    fix_coin(monkeypatch, "heads")
    adi.line("/coinflip 40 heads")
    adi.expect_text("You won 40", kind="money")
    assert tokens("Adi") == config.START_TOKENS + 40


def test_coinflip_loss_takes_the_bet(user, monkeypatch):
    adi = user("Adi")
    fix_coin(monkeypatch, "tails")
    adi.line("/coinflip 40 heads")
    adi.expect_text("You lost 40", kind="error")
    assert tokens("Adi") == config.START_TOKENS - 40


def test_coinflip_accepts_short_side_names(user, monkeypatch):
    adi = user("Adi")
    fix_coin(monkeypatch, "tails")
    adi.line("/coinflip 10 T")
    adi.expect_text("You won 10", kind="money")


def test_coinflip_needs_heads_or_tails(user):
    adi = user("Adi")
    adi.line("/coinflip 10 edge")
    adi.expect_text("Usage: /coinflip", kind="error")
    assert tokens("Adi") == config.START_TOKENS


def test_coinflip_all_in_loss_leaves_zero(user, monkeypatch):
    adi = user("Adi")
    fix_coin(monkeypatch, "tails")
    adi.line("/coinflip all heads")
    adi.expect_text(f"You lost {config.START_TOKENS}", kind="error")
    assert tokens("Adi") == 0


# ---------------------------------------------------------------- bad bets (all games)

@pytest.mark.parametrize("command", ["/dice {}", "/slots {}", "/coinflip {} heads"])
@pytest.mark.parametrize("bet, message", [
    ("0", "more than 0"),
    ("-10", "must be a number"),
    ("lots", "must be a number"),
    (str(config.START_TOKENS + 1), f"You only have {config.START_TOKENS}"),
])
def test_bad_bets_are_refused_and_cost_nothing(user, command, bet, message):
    adi = user("Adi")
    adi.line(command.format(bet))
    adi.expect_text(message, kind="error")
    assert tokens("Adi") == config.START_TOKENS


def test_betting_with_nothing_is_refused(user):
    adi = user("Adi")
    set_tokens("Adi", 0)
    adi.line("/dice all")
    adi.expect_text("more than 0", kind="error")


# ---------------------------------------------------------------- /dice

def test_dice_win_when_your_total_beats_the_house(user, monkeypatch):
    adi = user("Adi")
    fix_dice(monkeypatch, [6, 5, 1, 2])
    adi.line("/dice 30")
    adi.expect_text("You won 30", kind="money")
    assert tokens("Adi") == config.START_TOKENS + 30


def test_dice_loss_when_the_house_total_is_higher(user, monkeypatch):
    adi = user("Adi")
    fix_dice(monkeypatch, [1, 2, 6, 5])
    adi.line("/dice 30")
    adi.expect_text("You lost 30", kind="error")
    assert tokens("Adi") == config.START_TOKENS - 30


def test_dice_tie_gives_the_bet_back(user, monkeypatch):
    adi = user("Adi")
    fix_dice(monkeypatch, [3, 4, 6, 1])
    adi.line("/dice 30")
    adi.expect_text("got your bet back", kind="money")
    assert tokens("Adi") == config.START_TOKENS


# ---------------------------------------------------------------- /slots

def test_slots_two_matching_symbols_pay_one_and_a_half_times(user, monkeypatch):
    adi = user("Adi")
    fix_reels(monkeypatch, ["🍒", "🍒", "🍋"])
    adi.line("/slots 10")
    adi.expect_text("You won 5", kind="money")
    assert tokens("Adi") == config.START_TOKENS + 5


def test_slots_no_match_loses_the_bet(user, monkeypatch):
    adi = user("Adi")
    fix_reels(monkeypatch, ["🍒", "🍋", "🍇"])
    adi.line("/slots 10")
    adi.expect_text("You lost 10", kind="error")
    assert tokens("Adi") == config.START_TOKENS - 10


def test_slots_three_of_a_kind_pays_ten_times_and_unlocks_jackpot(user, monkeypatch):
    adi = user("Adi")
    fix_reels(monkeypatch, ["🍒"] * 3)
    adi.line("/slots 10")
    adi.expect_text("You won 90", kind="money")
    adi.expect_text("ACHIEVEMENT UNLOCKED: 🎰")
    assert tokens("Adi") == config.START_TOKENS + 90 + config.ACHIEVEMENTS["jackpot"][3]


def test_slots_three_diamonds_pay_25_times(user, monkeypatch):
    adi = user("Adi")
    fix_reels(monkeypatch, ["💎"] * 3)
    adi.line("/slots 10")
    adi.expect_text("You won 240", kind="money")


# ---------------------------------------------------------------- big wins and high rollers

def test_big_casino_win_is_announced_to_everyone_else(user, monkeypatch):
    adi, ben = user("Adi"), user("Ben")
    set_tokens("Adi", 500)
    fix_coin(monkeypatch, "heads")
    adi.line("/coinflip 500 heads")
    ben.expect_text("Adi just won 500", kind=None)


def test_betting_500_unlocks_high_roller(user, monkeypatch):
    adi = user("Adi")
    set_tokens("Adi", 600)
    fix_coin(monkeypatch, "tails")
    adi.line("/coinflip 500 heads")
    adi.expect_text("ACHIEVEMENT UNLOCKED: 🎲")
    assert tokens("Adi") == 100 + config.ACHIEVEMENTS["high_roller"][3]
