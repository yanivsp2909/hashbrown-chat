"""👥 The website's Groups screen: {"type": "get_groups"} -> {"type": "groups"} (one card per group) and
{"type": "get_group", "group"} -> {"type": "group_info"} (members, bank, upgrades, war, and admin-only parts).
Every button on the screen sends the existing /commands; these packets only SHOW things.
Privacy: a private group you're not in shows only its name, emoji and size; only admins get admin data."""
import time

import pytest

from chatserver import bank_log, config, group_view, state, wars

pytestmark = pytest.mark.integration


def make_group(owner, name="Potatoes", private=False):
    owner.line(f"/create {name}{' private' if private else ''}")
    owner.expect_text("Created")


def groups(client):
    client.send({"type": "get_groups"})
    return client.expect(lambda m: m.get("type") == "groups")["groups"]


def info(client, key="potatoes"):
    client.send({"type": "get_group", "group": key})
    return client.expect(lambda m: m.get("type") == "group_info")["group"]


def card_of(cards, key):
    return next(c for c in cards if c["key"] == key)


# ---------------------------------------------------------------- the list

def test_cards_mine_first_with_role_counts_and_bank(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi)
    make_group(ben, "Chess")
    state.groups["potatoes"]["bank"] = 420
    cards = groups(adi)
    assert [c["key"] for c in cards] == ["potatoes", "chess"]          # mine first
    mine = card_of(cards, "potatoes")
    assert (mine["your_role"], mine["members"], mine["online"], mine["bank"]) == ("owner", 1, 1, 420)
    assert card_of(cards, "chess")["your_role"] == "none"


def test_a_private_group_youre_not_in_shows_almost_nothing(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi, "Secret", private=True)
    adi.line("/pin our plans")
    adi.expect_text("pinned")
    secret = card_of(groups(ben), "secret")
    assert secret["private"] is True and secret["members"] == 1
    for hidden in ("topic", "bank", "upgrades", "persona"):
        assert hidden not in secret
    details = info(ben, "secret")
    for hidden in ("members_list", "bank", "bank_details", "war", "admin"):
        assert hidden not in details


def test_requesting_shows_as_requested(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi, "Secret", private=True)
    ben.line("/join Secret")
    ben.expect_text("Request sent")
    assert card_of(groups(ben), "secret")["your_role"] == "requested"


# ---------------------------------------------------------------- one group

def test_members_with_roles_and_online(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi)
    ben.line("/join Potatoes")
    ben.expect(lambda m: m.get("type") == "history" and m.get("key") == "potatoes")
    details = info(ben)
    assert {(m["name"], m["role"], m["online"]) for m in details["members_list"]} == {("Adi", "owner", True),
                                                                                       ("Ben", "member", True)}
    assert details["admins"] == ["Adi"]


def test_only_admins_get_the_admin_part(user):
    adi, ben, cat = user("Adi"), user("Ben"), user("Cat")
    make_group(adi, "Secret", private=True)
    cat.line("/join Secret")
    cat.expect_text("Request sent")
    adi.line("/approve Cat Secret")
    cat.expect_text("accepted into")
    ben.line("/join Secret")
    ben.expect_text("Request sent")
    admin = info(adi, "secret")["admin"]
    assert admin["requests"] == ["Ben"] and admin["banned"] == [] and admin["muted"] == []
    assert "admin" not in info(cat, "secret")                          # a plain member


def test_a_promoted_admin_gets_it_too(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi)
    ben.line("/join Potatoes")
    ben.expect(lambda m: m.get("type") == "history" and m.get("key") == "potatoes")
    adi.line("/promote Ben")
    adi.expect_text("admin")
    assert "admin" in info(ben)


def test_upgrades_all_listed_with_their_state(user):
    adi = user("Adi")
    make_group(adi)
    group = state.groups["potatoes"]
    group["upgrades"] = ["emoji"]
    group["bank"] = 200
    upgrades = {u["name"]: u for u in info(adi)["upgrades"]}
    assert set(upgrades) == set(config.GROUP_UPGRADES)
    assert upgrades["emoji"]["state"] == "owned"
    assert upgrades["history"]["state"] == "can_buy"                  # 200 = its price
    assert upgrades["income"]["state"] == "locked" and upgrades["income"]["missing"] == 100
    assert upgrades["income"]["price"] == 300 and upgrades["income"]["icon"] == "💰" and upgrades["income"]["does"]


def test_bank_earnings_now_and_why(user):
    adi = user("Adi")
    make_group(adi)
    state.groups["potatoes"]["upgrades"] = ["income"]
    bank = info(adi)["bank_details"]
    assert bank["per_minute"] == config.GROUP_INCOME and bank["members_online"] == 1 and bank["income_upgrade"] is True


def test_non_members_of_a_public_group_dont_get_the_bank_details(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi)
    details = info(ben)
    assert "bank_details" not in details and details["your_role"] == "none"
    assert len(details["upgrades"]) == len(config.GROUP_UPGRADES)     # the shop is public


# ---------------------------------------------------------------- 🏦 the bank's history (saved in history.db)

