"""
Groups: creating, joining (public and private), leaving, admin powers and the group bank.

Every test starts a real server and talks to it with fake clients, like test_economy_fixes.py.
"""
import pytest

from chatserver import config, state

pytestmark = pytest.mark.integration

GROUP = "Potatoes"
KEY = "potatoes"


def give_tokens(name, amount):
    with state.lock:
        state.accounts[name.lower()]["tokens"] = amount


def tokens(name):
    return state.accounts[name.lower()]["tokens"]


def enter_room(client):
    """Wait for the history message the server sends whenever you change room."""
    client.expect(lambda m: m.get("type") == "history")


def make_group(owner, private=False):
    """The owner creates the Potatoes group and is moved into it."""
    suffix = " private" if private else ""
    owner.line(f"/create {GROUP}{suffix}")
    owner.expect_text("Created")
    enter_room(owner)


def join_group(client):
    client.line(f"/join {GROUP}")
    enter_room(client)


def group_with_members(user, *names):
    """Returns [owner, member, ...]: the first name owns a public Potatoes, the rest joined it."""
    people = [user(n) for n in names]
    make_group(people[0])
    for person in people[1:]:
        join_group(person)
    return people


def saw_chat(client, text):
    with client.arrived:
        return any(m.get("type") == "chat" and m.get("text") == text for m in client.messages)


# ---------------------------------------------------------------- creating

def test_creating_a_group_costs_tokens_and_makes_you_the_owner(user):
    adi = user("Adi")
    give_tokens("Adi", 500)
    make_group(adi)
    founder_reward = config.ACHIEVEMENTS["founder"][3]
    assert tokens("Adi") == 500 - config.GROUP_COST + founder_reward
    assert state.groups[KEY]["owner"] == "adi"
    assert state.groups[KEY]["members"] == ["adi"]


def test_cannot_create_a_group_without_enough_tokens(user):
    adi = user("Adi")
    give_tokens("Adi", config.GROUP_COST - 1)
    adi.line(f"/create {GROUP}")
    adi.expect_text("costs", kind="error")
    assert KEY not in state.groups


def test_cannot_create_a_group_with_a_taken_name(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi)
    ben.line(f"/create {GROUP.upper()}")
    ben.expect_text("already exists", kind="error")


def test_group_names_must_be_valid(user):
    adi = user("Adi")
    adi.line("/create ab")
    adi.expect_text("3-16 letters", kind="error")
    adi.line("/create lobby")
    adi.expect_text("3-16 letters", kind="error")
    assert not state.groups


def test_groups_list_shows_groups_and_your_membership(user):
    adi, ben = user("Adi"), user("Ben")
    ben.line("/groups")
    ben.expect_text("No groups yet")
    make_group(adi)
    ben.line("/groups")
    listing = ben.expect_text("Groups:")
    assert GROUP in listing["text"] and "member" in listing["text"]
    assert "✅ member" not in listing["text"]
    adi.line("/groups")
    assert "✅ member" in adi.expect_text("Groups:")["text"]


# ---------------------------------------------------------------- joining

