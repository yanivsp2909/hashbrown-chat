"""🎁 /give against farming with extra accounts: accounts younger than GIVE_MIN_AGE_HOURS can't give, and
everyone can give at most GIVE_DAILY_MAX 🪙 a day in total."""
import json
import time

import pytest

from chatserver import config, state, storage

pytestmark = pytest.mark.integration


def grown_up(*keys):
    """Pretend these accounts were made two days ago."""
    for key in keys:
        state.accounts[key]["created"] = time.time() - 48 * 3600


def test_a_new_account_cant_give_yet(user):
    adi, _ = user("Adi"), user("Ben")
    adi.line("/give Ben 10")
    error = adi.expect_text("first 24 hours", kind="error")["text"]
    assert "h left" in error
    assert state.accounts["ben"]["tokens"] == config.START_TOKENS


def test_an_older_account_can_give(user):
    adi, ben = user("Adi"), user("Ben")
    grown_up("adi")
    adi.line("/give Ben 10")
    ben.expect_text("gave you 10")


def test_at_most_500_a_day_in_total(user):
    adi, _, _ = user("Adi"), user("Ben"), user("Cat")
    grown_up("adi")
    state.accounts["adi"]["tokens"] = 5000
    adi.line("/give Ben 300")
    adi.expect_text("You gave 300")
    adi.line("/give Cat 300")
    error = adi.expect_text("at most 500", kind="error")["text"]
    assert "200 left today" in error
    adi.line("/give Cat 200")
    adi.expect_text("You gave 200")
    assert state.accounts["cat"]["tokens"] == config.START_TOKENS + 200


def test_the_daily_total_starts_again_tomorrow(user):
    adi, _ = user("Adi"), user("Ben")
    grown_up("adi")
    state.accounts["adi"]["tokens"] = 5000
    state.accounts["adi"]["given"] = ["2000-01-01", config.GIVE_DAILY_MAX]
    adi.line("/give Ben 500")
    adi.expect_text("You gave 500")


def test_accounts_from_before_this_rule_count_as_old(tmp_path, monkeypatch):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"accounts": {"zed": {"login": "Zed", "nick": "Zed", "salt": "00", "password": "00",
                                                     "tokens": 5}}, "groups": {}}), encoding="utf-8")
    monkeypatch.setattr(config, "DATA_FILE", str(path))
    assert storage.load_data()
    assert state.accounts["zed"]["created"] == 0
    assert storage.new_account("Amy", "s", "h")["created"] > time.time() - 5
