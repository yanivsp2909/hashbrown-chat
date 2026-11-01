"""
🏛️ Seasons and the boards (docs/VENTURES.md, 9.6-9.7): a season lasts SEASON_TICKS game days. At its end every
private company pays its holders SEASON_END_PAYOUT_PERCENT of an exit, public ones are delisted, the Hall of Fame
keeps the winners, every company is archived (its chat stays) and a new season starts at the next tick.
"""
from chatserver import (achievements, cap_table, config, rooms, state, storage, ventures_deals, ventures_exits,
                        ventures_news, ventures_sectors, ventures_store)
from chatserver.ventures_text import money


def investors_board(limit=10):
    """Angels by how their tokens did: (paper value of their stakes + exits received) / tokens put in."""
    rows = {}
    for co in ventures_store.companies().values():
        for login, tokens in co["angel_in"].items():
            row = rows.setdefault(login, {"login": login, "tokens_in": 0, "paper": 0})
            row["tokens_in"] += tokens
            if co["status"] == "alive":
                bp = co["cap"].get(cap_table.player(login), 0)
                row["paper"] += ventures_exits.tokens_for(bp, co["valuation"])[2]
    board = []
    for login, row in rows.items():
        got = ventures_exits.received(login, ventures_store.ensure()["season"])
        board.append({"name": rooms.nick(login) if login in state.accounts else login, "tokens_in": row["tokens_in"],
                      "value": row["paper"] + got, "multiple": round((row["paper"] + got) / max(1, row["tokens_in"]), 2)})
    return sorted(board, key=lambda r: -r["multiple"])[:limit]


def maybe_end(tick):
    """After a tick: the season's last day ends it."""
    if tick >= config.SEASON_TICKS:
        end_season()


def end_season():
    ventures = ventures_store.ensure()
    season = ventures["season"]
    companies = list(ventures_store.companies().values())
    fame = awards(season, companies)
    for co in ventures_store.alive():
        # closed BEFORE anyone is paid: if something breaks halfway, nobody is paid twice
        ended = ventures_store.put({**co, "status": "ended", "cause": f"season {season} ended"})
        if co["stage"] == "public":
            ventures_deals.delist(ended, "the season ended")
        else:
            ventures_exits.pay_exit(ended, co["valuation"], "season end", config.SEASON_END_PAYOUT_PERCENT)
    ventures_store.set_field("fame", ventures_store.ensure()["fame"] + fame)
    for entry in fame:
        if entry.get("login") in state.accounts and entry["award"] == "Most valuable company":
            achievements.unlock(entry["login"], "ventures_champion")
    ventures_news.add("season", f"🏛️ Season {season} is over! " + "; ".join(f"{e['award']}: {e['name']}" for e in fame[:3]),
                      big=True)
    ventures_store.set_field("season", season + 1)
    ventures_store.set_field("tick", 0)
    ventures_store.set_field("cooldowns", {})
    ventures_store.set_field("events", [])
    ventures_store.set_field("minted", 0)
    ventures_store.set_field("acquisitions", {})
    ventures_store.set_field("partner_offers", {})
    rooms.announce(f"🏛️ A new Ventures season starts: season {season + 1}. Everyone can found a company again!")
    storage.save_data()


def awards(season, companies):
    """The Hall of Fame entries of a season."""
    this = [co for co in companies if co.get("season", 1) == season]
    exits = [e for e in ventures_store.ensure().get("exits", []) if e["season"] == season]
    fame = []
    alive = [co for co in this if co["status"] == "alive"]
    if alive:
        best = max(alive, key=lambda co: co["valuation"])
        fame.append(entry(season, "Most valuable company", best["name"], ventures_store_ceo(best), money(best["valuation"])))
    if exits:
        big = max(exits, key=lambda e: e["value"])
        fame.append(entry(season, "Biggest exit", big["name"], "", f"{big['kind']} at {money(big['value'])}"))
        founders = {}
        for e in exits:
            for p in e["paid"]:
                founders[p["login"]] = founders.get(p["login"], 0) + p["tokens"]
        login, tokens = max(founders.items(), key=lambda item: item[1])
        fame.append(entry(season, "Best founder", rooms.nick(login) if login in state.accounts else login, login, f"{tokens:,} 🪙 from exits"))
    board = investors_board(1)
    if board:
        fame.append(entry(season, "Best investor", board[0]["name"], "", f"{board[0]['multiple']}x"))
    dead = [co for co in this if co["status"] in ("dead", "shutdown")]
    if dead:
        flop = max(dead, key=lambda co: co["raised"])
        fame.append(entry(season, "Most raised before dying", flop["name"], "", money(flop["raised"])))
    rows, _ = ventures_sectors.bench(alive, ventures_store.ensure()["tick"])
    champ = next((r for r in rows if not r["npc"]), None)
    if champ:
        fame.append(entry(season, "Spud-Bench champion", champ["lab"], "", f"{champ['name']}: {champ['score']}"))
    return fame


def ventures_store_ceo(co):
    from chatserver.ventures_team import ceo_of
    return ceo_of(co)


def entry(season, award, name, login, text):
    return {"season": season, "award": award, "name": name, "login": login, "text": text}
