"""💬 Chat commands: private messages, /me, /nick, /whois and /users."""
import pytest

from chatserver import config, state

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------- 💌 /send

def test_a_private_message_reaches_only_the_person_it_is_for(user):
    adi, ben, cat = user("Adi"), user("Ben"), user("Cat")
    adi.line("/send Ben meet me at 5")
    ben.expect_text("Adi → you: meet me at 5", kind="private")
    adi.expect_text("you → Ben: meet me at 5", kind="private")
    cat.line("/users")
    cat.expect_text("Online now")  # anything Cat got before this reply was sent before the message
    assert not any("meet me at 5" in text for text in cat.texts())


@pytest.mark.parametrize("line, error", [
    ("/send Ben", "Usage: /send name message"),
    ("/send Adi hi", "can't message yourself"),
    ("/send Nobody hi", "Nobody"),
])
def test_bad_private_messages_are_refused(user, line, error):
    adi, _ = user("Adi"), user("Ben")
    adi.line(line)
    adi.expect_text(error, kind="error")


# ---------------------------------------------------------------- 🎭 /me

def test_me_posts_an_action_to_the_room(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/me dances")
    msg = ben.expect(lambda m: m.get("type") == "chat")
    assert (msg["name"], msg["text"], msg["action"]) == ("Adi", "dances", True)


# ---------------------------------------------------------------- ✏️ /nick

def test_nick_renames_you_but_you_still_log_in_with_the_old_name(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/nick Spud")
    ben.expect_text("✏️ Adi is now called Spud")
    adi.expect_text("You still log in as Adi")
    assert state.accounts["adi"]["nick"] == "Spud"


@pytest.mark.parametrize("new_name, error", [
    ("x", "Names: 3-16 letters"),
    ("Ben", "already has that name"),
])
def test_nick_refuses_bad_or_taken_names(user, new_name, error):
    adi, _ = user("Adi"), user("Ben")
    adi.line(f"/nick {new_name}")
    adi.expect_text(error, kind="error")
    assert state.accounts["adi"]["nick"] == "Adi"


# ---------------------------------------------------------------- 👤 /whois and /users

def test_whois_shows_a_profile(user):
    adi, _ = user("Adi"), user("Ben")
    adi.line("/whois Ben")
    profile = adi.expect_text("👤")["text"]
    assert "Ben" in profile and "online in 🏠 Lobby" in profile and f"{config.START_TOKENS} tokens" in profile


def test_whois_an_unknown_name_is_an_error(user):
    adi = user("Adi")
    adi.line("/whois Nobody")
    adi.expect_text("No one called Nobody", kind="error")


def test_users_lists_everyone_online_with_their_room(user):
    adi, _ = user("Adi"), user("Ben")
    adi.line("/users")
    listing = adi.expect_text("🟢 Online now (2):")["text"]
    assert "Adi  🏠 Lobby" in listing and "Ben  🏠 Lobby" in listing
