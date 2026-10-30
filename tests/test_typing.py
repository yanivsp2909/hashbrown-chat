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


def test_stopping_is_passed_on_and_the_next_start_goes_out_at_once(typer):
    """{"type": "typing_stop"} (you sent it or emptied the box) reaches the others right away, and when you
    start again the first "typing" isn't held back by the 2-second limit (that's only for refreshes)."""
    adi, ben = typer("Adi"), typer("Ben")
    adi.send({"type": "typing"})
    ben.expect(lambda m: m.get("type") == "typing")
    adi.send({"type": "typing_stop"})
    assert ben.expect(lambda m: m.get("type") == "typing_stop")["name"] == "Adi"
    adi.send({"type": "typing"})
    ben.expect(lambda m: m.get("type") == "typing" and len(typing_from(ben, "Adi")) == 2)


def test_sending_a_message_ends_your_typing(typer):
    adi, ben = typer("Adi"), typer("Ben")
    adi.send({"type": "typing"})
    ben.expect(lambda m: m.get("type") == "typing")
    adi.line("done")
    ben.expect(lambda m: m.get("text") == "done")
    adi.send({"type": "typing"})                       # a new message: the first key goes out at once
    ben.expect(lambda m: m.get("type") == "typing" and len(typing_from(ben, "Adi")) == 2)


def test_a_stop_without_a_start_isnt_passed_on_and_old_clients_never_see_stops(typer, user):
    adi, ben = typer("Adi"), typer("Ben")
    old = user("Old")
    adi.send({"type": "typing_stop"})
    adi.send({"type": "typing"})
    adi.send({"type": "typing_stop"})
    ben.expect(lambda m: m.get("type") == "typing_stop")
    settle(old)
    settle(ben)
    assert len([m for m in ben.messages if m.get("type") == "typing_stop"]) == 1
    assert not [m for m in old.messages if str(m.get("type", "")).startswith("typing")]


def test_start_stop_flooding_is_still_limited(typer):
    adi, ben = typer("Adi"), typer("Ben")
    for _ in range(20):
        adi.send({"type": "typing"})
        adi.send({"type": "typing_stop"})
    settle(adi)
    settle(ben)
    passed = [m for m in ben.messages if str(m.get("type", "")).startswith("typing")]
    assert len(passed) == config.TYPING_LIMIT            # then nothing until TYPING_WINDOW has passed


def test_switching_rooms_or_leaving_while_typing_stops_it(typer):
    """Code review: nobody keeps "is typing…" for someone who went to another room or left."""
    adi, ben = typer("Adi"), typer("Ben")
    adi.send({"type": "typing"})
    ben.expect(lambda m: m.get("type") == "typing")
    adi.line("/create Potatoes")
    assert ben.expect(lambda m: m.get("type") == "typing_stop")["name"] == "Adi"
    adi.line("/lobby")
    adi.expect(lambda m: m.get("type") == "history" and m.get("key") == "lobby")
    adi.send({"type": "typing"})                 # back in the lobby: a fresh start goes out at once
    assert ben.expect(lambda m: m.get("type") == "typing")["name"] == "Adi"
    adi.close()
    assert ben.expect(lambda m: m.get("type") == "typing_stop")["name"] == "Adi"
