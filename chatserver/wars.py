"""
⚔️ Group wars: two groups agree to a war; for WAR_MINUTES, every match a member of one group wins against
a member of the other scores a point. At the end the winner takes WAR_PRIZE from the loser's bank.
The commands are in cmd_wars.py; scoring hooks into every finished match (matches.finish_hooks).
"""
import time

from chatserver import bank_log, config, matches, rooms, state, storage


def war_of(group_key):
    return next((war for war in state.wars if group_key in (war["a"], war["b"])), None)


def tell_group(group_key, text):
    for member in state.groups.get(group_key, {}).get("members", []):
        rooms.tell(member, text, "event")


def start_war(a, b):
    war = {"a": a, "b": b, "points": {a: 0, b: 0}, "until": time.time() + config.WAR_MINUTES * 60}
    state.wars.append(war)
    for key in (a, b):
        tell_group(key, f"⚔️ The war is on: {rooms.room_title(a)} vs {rooms.room_title(b)} for "
                        f"{config.WAR_MINUTES} min! Win games against the other group. The winner takes "
                        f"{config.WAR_PRIZE} 🪙 from the loser's bank.")


def score(match, winner):
    """After every match: a win against a member of the enemy group is a point."""
    if winner in ("draw", None) or not matches.was_played(match):
        return
    loser = match.opponent(winner)
    for war in state.wars:
        for side, enemy in ((war["a"], war["b"]), (war["b"], war["a"])):
            mine, theirs = state.groups.get(side), state.groups.get(enemy)
            if mine and theirs and winner in mine["members"] and loser in theirs["members"] \
                    and winner not in theirs["members"]:
                war["points"][side] += 1
                rooms.tell(winner, f"⚔️ +1 for {rooms.room_title(side)} in the war!", "event")


def score_text(war):
    a, b = war["a"], war["b"]
    left = max(0, int(war["until"] - time.time()) // 60)
    return (f"⚔️ {rooms.room_title(a)} vs {rooms.room_title(b)}: {rooms.room_title(a)} {war['points'][a]}, "
            f"{rooms.room_title(b)} {war['points'][b]} ({left} min left)")


def end_war(war):
    if war in state.wars:
        state.wars.remove(war)
    a, b = war["a"], war["b"]
    if a not in state.groups or b not in state.groups:
        return  # a group was disbanded during the war
    if war["points"][a] == war["points"][b]:
        text = f"⚔️ The war {rooms.room_title(a)} vs {rooms.room_title(b)} ended in a tie. Nobody pays."
    else:
        winner, loser = (a, b) if war["points"][a] > war["points"][b] else (b, a)
        prize = min(config.WAR_PRIZE, state.groups[loser]["bank"])
        state.groups[loser]["bank"] -= prize
        state.groups[winner]["bank"] += prize
        bank_log.record(winner, "war_won", "", prize, state.groups[loser]["name"])
        bank_log.record(loser, "war_lost", "", -prize, state.groups[winner]["name"])
        storage.save_data()
        text = (f"🏆 {rooms.room_title(winner)} won the war against {rooms.room_title(loser)} "
                f"({war['points'][winner]} to {war['points'][loser]}) and took {prize} 🪙 from their bank!")
    for key in (a, b):
        tell_group(key, text)


def forget_group(key):
    """A group was disbanded: its war ends with no winner, and its war invites go."""
    for war in [w for w in state.wars if key in (w["a"], w["b"])]:
        state.wars.remove(war)
        other = war["b"] if war["a"] == key else war["a"]
        tell_group(other, "⚔️ The war is over: the other group was disbanded. Nobody pays.")
    for target, (attacker, _) in list(state.war_invites.items()):
        if key in (target, attacker):
            del state.war_invites[target]


def end_due():
    """Called once a minute: end the wars whose time is up."""
    now = time.time()
    for war in list(state.wars):
        if war["until"] <= now:
            end_war(war)


matches.finish_hooks.append(score)
