"""
📊 Polls: /poll question | option | option, /vote number, /poll (see the votes), /endpoll.
One poll per room. The poll message also carries "poll": {question, options} so the website can show buttons.
"""
from chatserver import registry, rooms, state

USAGE = "Use: /poll question | option | option (2 to 6 options)"


def results(poll):
    counts = [list(poll["votes"].values()).count(i) for i in range(len(poll["options"]))]
    lines = [f"  {option}: {count}" for option, count in zip(poll["options"], counts)]
    return counts, "\n".join(lines)


@registry.command("/poll", "/poll question | a | b", "ask the room to vote 📊 (/poll alone: the votes)", "💬 Chat")
def cmd_poll(client, args):
    poll = state.polls.get(client.room)
    if not args.strip():
        if poll is None:
            client.say(USAGE, "error")
        else:
            client.say(f"📊 {poll['question']}\n{results(poll)[1]}")
        return
    parts = [p.strip() for p in args.split("|")]
    question, options = parts[0], [o for o in parts[1:] if o]
    if not question or not 2 <= len(options) <= 6:
        client.say(USAGE, "error")
        return
    if poll is not None:
        client.say("📊 There's already a poll here. /endpoll it first (whoever made it can).", "error")
        return
    state.polls[client.room] = {"by": client.key, "question": question, "options": options, "votes": {}}
    numbered = "\n".join(f"  {i}) {option}" for i, option in enumerate(options, 1))
    rooms.send_room(client.room, {"type": "msg", "kind": "event",
                                  "text": f"📊 Poll by {rooms.nick(client.key)}: {question}\n{numbered}\n"
                                          f"Vote with /vote 1-{len(options)}",
                                  "poll": {"question": question, "options": options}})


@registry.command("/vote", "/vote number", "vote in the room's poll", "💬 Chat")
def cmd_vote(client, args):
    poll = state.polls.get(client.room)
    if poll is None:
        client.say("📊 No poll here. Start one with /poll question | a | b", "error")
        return
    choice = args.strip()
    if not choice.isdecimal() or not 1 <= int(choice) <= len(poll["options"]):
        client.say(f"📊 Use /vote 1-{len(poll['options'])}", "error")
        return
    poll["votes"][client.key] = int(choice) - 1   # voting again changes your vote
    client.say(f"🗳️ You voted for {poll['options'][int(choice) - 1]}.")


@registry.command("/endpoll", "/endpoll", "close your poll and show who won", "💬 Chat")
def cmd_endpoll(client, args):
    poll = state.polls.get(client.room)
    if poll is None:
        client.say("📊 No poll here.", "error")
        return
    group = state.groups.get(client.room)
    if client.key != poll["by"] and not (group and rooms.is_admin(group, client.key)):
        client.say(f"📊 Only {rooms.nick(poll['by'])} (or a group admin) can end this poll.", "error")
        return
    del state.polls[client.room]
    counts, lines = results(poll)
    best = max(counts)
    winners = [option for option, count in zip(poll["options"], counts) if count == best]
    verdict = "nobody voted" if best == 0 else (f"{winners[0]} wins" if len(winners) == 1 else "it's a tie")
    rooms.notify_room(client.room, f"📊 Poll closed: {poll['question']}\n{lines}\n🏁 {verdict}!", kind="event")
