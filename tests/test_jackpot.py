"""💰 The jackpot: a share of every casino loss goes into a pot; three 💎 on /slots wins all of it."""
import json
import random

import pytest

from chatserver import config, state, storage

pytestmark = pytest.mark.integration


def test_losing_feeds_the_pot(user, monkeypatch):
    adi = user("Adi")
    monkeypatch.setattr(random, "choice", lambda options: "tails")
    adi.line("/coinflip 50 heads")
    adi.expect_text("You lost 50")
    assert state.jackpot == 50 * config.JACKPOT_SHARE // 100


def test_three_diamonds_win_the_whole_pot(user, monkeypatch):
    adi, ben = user("Adi"), user("Ben")
    state.jackpot = 400
    before = state.accounts["adi"]["tokens"]
    monkeypatch.setattr(random, "choices", lambda options, k: ["💎"] * 3)
    adi.line("/slots 10")
    adi.expect_text("JACKPOT")
    ben.expect_text("JACKPOT")
    assert state.jackpot == 0
    jackpot_trophy = config.ACHIEVEMENTS["jackpot"][-1]
    assert state.accounts["adi"]["tokens"] == before - 10 + 250 + 400 + jackpot_trophy


def test_the_pot_is_saved_and_loaded(tmp_path):
    state.jackpot = 123
    assert storage.save_data()
    with open(config.DATA_FILE, encoding="utf-8") as f:
        assert json.load(f)["jackpot"] == 123
    state.jackpot = 0
    assert storage.load_data()
    assert state.jackpot == 123


def test_jackpot_command_shows_the_pot(user):
    adi = user("Adi")
    state.jackpot = 77
    adi.line("/jackpot")
    assert "77" in adi.expect_text("💰")["text"]
