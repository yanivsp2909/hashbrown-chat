"""
💰 Raising money: /pitch (the AI investor), /offer (term sheets) and /invest (angel investing).
The rules are in ventures_pitch.py, ventures_rounds.py and ventures_angels.py (docs/VENTURES.md, section 6).
"""

from chatserver import registry, storage, ventures_angels, ventures_pitch, ventures_rounds, ventures_store, ventures_team

NOT_IN_ONE = "🏢 You're not in a company. Found one: /company found name sector"


@registry.command("/pitch", "/pitch [send | stop | your words]", "🎤 pitch an investor for your next round",
                  "🏢 Ventures")
def cmd_pitch(client, args):
    co = ventures_team.saw(client.key)
    if co is None:
        return client.say(NOT_IN_ONE, "error")
    words = args.strip()
    if words == "":
        return ventures_pitch.start(client, co)
    if words.lower() == "send":
        return ventures_pitch.send(client, co)
    if words.lower() == "stop":
        return ventures_pitch.stop(client, co)
    if not co["pitch"]:
        return client.say("🎤 No pitch is going on. /pitch starts one.", "error")
    ventures_pitch.send(client, co, words)


@registry.command("/offer", "/offer [accept | decline | counter valuation]", "📄 answer a term sheet (the CEO)",
                  "🏢 Ventures")
def cmd_offer(client, args):
    co = ventures_team.saw(client.key)
    if co is None:
        return client.say(NOT_IN_ONE, "error")
    ventures_rounds.expire_due()
    co = ventures_store.get(co["id"])
    sub, _, rest = args.strip().partition(" ")
    if not co["sheet"]:
        return client.say("📄 No term sheet is waiting. /pitch an investor to get one.", "error" if sub else "system")
    if sub == "":
        return client.say(ventures_rounds.card(co["sheet"])[0])
    if ventures_team.ceo_of(co) != client.key:
        return client.say("👑 Only the CEO can answer a term sheet.", "error")
    sub = sub.lower()
    if rest and sub in ("accept", "decline") and rest != co["sheet"]["id"]:   # (a button for an older sheet)
        return client.say("📄 That term sheet isn't open any more. /offer shows the one that is.", "error")
    if sub == "accept":
        return ventures_rounds.take_offer(client, co)
    if sub == "decline":
        ventures_rounds.close_sheet(co, "declined")
        line = f"👎 {co['name']} said no to {ventures_rounds.investor_title(co['sheet']['investor'])}'s term sheet."
        ventures_team.tell_company(co, line)
        if client.room != co["group"]:
            client.say(line)
        return storage.save_data()
    if sub == "counter":
        return ventures_rounds.counter(client, co, rest)
    client.say("Usage: /offer accept · /offer decline · /offer counter 15M", "error")


@registry.command("/invest", "/invest company tokens | cancel company", "😇 angel-invest your 🪙 in an early startup",
                  "🏢 Ventures")
def cmd_invest(client, args):
    ventures_angels.offer(client, args)
