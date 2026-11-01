"""
🏢 The daily tick: once a day after VENTURES_TICK_HOUR (Israel time) every live company lives one game day
(ventures_sim.next_day), gets its report in its chat, refills its action points; broke companies go on fumes, then
die. Called every minute from background.market_loop (holding the lock). If the server was off, the missed days
don't count: the next tick is simply the next game day.
"""
import random

from chatserver import config, rooms, state, storage, ventures_log, ventures_sim, ventures_store, ventures_team
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


def run_tick(rng=None):
    """One game day for every live company (the console's "ventures tick" calls this directly)."""
    rng = rng or random.Random()
    tick = ventures_store.ensure()["tick"] + 1
    ventures_store.set_field("tick", tick)
    for co in sorted(ventures_store.alive(), key=lambda c: c["id"]):
        live_one_day(co, rng, tick)
    for job in list(_after_tick):
        job(tick)
    storage.save_data()


def live_one_day(co, rng, tick):
    players = max(1, len(ventures_store.members(co)))
    new, lines = ventures_sim.next_day(co, rng, players)
    online = [login for login in ventures_store.members(new) if login in state.online]
    if new["status"] == "alive":
        bonus = max(0, len(online) - 1)
        new = {**new, "ap": min(config.AP_MAX, config.AP_BASE + bonus), "seen": online}
        lines = lines + [next_round_line(new, players)]
    text = "\n".join(lines)
    new = ventures_store.put({**new, "report": text})
    ventures_log.record_day(new)
    ventures_team.post_to_company(new, text)
    ventures_team.send_event(new, "report", text)
    if new["fumes"] and new["status"] == "alive":
        for login in ventures_store.members(new):
            rooms.tell(login, f"🚨 {new['name']} is on fumes! Raise money or cut costs before the next tick.", "error")
    if new["status"] == "dead":
        ventures_team.bury(new, "died")


def next_round_line(co, players):
    """"⚡ 4 action points today. Next round (Seed) needs: MRR $10K (now $4.2K) ❌ ..."."""
    rows = ventures_sim.milestones(co, players)
    if not rows:
        return f"⚡ {co['ap']} action points today."
    goal = "the IPO" if co["stage"] == "c" else config.STAGE_NAMES[config.STAGES[config.STAGES.index(co["stage"]) + 1]]
    parts = [milestone_text(r) for r in rows]
    return f"⚡ {co['ap']} action points today. Next round ({goal}) needs: " + " · ".join(parts)


def milestone_text(r):
    mark = "✅" if r["ok"] else "❌"
    if r["what"] in ("MRR", "valuation"):
        return f"{r['what']} {money(r['need'])} (now {money(r['have'])}) {mark}"
    if r["what"] == "ticks":
        return f"{r['need']} days in this stage (now {r['have']}) {mark}"
    if r["what"] == "profit":
        return f"revenue ≥ {r['need']}% of burn (now {r['have']:.0f}%) {mark}"
    return f"{r['what']} {r['need']} (now {r['have']:.0f}) {mark}"