def test_anyone_can_join_a_public_group(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    assert "ben" in state.groups[KEY]["members"]
    adi.expect_text("entered")


def test_joining_a_group_that_does_not_exist_is_an_error(user):
    adi = user("Adi")
    adi.line("/join Nowhere")
    adi.expect_text("No group called", kind="error")


def test_private_group_join_sends_a_request_and_notifies_the_owner(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi, private=True)
    ben.line(f"/join {GROUP}")
    ben.expect_text("Request sent")
    adi.expect_text("Ben wants to join", kind="event")
    assert state.groups[KEY]["requests"] == ["ben"]
    assert "ben" not in state.groups[KEY]["members"]


def test_asking_twice_to_join_says_the_request_is_waiting(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi, private=True)
    ben.line(f"/join {GROUP}")
    ben.expect_text("Request sent")
    ben.line(f"/join {GROUP}")
    ben.expect_text("still waiting")


def test_admins_are_notified_of_join_requests_too(user):
    adi, ben, cat = user("Adi"), user("Ben"), user("Cat")
    make_group(adi, private=True)
    ben.line(f"/join {GROUP}")
    adi.expect_text("Ben wants to join", kind="event")
    adi.line("/approve Ben")
    ben.expect_text("You were accepted", kind="event")
    join_group(ben)
    adi.line("/promote Ben")
    ben.expect_text("You're now an admin", kind="event")
    cat.line(f"/join {GROUP}")
    ben.expect_text("Cat wants to join", kind="event")


def test_owner_approves_a_request_and_the_player_can_then_join(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi, private=True)
    ben.line(f"/join {GROUP}")
    ben.expect_text("Request sent")
    adi.expect_text("wants to join")
    adi.line("/requests")
    adi.expect_text("Waiting: Ben")
    adi.line("/approve Ben")
    adi.expect_text("can now join")
    ben.expect_text("You were accepted", kind="event")
    join_group(ben)
    assert state.groups[KEY]["requests"] == []
    assert "ben" in state.groups[KEY]["members"]


def test_owner_rejects_a_request_and_the_player_is_told(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi, private=True)
    ben.line(f"/join {GROUP}")
    adi.expect_text("wants to join")
    adi.line("/reject Ben")
    adi.expect_text("Rejected")
    ben.expect_text("turned down", kind="error")
    assert "ben" not in state.groups[KEY]["members"]


def test_approve_and_requests_are_for_admins_only(user):
    adi, ben, cat = user("Adi"), user("Ben"), user("Cat")
    make_group(adi, private=True)
    state.groups[KEY]["members"].append("ben")
    join_group(ben)
    cat.line(f"/join {GROUP}")
    cat.expect_text("Request sent")
    ben.line("/requests")
    ben.expect_text("Only group admins", kind="error")
    ben.line("/approve Cat")
    ben.expect_text("Only group admins", kind="error")
    assert "cat" not in state.groups[KEY]["members"]


def test_requests_when_nobody_is_waiting(user):
    adi = user("Adi")
    make_group(adi, private=True)
    adi.line("/requests")
    adi.expect_text("No one is waiting")


# ---------------------------------------------------------------- chatting inside a group

def test_group_messages_stay_in_the_group(user):
    adi, ben, cat = user("Adi"), user("Ben"), user("Cat")
    make_group(adi)
    join_group(ben)
    adi.line("hello potatoes")
    ben.expect(lambda m: m.get("type") == "chat" and m.get("text") == "hello potatoes")
    cat.sync()  # Cat is still in the lobby
    adi.sync()
    assert not saw_chat(cat, "hello potatoes")


def test_lobby_messages_do_not_reach_the_group(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi)
    ben.line("hi lobby")
    ben.sync()
    adi.sync()
    assert not saw_chat(adi, "hi lobby")


def test_private_group_non_member_stays_in_the_lobby(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi, private=True)
    ben.line(f"/join {GROUP}")
    ben.expect_text("Request sent")
    ben.line("secret words")
    ben.sync()
    adi.sync()
    assert not saw_chat(adi, "secret words")
    ben.line("/members")
    ben.expect_text("You're in the lobby", kind="error")


def test_lobby_command_brings_you_back_to_the_lobby(user):
    adi = user("Adi")
    make_group(adi)
    adi.line("/lobby")
    enter_room(adi)
    adi.line("/lobby")
    adi.expect_text("already in the lobby")
    assert state.groups[KEY]["members"] == ["adi"]  # still a member


def test_members_lists_roles_and_online_status(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    adi.line("/members")
    listing = adi.expect_text("👥")["text"]
    assert "Adi" in listing and "👑 owner" in listing and "Ben" in listing


# ---------------------------------------------------------------- leaving

def test_a_member_can_leave_and_lands_in_the_lobby(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    ben.line("/leave")
    ben.expect_text("You left")
    assert "ben" not in state.groups[KEY]["members"]
    ben.line("/lobby")
    ben.expect_text("already in the lobby")


def test_the_owner_cannot_leave_and_must_disband(user):
    adi = user("Adi")
    make_group(adi)
    adi.line("/leave")
    adi.expect_text("Use /disband", kind="error")
    assert state.groups[KEY]["owner"] == "adi"


def test_leaving_from_the_lobby_asks_you_to_join_a_group(user):
    adi = user("Adi")
    adi.line("/leave")
    adi.expect_text("You're in the lobby", kind="error")


# ---------------------------------------------------------------- kick and ban

def test_admin_kicks_a_member_into_the_lobby(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    adi.line("/kick Ben")
    ben.expect_text("kicked", kind="error")
    assert "ben" not in state.groups[KEY]["members"]
    ben.line("/members")
    ben.expect_text("You're in the lobby", kind="error")


def test_a_kicked_player_can_join_a_public_group_again(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    adi.line("/kick Ben")
    ben.expect_text("kicked", kind="error")
    ben.line(f"/join {GROUP}")
    enter_room(ben)
    assert "ben" in state.groups[KEY]["members"]


def test_banned_player_cannot_rejoin_until_unbanned(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    adi.line("/ban Ben")
    ben.expect_text("banned", kind="error")
    ben.line(f"/join {GROUP}")
    ben.expect_text("You're banned", kind="error")
    adi.line("/unban Ben")
    adi.expect_text("is unbanned")
    join_group(ben)
    assert "ben" in state.groups[KEY]["members"]


def test_unbanning_someone_who_is_not_banned(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    adi.line("/unban Ben")
    adi.expect_text("isn't banned")


def test_ban_also_works_on_someone_who_is_not_a_member(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi)
    adi.line("/ban Ben")
    ben.expect_text("banned", kind="error")
    assert "ben" in state.groups[KEY]["banned"]


def test_members_cannot_kick_or_ban(user):
    adi, ben, cat = group_with_members(user, "Adi", "Ben", "Cat")
    ben.line("/kick Cat")
    ben.expect_text("Only group admins", kind="error")
    ben.line("/ban Cat")
    ben.expect_text("Only group admins", kind="error")
    assert "cat" in state.groups[KEY]["members"]
    assert state.groups[KEY]["banned"] == []


def test_nobody_can_act_against_the_owner_or_themselves(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    state.groups[KEY]["admins"].append("ben")
    ben.line("/kick Adi")
    ben.expect_text("can't do that to the owner", kind="error")
    ben.line("/kick Ben")
    ben.expect_text("yourself", kind="error")
    adi.line("/kick Nobody")
    adi.expect_text("No user called", kind="error")


def test_an_admin_cannot_kick_another_admin(user):
    adi, ben, cat = group_with_members(user, "Adi", "Ben", "Cat")
    state.groups[KEY]["admins"] += ["ben", "cat"]
    ben.line("/kick Cat")
    ben.expect_text("Only the owner", kind="error")
    assert "cat" in state.groups[KEY]["members"]


def test_kicking_someone_who_is_not_in_the_group(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi)
    adi.line("/kick Ben")
    adi.expect_text("isn't in this group", kind="error")


def test_admin_commands_do_not_work_from_the_lobby(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/kick Ben")
    adi.expect_text("You're in the lobby", kind="error")


# ---------------------------------------------------------------- mute

def test_muted_member_gets_an_error_and_the_group_does_not_see_the_message(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    adi.line("/mute Ben 10")
    ben.expect_text("muted for 10 min")
    ben.line("can anyone hear me")
    ben.expect_text("🔇", kind="error")
    adi.sync()
    assert not saw_chat(adi, "can anyone hear me")


def test_unmuted_member_can_talk_again(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    adi.line("/mute Ben")
    ben.expect_text("muted for 5 min")
    adi.line("/unmute Ben")
    ben.expect_text("can talk again")
    ben.line("back again")
    adi.expect(lambda m: m.get("type") == "chat" and m.get("text") == "back again")


def test_mute_time_is_limited_to_one_day(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    adi.line("/mute Ben 99999")
    adi.expect_text("muted for 1440 min")


def test_members_cannot_mute(user):
    adi, ben, cat = group_with_members(user, "Adi", "Ben", "Cat")
    ben.line("/mute Cat")
    ben.expect_text("Only group admins", kind="error")
    assert not state.mutes


# ---------------------------------------------------------------- promote and demote

def test_owner_promotes_and_demotes_an_admin(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    adi.line("/promote Ben")
    ben.expect_text("You're now an admin", kind="event")
    assert state.groups[KEY]["admins"] == ["ben"]
    adi.line("/promote Ben")
    adi.expect_text("already an admin")
    adi.line("/demote Ben")
    ben.expect_text("no longer an admin")
    assert state.groups[KEY]["admins"] == []
    adi.line("/demote Ben")
    adi.expect_text("isn't an admin")


def test_a_promoted_admin_can_kick(user):
    adi, ben, cat = group_with_members(user, "Adi", "Ben", "Cat")
    adi.line("/promote Ben")
    ben.expect_text("You're now an admin", kind="event")
    ben.line("/kick Cat")
    cat.expect_text("kicked", kind="error")


def test_only_the_owner_can_promote_or_demote(user):
    adi, ben, cat = group_with_members(user, "Adi", "Ben", "Cat")
    state.groups[KEY]["admins"].append("ben")
    ben.line("/promote Cat")
    ben.expect_text("Only the owner", kind="error")
    ben.line("/demote Cat")
    ben.expect_text("Only the owner", kind="error")
    assert state.groups[KEY]["admins"] == ["ben"]


def test_leaving_removes_admin_rights(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    adi.line("/promote Ben")
    ben.expect_text("You're now an admin", kind="event")
    ben.line("/leave")
    ben.expect_text("You left")
    assert state.groups[KEY]["admins"] == []


# ---------------------------------------------------------------- disband

def test_disband_removes_the_group_and_moves_members_to_the_lobby(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    adi.line("/disband")
    ben.expect_text("disbanded", kind="event")
    enter_room(ben)
    assert KEY not in state.groups
    ben.line("/members")
    ben.expect_text("You're in the lobby", kind="error")
    ben.line("/groups")
    ben.expect_text("No groups yet")


def test_only_the_owner_can_disband(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    state.groups[KEY]["admins"].append("ben")
    ben.line("/disband")
    ben.expect_text("Only the owner", kind="error")
    assert KEY in state.groups


def test_disband_pays_the_bank_to_the_owner(user):
    adi = user("Adi")
    make_group(adi)
    give_tokens("Adi", 0)
    state.groups[KEY]["bank"] = 120
    adi.line("/disband")
    adi.expect_text("120", kind="money")
    assert tokens("Adi") == 120


# ---------------------------------------------------------------- bank

def test_donate_moves_tokens_from_you_to_the_bank(user):
    adi = user("Adi")
    make_group(adi)
    give_tokens("Adi", 100)
    adi.line("/donate 30")
    adi.expect_text("donated 30", kind="money")
    assert tokens("Adi") == 70
    assert state.groups[KEY]["bank"] == 30


def test_donate_all_empties_your_balance_into_the_bank(user):
    adi = user("Adi")
    make_group(adi)
    give_tokens("Adi", 40)
    adi.line("/donate all")
    adi.expect_text("donated 40")
    assert tokens("Adi") == 0 and state.groups[KEY]["bank"] == 40


def test_donate_rejects_bad_amounts(user):
    adi = user("Adi")
    make_group(adi)
    give_tokens("Adi", 10)
    for bad, message in (("abc", "must be a number"), ("0", "more than 0"), ("11", "You only have 10")):
        adi.line(f"/donate {bad}")
        adi.expect_text(message, kind="error")
    assert tokens("Adi") == 10 and state.groups[KEY]["bank"] == 0


def test_bank_commands_need_a_group(user):
    adi = user("Adi")
    for command in ("/bank", "/donate 5", "/upgrade emoji", "/groupemoji 🔥"):
        adi.line(command)
        adi.expect_text("You're in the lobby", kind="error")


def test_bank_shows_balance_and_upgrade_prices(user):
    adi = user("Adi")
    make_group(adi)
    state.groups[KEY]["bank"] = 77
    adi.line("/bank")
    text = adi.expect_text("bank: 77", kind="money")["text"]
    for name, (_, price, _) in config.GROUP_UPGRADES.items():
        assert name in text and str(price) in text


def test_admin_buys_an_upgrade_with_the_bank(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    price = config.GROUP_UPGRADES["emoji"][1]
    state.groups[KEY]["bank"] = price + 10
    adi.line("/upgrade emoji")
    ben.expect_text("bought", kind="event")
    assert state.groups[KEY]["upgrades"] == ["emoji"]
    assert state.groups[KEY]["bank"] == 10
    adi.line("/upgrade emoji")
    adi.expect_text("already has that")


def test_upgrade_fails_when_the_bank_is_too_poor(user):
    adi = user("Adi")
    make_group(adi)
    state.groups[KEY]["bank"] = 5
    adi.line("/upgrade income")
    adi.expect_text("costs", kind="error")
    assert state.groups[KEY]["upgrades"] == [] and state.groups[KEY]["bank"] == 5


def test_non_admin_cannot_spend_the_bank(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    state.groups[KEY]["bank"] = 1000
    ben.line("/upgrade emoji")
    ben.expect_text("Only group admins can spend", kind="error")
    assert state.groups[KEY]["bank"] == 1000 and state.groups[KEY]["upgrades"] == []


def test_upgrade_with_an_unknown_name_shows_the_bank(user):
    adi = user("Adi")
    make_group(adi)
    adi.line("/upgrade rocket")
    adi.expect_text("Upgrades:", kind="money")


def test_group_emoji_needs_the_upgrade_and_then_shows_in_the_name(user):
    adi = user("Adi")
    make_group(adi)
    adi.line("/groupemoji 🔥")
    adi.expect_text("Buy the emoji upgrade first", kind="error")
    state.groups[KEY]["bank"] = config.GROUP_UPGRADES["emoji"][1]
    adi.line("/upgrade emoji")
    adi.expect_text("Now pick it")
    adi.line("/groupemoji 🔥")
    adi.expect_text("🔥 #Potatoes", kind="event")
    assert state.groups[KEY]["emoji"] == "🔥"


def test_group_emoji_rejects_ordinary_text(user):
    adi = user("Adi")
    make_group(adi)
    state.groups[KEY]["upgrades"].append("emoji")
    adi.line("/groupemoji hello")
    adi.expect_text("Send a single emoji", kind="error")
    assert state.groups[KEY]["emoji"] == ""


def test_members_cannot_set_the_group_emoji(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    state.groups[KEY]["upgrades"].append("emoji")
    ben.line("/groupemoji 🔥")
    ben.expect_text("Only group admins", kind="error")


def test_topgroups_ranks_by_bank(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/topgroups")
    adi.expect_text("No groups yet")
    make_group(adi)
    ben.line("/create Rich")
    ben.expect_text("Created")
    state.groups[KEY]["bank"] = 10
    state.groups["rich"]["bank"] = 500
    ben.line("/topgroups")
    text = ben.expect_text("Richest groups", kind="money")["text"]
    assert text.index("Rich") < text.index("Potatoes")
    assert "500" in text