def test_donations_and_purchases_are_in_the_history_newest_first(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi)
    ben.line("/join Potatoes")
    ben.expect(lambda m: m.get("type") == "history" and m.get("key") == "potatoes")
    ben.line("/donate 60")
    ben.expect_text("donated 60")
    state.accounts["adi"]["tokens"] = 1000
    adi.line("/donate 300")
    adi.expect_text("donated 300")
    adi.line("/upgrade emoji")
    adi.expect_text("bought")
    bank = info(adi)["bank_details"]
    kinds = [(row["kind"], row["who"], row["amount"]) for row in bank["history"]]
    assert kinds[:3] == [("upgrade", "Adi", -150), ("donate", "Adi", 300), ("donate", "Ben", 60)]
    assert bank["history"][0]["note"] == "emoji" and bank["history"][0]["balance"] == 210
    assert bank["top_donors"] == [{"name": "Adi", "amount": 300}, {"name": "Ben", "amount": 60}]


def test_war_prizes_are_in_both_histories(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi, "Red")
    make_group(ben, "Blue")
    state.groups["blue"]["bank"] = 500
    adi.line("/war Blue")
    ben.expect_text("declared war")
    ben.line("/war accept Red")
    adi.expect_text("war is on")
    war = state.wars[0]
    war["points"] = {"red": 2, "blue": 0}
    with state.lock:
        wars.end_war(war)
    red = info(adi, "red")["bank_details"]["history"][0]
    blue = info(ben, "blue")["bank_details"]["history"][0]
    assert (red["kind"], red["amount"]) == ("war_won", config.WAR_PRIZE)
    assert (blue["kind"], blue["amount"]) == ("war_lost", -config.WAR_PRIZE)


def test_the_history_survives_a_restart_and_a_new_group_starts_empty(user):
    adi = user("Adi")
    make_group(adi)
    adi.line("/donate 10")
    adi.expect_text("donated 10")
    from chatserver import history
    history.close()                                       # like a restart: the file stays
    assert bank_log.recent("potatoes")[0]["amount"] == 10
    adi.line("/disband")
    adi.expect_text("disbanded")
    adi.line("/users")                                    # (the notice comes before the server is done)
    adi.expect_text("Online now")
    assert bank_log.recent("potatoes") == []


def test_balance_points_for_the_chart(user):
    adi = user("Adi")
    make_group(adi)
    state.groups["potatoes"]["bank"] = 70
    with state.lock:
        bank_log.snapshot_all(now=time.time())
        bank_log.snapshot_all(now=time.time() + 60)          # less than an hour later: no second point
    points = info(adi)["bank_details"]["chart"]
    assert [p["balance"] for p in points] == [70, 70]           # the snapshot, then the balance now


# ---------------------------------------------------------------- buying stays the server's decision

def test_a_member_cant_buy_even_by_typing_the_command(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi)
    ben.line("/join Potatoes")
    ben.expect(lambda m: m.get("type") == "history" and m.get("key") == "potatoes")
    state.groups["potatoes"]["bank"] = 1000
    ben.line("/upgrade income")
    ben.expect_text("Only group admins", kind="error")
    assert state.groups["potatoes"]["upgrades"] == [] and state.groups["potatoes"]["bank"] == 1000
    assert all(row["kind"] != "upgrade" for row in info(ben)["bank_details"]["history"])


# ---------------------------------------------------------------- updates and old clients

def test_an_open_screen_gets_updates_and_a_closed_one_doesnt(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi)
    info(ben)                                              # Ben looks at Potatoes
    ben.line("/join Potatoes")
    ben.expect(lambda m: m.get("type") == "history" and m.get("key") == "potatoes")
    with state.lock:
        group_view.push_updates()
    fresh = ben.expect(lambda m: m.get("type") == "group_info" and m["group"]["members"] == 2)
    assert fresh["group"]["your_role"] == "member"
    ben.send({"type": "groups_closed"})
    ben.line("/users")
    ben.expect_text("Online now")
    count = len([m for m in ben.messages if m.get("type") in ("groups", "group_info")])
    with state.lock:
        group_view.mark_dirty()
        group_view.push_updates()
    ben.line("/users")
    ben.expect_text("Online now")
    assert len([m for m in ben.messages if m.get("type") in ("groups", "group_info")]) == count


def test_old_clients_never_get_these_packets(user):
    adi, old = user("Adi"), user("Old")
    make_group(adi)
    with state.lock:
        group_view.mark_dirty()
        group_view.push_updates()
    old.line("/users")
    old.expect_text("Online now")
    assert not [m for m in old.messages if m.get("type") in ("groups", "group_info")]


def test_asking_about_a_group_that_doesnt_exist(user):
    adi = user("Adi")
    adi.send({"type": "get_group", "group": "nope"})
    adi.expect_text("No group", kind="error")
    adi.send({"type": "get_group", "group": ["x"]})
    adi.expect_text("No group", kind="error")


def test_donation_spam_doesnt_grow_the_chart(user):
    """Security review: the chart is built from hourly snapshots only (at most BANK_CHART_POINTS)."""
    adi = user("Adi")
    make_group(adi)
    state.accounts["adi"]["tokens"] = 1000
    for _ in range(20):
        adi.line("/donate 1")
    adi.line("/users")
    adi.expect_text("Online now")
    assert len(info(adi)["bank_details"]["chart"]) == 1


def test_a_private_group_doesnt_show_who_is_online_to_outsiders(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi, "Secret", private=True)
    assert "online" not in card_of(groups(ben), "secret")


def test_an_unchanged_screen_isnt_sent_again(user):
    adi = user("Adi")
    make_group(adi)
    info(adi)
    before = len([m for m in adi.messages if m.get("type") == "group_info"])
    with state.lock:
        group_view.mark_dirty()
        group_view.push_updates()
    adi.line("/users")
    adi.expect_text("Online now")
    assert len([m for m in adi.messages if m.get("type") == "group_info"]) == before
