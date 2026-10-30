"""🥔 /give hashbrown 10: Hashbrown keeps its own balance (saved in chat_data.json), shows up in /top and says
a short thanks in the room (no AI call). The usual /give limits apply."""
import json

import pytest

from chatserver import config, state, storage

pytestmark = pytest.mark.integration


def old(key):
    state.accounts[key]["created"] = 0


def test_a_tip_moves_tokens_and_hashbrown_says_thanks(user, fake_hashbrown):
    adi, ben = user("Adi"), user("Ben")
    old("adi")
    adi.line("/give hashbrown 10")
    adi.expect_text("You gave 10 🪙 to 🥔 Hashbrown")
    thanks = ben.expect(lambda m: m.get("type") == "chat" and m.get("name") == "Hashbrown")
    assert "Adi" in thanks["text"] and "10" in thanks["text"]
    assert state.hashbrown_tokens == 10 and state.accounts["adi"]["tokens"] == config.START_TOKENS - 10
    assert fake_hashbrown.requests == []                    # no AI call


def test_works_with_the_at_sign_and_any_case(user):
    adi = user("Adi")
    old("adi")
    adi.line("/give @HashBrown 5")
    adi.expect_text("You gave 5")
    assert state.hashbrown_tokens == 5


def test_hashbrown_is_in_top(user):
    adi = user("Adi")
    state.hashbrown_tokens = 10 ** 6
    adi.line("/top")
    top = adi.expect_text("Richest")["text"]
    assert top.split("\n")[1].strip().startswith("🥇 🥔 Hashbrown") and "1000000" in top


def test_new_accounts_cant_tip_either(user):
    adi = user("Adi")
    adi.line("/give hashbrown 5")
    adi.expect_text("first 24 hours", kind="error")
    assert state.hashbrown_tokens == 0


def test_the_balance_is_saved(user, tmp_path, monkeypatch):
    state.hashbrown_tokens = 42
    path = tmp_path / "data.json"
    monkeypatch.setattr(config, "DATA_FILE", str(path))
    storage.save_data()
    assert json.loads(path.read_text(encoding="utf-8"))["hashbrown_tokens"] == 42
    state.hashbrown_tokens = 0
    assert storage.load_data() and state.hashbrown_tokens == 42
