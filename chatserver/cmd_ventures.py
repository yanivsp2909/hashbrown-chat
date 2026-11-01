"""
🦄 /ventures: the boards of Hashbrown Ventures (the Unicorn Board, the graveyard).
"""
from chatserver import config, registry, rooms, ventures_store
from chatserver.ventures_text import money, sector_title, stage_name


@registry.command("/ventures", "/ventures [board | graveyard]", "🦄 the startup boards", "🏢 Ventures")
def cmd_ventures(client, args):
    sub = args.strip().lower()
    if sub in ("graveyard", "grave", "dead"):
        return client.say(graveyard_text())
    client.say(board_text())


def board_text():
    ventures = ventures_store.ensure()
    live = sorted(ventures_store.alive(), key=lambda co: -co["valuation"])
    head = f"🦄 Unicorn Board · season {ventures['season']}, day {ventures['tick']} of {config.SEASON_TICKS}"
    if not live:
        return f"{head}\n  No companies yet. Found one: /company found name sector"
    lines = [head]
    for place, co in enumerate(live[:15], 1):
        horn = " 🦄" if co["valuation"] >= 1_000_000_000 else ""
        founders = ", ".join(rooms.nick(k) for k in ventures_store.members(co))
        lines.append(f"  {place}. {co['name']} {sector_title(co['sector'])} · {stage_name(co['stage'])} · "
                     f"{money(co['valuation'])}{horn}  ({founders})")
    lines.append("More: /company info name · /ventures graveyard")
    return "\n".join(lines)


def graveyard_text():
    graves = ventures_store.ensure()["graveyard"]
    if not graves:
        return "⚰️ The graveyard is empty. For now."
    lines = ["⚰️ The startup graveyard:"]
    for g in reversed(graves[-15:]):
        lines.append(f"  🪦 {g['name']} ({sector_title(g['sector'])}, {stage_name(g['stage'])}) {g['how']} after "
                     f"{g['lived']} days, peak {money(g['peak'])}: {g['cause']}. “{g['epitaph']}”")
    return "\n".join(lines)
