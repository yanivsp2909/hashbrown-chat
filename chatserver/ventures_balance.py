"""
⚖️ The balance simulation: bot companies play a season with the REAL formulas (ventures_sim, ventures_actions,
ventures_rounds) and the formula investor, so we can see whether the game is fair: some die, some raise, about one
reaches the IPO, nobody gets infinite money, and how many 🪙 the exits would create (owner's decision V2).

    python3 -m chatserver.ventures_balance          (prints a report; tests/test_ventures_balance.py checks it)
"""
import random
import statistics

from chatserver import cap_table, config, ventures_actions, ventures_rounds, ventures_sectors, ventures_sim, ventures_store

STRATEGIES = ("careful", "hirer", "hype", "idle")
SKILL = {"careful": (6, 9), "hirer": (4, 8), "hype": (5, 9), "idle": (2, 6)}   # how good their pitches are


# ---------------------------------------------------------------- the bots

def sector_wish(co, rng):
    """What the sector needs right now (a bot that plays its sector), or None."""
    s = ventures_sectors.state(co)
    kind = co["sector"]
    if kind == "ai":
        need = (co["customers"] // 100 + 1) * config.COMPUTE_PER_100_CUSTOMERS
        if s["compute"] < need * 3:
            return "compute", str(int(min(500, need * 5)))
        if any(not m["released"] for m in s["models"]):
            return "release", ""
        if not s["training"] and s["compute"] >= config.TRAIN_COMPUTE * (len(s["models"]) + 1) and rng.random() < 0.5:
            return "train", ""
        if s["safety"] < 60 and rng.random() < 0.3:
            return "safety", ""
    elif kind == "cyber":
        idle_lines = [k for k, level in s["lines"].items() if level == 0]
        if len(idle_lines) == len(s["lines"]) or (idle_lines and rng.random() < 0.15):
            return "launch", idle_lines[0]
        if s["security"] < 60 and rng.random() < 0.4:
            return "audit", ""
        if rng.random() < 0.25:
            return "improve", rng.choice([k for k, level in s["lines"].items() if level > 0])
    elif kind == "hardware":
        coming = s["stock"] + sum(b["units"] for b in s["batches"])
        if coming < co["customers"] * 2 + 10:
            limit = int(config.BATCH_MAX * ventures_sim.stage(co)["reach"])
            affordable = int(co["cash"] / 3 / max(1, s["unit_cost"]))   # (never bet the company on one batch)
            units = max(0, min(limit, affordable, int(co["customers"] * 3 + 20)))
            return ("manufacture", str(units)) if units >= 5 else None
        if rng.random() < 0.2:
            return "supply", ""
        if rng.random() < 0.15:
            return "keynote", ""
    elif kind == "game":
        if s["project"]["progress"] >= 100:
            return "launch", ""
        if rng.random() < 0.5:
            return "develop", ""
        if rng.random() < 0.2:
            return "liveops", ""
    elif kind == "saas" and rng.random() < 0.2:
        return rng.choice([("retention", ""), ("experiment", "")])
    return None


def wish(co, strategy, rng):
    """The action this kind of bot wants to do now: (name, args)."""
    if strategy != "idle" or rng.random() < 0.3:
        need = sector_wish(co, rng)
        if need and rng.random() < 0.7:
            return need
    need = config.ROUNDS.get(co["stage"], config.ROUNDS["c"])
    players = co["bot_players"]
    rich = co["cash"] > 25 * ventures_sim.burn(co, players)
    if strategy == "careful":
        if co["quality"] < need["quality"] + 5:
            return "build", ""
        if rich and ventures_actions.hire_count(co) > 0:
            return "hire", rng.choice(["engineer", "engineer", "sales", "marketer"])
        if co["reputation"] < need["reputation"] + 5:
            return "pr", ""
        return rng.choice([("marketing", ""), ("sales", ""), ("build", "")])
    if strategy == "hirer":
        if ventures_actions.hire_count(co) > 0:
            return "hire", rng.choice(["engineer", "sales", "marketer"])
        return rng.choice([("marketing", ""), ("build", ""), ("sales", "")])
    if strategy == "hype":
        return rng.choice([("marketing", ""), ("marketing", ""), ("sales", ""), ("build", ""), ("pr", "")])
    return rng.choice([("build", ""), ("sales", ""), (None, ""), (None, "")])   # idle: half the time nothing


def play_day(co, strategy, rng):
    """Spend today's action points (a few tries; an action it can't afford is skipped). An idle player skips
    half the days completely, like a real one who forgets to come back."""
    if strategy == "idle" and rng.random() < 0.5:
        return co
    for _ in range(8):
        if co["ap"] <= 0:
            break
        name, args = wish(co, strategy, rng)
        if name is None:
            co = {**co, "ap": co["ap"] - 1}
            continue
        try:
            co, _ = ventures_actions.apply(co, name, args, rng, co.get("bot_tick", 0))
        except ventures_actions.ActionError:
            continue
    return co


def raise_money(co, strategy, rng):
    """Pitch when the milestones are there (the formula investor; bots always accept), bridge when broke."""
    players = co["bot_players"]
    if co["stage"] in config.ROUNDS and co["stage"] != "c" and ventures_sim.ready(co, players) \
            and co["pitches"] < config.PITCHES_PER_STAGE:
        co = {**co, "pitches": co["pitches"] + 1}
        investor = rng.choice(ventures_rounds.eligible(co) or ["maya"])
        offer = ventures_rounds.fair_offer(co, investor, rng.randint(*SKILL[strategy]), players)
        if offer["score"] >= config.PASS_BELOW:
            return ventures_rounds.accept(co, ventures_rounds.new_sheet(co, investor, offer, "formula", ""))
    if co["fumes"] and co["bridged"] != co["stage"] and co["stage"] in config.ROUNDS:
        amount, post, bp = ventures_rounds.bridge_terms(co)
        co = {**co, "cash": co["cash"] + amount, "bridged": co["stage"],
              "cap": cap_table.dilute(co["cap"], cap_table.investor("bridge"), bp)}
    return co


def ipo_value(co, players, rng):
    """At Series C with the IPO milestones: the IPO valuation (with the "IPO pop"), else None."""
    if co["stage"] == "c" and ventures_sim.ready(co, players):
        return ventures_sim.valuation(co) * rng.uniform(0.9, 1.2)
    return None


# ---------------------------------------------------------------- exits (V2)

def exit_tokens(bp, value):
    """(gross, net) 🪙 for one holder's stake at an exit: capped per person, then taxed."""
    gross = min(config.EXIT_MAX_TOKENS, int(bp / cap_table.TOTAL * value / config.EXIT_DOLLARS_PER_TOKEN))
    return gross, gross - gross * config.EXIT_TAX_PERCENT // 100


def payouts(co, value):
    """Net 🪙 for every PLAYER holder (investors are the game's characters: they get nothing in 🪙)."""
    return {holder: exit_tokens(bp, value)[1] for holder, bp in co["cap"].items() if holder.startswith("p:")}


# ---------------------------------------------------------------- one season

def new_bot(number, rng):
    strategy = STRATEGIES[number % len(STRATEGIES)]
    sector = list(config.SECTORS)[number % len(config.SECTORS)]
    co = ventures_store.new_company(f"c{number}", f"Bot{number}", f"bot{number}", sector, f"bot{number}", 0)
    players = rng.choice([1, 1, 2, 3])
    cap = co["cap"]
    angel_tokens = 0
    if rng.random() < 0.3:   # 😇 a friend invests early
        angel_tokens = rng.choice([200, 500, 1000])
        dollars, bp = ventures_rounds.angel_terms(co, angel_tokens)
        cap = cap_table.dilute(cap, cap_table.player(f"angel{number}"), bp)
        co = {**co, "cash": co["cash"] + dollars}
    return {**co, "cap": cap, "bot_players": players, "bot_strategy": strategy}, angel_tokens


def maybe_acquire(bots, i, rng):
    """A rich company at Series A or later sometimes buys a young one (paying a bit over its valuation)."""
    buyer = bots[i]
    if buyer["status"] != "alive" or config.STAGES.index(buyer["stage"]) < config.STAGES.index("a") or rng.random() > 0.02:
        return None
    targets = [j for j, co in enumerate(bots) if j != i and co["status"] == "alive" and co["stage"] != "public"
               and 0 < co["valuation"] * 1.2 < buyer["cash"] / 3]
    if not targets:
        return None
    j = rng.choice(targets)
    price = bots[j]["valuation"] * 1.2
    same = bots[j]["sector"] == buyer["sector"]
    bots[i] = {**buyer, "cash": buyer["cash"] - int(price),
               "customers": buyer["customers"] + (bots[j]["customers"] * config.ACQUIRE_KEEP_CUSTOMERS if same else 0)}
    paid = sum(payouts(bots[j], min(price, bots[j]["valuation"] * 1.5)).values())   # (the real cap on an exit's value)
    bots[j] = {**bots[j], "status": "acquired"}
    return paid


def season(seed, companies=20, ticks=config.SEASON_TICKS):
    """One simulated season (IPOs, acquisitions and the season's end). Returns its numbers."""
    rng = random.Random(seed)
    bots, tokens_in = [], companies * config.FOUND_COST
    for number in range(companies):
        bot, angel = new_bot(number, rng)
        bots.append(bot)
        tokens_in += angel
    exits, buys, max_cash = [], [], 0
    for tick in range(1, ticks + 1):
        _, bench = ventures_sectors.bench(bots, tick)
        for i, co in enumerate(bots):
            if co["status"] != "alive" or co["stage"] == "public":
                continue
            players = co["bot_players"]
            co = play_day({**co, "ap": min(config.AP_MAX, config.AP_BASE + players - 1), "bot_tick": tick},
                          co["bot_strategy"], rng)
            co = raise_money(co, co["bot_strategy"], rng)
            co, _ = ventures_sim.next_day(co, rng, players, world={"tick": tick, "bench": bench})
            value = ipo_value(co, players, rng)
            if value:
                exits.append(sum(payouts(co, value).values()))
                co = {**co, "stage": "public"}
            max_cash = max(max_cash, co["cash"])
            bots[i] = co
            bought = maybe_acquire(bots, i, rng)
            if bought is not None:
                buys.append(bought)
    season_end = sum(sum(payouts(co, co["valuation"] * config.SEASON_END_PAYOUT_PERCENT / 100).values())
                     for co in bots if co["status"] == "alive" and co["stage"] != "public")
    stages = [b["stage"] for b in bots]
    paid = sum(exits) + sum(buys) + season_end
    from_fund = min(paid, tokens_in)   # the fund pays first (here: only what this game put in)
    minted = min(paid - from_fund, config.VENTURES_MINT_SEASON_CAP)
    return {"dead": sum(1 for b in bots if b["status"] == "dead"), "companies": companies,
            "seed_or_more": sum(1 for b in bots if config.STAGES.index(b["stage"]) >= config.STAGES.index("seed")),
            "ipos": len(exits), "acquisitions": len(buys), "max_cash": max_cash, "paid": paid,
            "paid_ipo": sum(exits), "paid_buys": sum(buys), "paid_season_end": season_end,
            "tokens_in": tokens_in, "from_fund": from_fund, "minted": minted, "waiting": paid - from_fund - minted,
            "mint_need": paid - from_fund,   # (what new tokens WOULD be needed, before the season's cap)
            "stages": stages,
            "by_strategy": {s: [b["status"] if b["status"] != "alive" else b["stage"] for b in bots
                                if b["bot_strategy"] == s] for s in STRATEGIES}}


def summary(seeds=20, companies=20, ticks=config.SEASON_TICKS):
    runs = [season(seed, companies, ticks) for seed in range(seeds)]
    total = seeds * companies

    def mean(key):
        return statistics.mean(r[key] for r in runs)
    return {"runs": runs, "death_rate": sum(r["dead"] for r in runs) / total,
            "seed_rate": sum(r["seed_or_more"] for r in runs) / total, "ipos_per_season": mean("ipos"),
            "max_cash": max(r["max_cash"] for r in runs), "paid_per_season": mean("paid"),
            "acquisitions_per_season": mean("acquisitions"), "mint_need_max": max(r["mint_need"] for r in runs), "paid_ipo": mean("paid_ipo"), "paid_buys": mean("paid_buys"),
            "paid_season_end": mean("paid_season_end"),
            "paid_max": max(r["paid"] for r in runs), "minted_per_season": mean("minted"),
            "minted_max": max(r["minted"] for r in runs), "tokens_in_per_season": mean("tokens_in"),
            "waiting_max": max(r["waiting"] for r in runs)}


def report():
    s = summary()
    lines = [f"⚖️ Ventures balance: {len(s['runs'])} seasons x {s['runs'][0]['companies']} bot companies x {config.SEASON_TICKS} days",
             f"  died: {s['death_rate']:.0%}   reached Seed or later: {s['seed_rate']:.0%}   "
             f"IPOs per season: {s['ipos_per_season']:.2f}   acquisitions: {s['acquisitions_per_season']:.2f}   "
             f"richest cash: ${s['max_cash'] / 1e6:,.0f}M",
             f"  🪙 exits pay on average: IPOs {s['paid_ipo']:,.0f} + acquisitions {s['paid_buys']:,.0f} + season end "
             f"{s['paid_season_end']:,.0f}",
             f"  🪙 into the fund (founding + angels): {s['tokens_in_per_season']:,.0f} a season",
             f"  🪙 exits pay (after tax and the {config.EXIT_MAX_TOKENS} cap): {s['paid_per_season']:,.0f} a season "
             f"on average, {s['paid_max']:,} at most",
             f"  🪙 newly created (after the fund, cap {config.VENTURES_MINT_SEASON_CAP:,}): "
             f"{s['minted_per_season']:,.0f} on average, {s['minted_max']:,} at most; waiting at most {s['waiting_max']:,}"]
    for strategy in STRATEGIES:
        ends = [x for r in s["runs"] for x in r["by_strategy"][strategy]]
        counts = {k: ends.count(k) for k in ["dead", "acquired"] + config.STAGES}
        lines.append(f"  {strategy:8} " + "  ".join(f"{k}: {v}" for k, v in counts.items() if v))
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
