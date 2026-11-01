"""
🏢 The daily tick: once a day after VENTURES_TICK_HOUR (Israel time) every live company lives one game day
(ventures_sim.next_day), gets its report in its chat, refills its action points; broke companies go on fumes, then
die. Called every minute from background.market_loop (holding the lock). If the server was off, the missed days
don't count: the next tick is simply the next game day.
"""
import random
import time
import traceback
from datetime import timedelta

from chatserver import (config, invites, rooms, state, storage, textutil, ventures_deals, ventures_events, ventures_exits,
                        ventures_log, ventures_news, ventures_season, ventures_sectors, ventures_sim, ventures_store,
                        ventures_team)
from chatserver.hashbrown_text import israel_now
from chatserver.ventures_text import money

_after_tick = []   # more daily jobs (funding rounds, events...) register here: job(tick)


def on_tick(job):
    _after_tick.append(job)


def maybe_run():
    """Run the tick if today's hasn't run yet and it's late enough."""
    now = israel_now()
    today = now.date().isoformat()
    ventures = ventures_store.ensure()
    if ventures["day"] == today or now.hour < config.VENTURES_TICK_HOUR:
        return False
    ventures_store.set_field("day", today)
    run_tick()
    return True


def next_tick_at():
    """When the next daily tick runs, as a Unix time (for the website's countdown)."""
    now = israel_now()
    target = now.replace(hour=config.VENTURES_TICK_HOUR, minute=0, second=0, microsecond=0)
    if ventures_store.ensure()["day"] == now.date().isoformat():
        target += timedelta(days=1)
    elif now >= target:
        return int(time.time()) + 60   # due now: within the minute
    return int(time.time() + (target - now).total_seconds())


def run_tick(rng=None):
    """One game day for every live company (the console's "ventures tick" calls this directly)."""
    rng = rng or random.Random()
    tick = ventures_store.ensure()["tick"] + 1
    ventures_store.set_field("tick", tick)
    ventures_events.expire()
    world = make_world(tick)
    for co in sorted(ventures_store.alive(), key=lambda c: c["id"]):
        try:
            live_one_day(co, rng, tick, world)
        except Exception:   # one broken record must not stop every other company's day
            textutil.log(f"[VENTURES] ⚠️ The tick failed for {co.get('name')!r}:\n{traceback.format_exc()}")
    for job in list(_after_tick):
        try:
            job(tick)
        except Exception:
            textutil.log(f"[VENTURES] ⚠️ A daily job failed:\n{traceback.format_exc()}")
    drop_old_offers()
    ventures_exits.pay_queue()   # 🚪 exits that waited for the fund
    ventures_season.maybe_end(tick)   # 🏛️ the season's last day
    storage.save_data()


def make_world(tick):
    """What every company's day depends on: the market events, the mood and the Spud-Bench ranks."""
    events, mood, _, _ = ventures_events.world_effects()
    _, boost = ventures_sectors.bench(ventures_store.alive(), tick)
    return {"tick": tick, "events": events, "mood": mood, "bench": boost, "crowd": ventures_deals.crowd(ventures_store.alive())}


def drop_old_offers():
    """Team offers whose invite ran out are forgotten."""
    for co in ventures_store.alive():
        kept = {k: o for k, o in co["offers"].items() if time.time() - o.get("at", 0) < invites.LIFETIME}
        if kept != co["offers"]:
            ventures_store.put({**co, "offers": kept})


def live_one_day(co, rng, tick, world=None):
    players = max(1, len(ventures_store.members(co)))
    new, lines = ventures_sim.next_day(co, rng, players, world=world or {"tick": tick})
    news = new.pop("_news", [])
    online = [login for login in ventures_store.members(new) if login in state.online]
    if new["status"] == "alive":
        bonus = max(0, len(online) - 1)
        new = {**new, "ap": min(config.AP_MAX, config.AP_BASE + bonus), "seen": online}
        lines = lines + [next_round_line(new, players)]
    text = "\n".join(lines)
    reports = (new["reports"] + [{"age": new["age"], "text": text}])[-config.REPORTS_KEPT:]
    new = ventures_store.put({**new, "report": text, "reports": reports})
    ventures_log.record_day(new)
    ventures_team.post_to_company(new, text)
    ventures_team.send_event(new, "report", text)
    if new["fumes"] and new["status"] == "alive":
        for login in ventures_store.members(new):
            rooms.tell(login, f"🚨 {new['name']} is on fumes! Raise money or cut costs before the next tick.", "error")
    for headline in news:
        ventures_news.add("sector", headline, new)
    if new["status"] == "dead":
        if (new.get("ipo") or {}).get("symbol"):
            ventures_deals.delist(new, "the company died")
        ventures_team.bury(new, "died")


def next_round_line(co, players, when="today."):
    """"⚡ 4 action points today. Next round (Seed) needs: MRR $10K (now $4.2K) ❌ ..."."""
    points = "1 action point" if co["ap"] == 1 else f"{co['ap']} action points"
    rows = ventures_sim.milestones(co, players)
    if not rows:
        return f"⚡ {points} {when}"
    goal = "the IPO" if co["stage"] == "c" else config.STAGE_NAMES[config.STAGES[config.STAGES.index(co["stage"]) + 1]]
    parts = [milestone_text(r) for r in rows]
    return f"⚡ {points} {when} Next round ({goal}) needs: " + " · ".join(parts)


def milestone_text(r):
    mark = "✅" if r["ok"] else "❌"
    if r["what"] in ("MRR", "valuation"):
        return f"{r['what']} {money(r['need'])} (now {money(r['have'])}) {mark}"
    if r["what"] == "ticks":
        return f"{r['need']} days in this stage (now {r['have']}) {mark}"
    if r["what"] == "profit":
        return f"revenue ≥ {r['need']}% of burn (now {r['have']:.0f}%) {mark}"
    return f"{r['what']} {r['need']} (now {r['have']:.0f}) {mark}"
