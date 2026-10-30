"""⌨️ The typing indicator: {"type": "typing"} from you -> {"type": "typing", "name": you} to the others in
your room who said "typing" at login. It never counts toward the spam limit (it has its own limit)."""
import pytest

from chatserver import config

pytestmark = pytest.mark.integration


@pytest.fixture
def typer(connect):
    def make(name, features=("typing",)):
        client = connect()
        client.send({"type": "auth", "action": "register", "username": name, "password": "pass1234",
                     "features": list(features)})
        assert client.expect(lambda m: m.get("type") == "auth_result")["ok"]
        client.expect(lambda m: m.get("type") == "history")
        return client
    return make


def settle(client):
    client.line("/users")
    client.expect_text("Online now")


def typing_from(client, name):
    return [m for m in client.messages if m.get("type") == "typing" and m.get("name") == name]


def test_the_others_in_the_room_see_you_typing(typer):
    adi, ben = typer("Adi"), typer("Ben")
    adi.send({"type": "typing"})
    assert ben.expect(lambda m: m.get("type") == "typing")["name"] == "Adi"
    settle(adi)
    assert typing_from(adi, "Adi") == []                       # not sent back to you


def test_old_clients_and_other_rooms_dont_get_it(typer, user):
    adi, cat = typer("Adi"), typer("Cat")
    old = user("Old")
    cat.line("/create Potatoes")
    cat.expect_text("Created")
    adi.send({"type": "typing"})
    settle(old)
    settle(cat)
    assert typing_from(old, "Adi") == [] and typing_from(cat, "Adi") == []


def test_typing_doesnt_count_toward_the_spam_limit_and_has_its_own_limit(typer, monkeypatch):
    monkeypatch.setattr(config, "SPAM_LIMIT", 2)
    adi, ben = typer("Adi"), typer("Ben")
    for _ in range(6):
        adi.send({"type": "typing"})
    adi.line("still allowed to talk")
    ben.expect(lambda m: m.get("text") == "still allowed to talk")
    assert len(typing_from(ben, "Adi")) == 1                   # one per TYPING_EVERY seconds
