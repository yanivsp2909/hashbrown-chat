"""
⚖️ The balance simulation: bot companies play a season with the REAL formulas (ventures_sim, ventures_actions,
ventures_rounds) and the formula investor, so we can see whether the game is fair: some die, some raise, about one
reaches the IPO, nobody gets infinite money, and how many 🪙 the exits would create (owner's decision V2).

    python3 -m chatserver.ventures_balance          (prints a report; tests/test_ventures_balance.py checks it)
"""
import random
import statistics

from chatserver import cap_table, config, ventures_actions, ventures_rounds, ventures_sim, ventures_store

STRATEGIES = ("careful", "hirer", "hype", "idle")
SKILL = {"careful": (6, 9), "hirer": (4, 8), "hype": (5, 9), "idle": (2, 6)}   # how good their pitches are


# ---------------------------------------------------------------- the bots

def wish(co, strategy, rng):
    """The action this kind of bot wants to do now: (name, args)."""
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
            co, _ = ventures_actions.apply(co, name, args)
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


def season(seed, companies=20, ticks=30):
    """One simulated season. Returns its numbers."""
    rng = random.Random(seed)
    bots, tokens_in = [], companies * config.FOUND_COST
    for number in range(companies):
        bot, angel = new_bot(number, rng)
        bots.append(bot)
        tokens_in += angel
    exits, max_cash = [], 0
    for _ in range(ticks):
        for i, co in enumerate(bots):
            if co["status"] != "alive" or co["stage"] == "public":
                continue
            players = co["bot_players"]
            co = play_day({**co, "ap": min(config.AP_MAX, config.AP_BASE + players - 1)}, co["bot_strategy"], rng)
            co = raise_money(co, co["bot_strategy"], rng)
            co, _ = ventures_sim.next_day(co, rng, players)
            value = ipo_value(co, players, rng)
            if value:
                exits.append(sum(payouts(co, value).values()))
                co = {**co, "stage": "public"}
            max_cash = max(max_cash, co["cash"])
            bots[i] = co
    stages = [b["stage"] for b in bots]
    paid = sum(exits)
    from_fund = min(paid, tokens_in)   # the fund pays first (here: only what this game put in)
    minted = min(paid - from_fund, config.VENTURES_MINT_SEASON_CAP)
    return {"dead": sum(1 for b in bots if b["status"] == "dead"), "companies": companies,
            "seed_or_more": sum(1 for s in stages if config.STAGES.index(s) >= config.STAGES.index("seed")),
            "ipos": len(exits), "max_cash": max_cash, "paid": paid, "tokens_in": tokens_in, "from_fund": from_fund,
            "minted": minted, "waiting": paid - from_fund - minted, "stages": stages,
            "by_strategy": {s: [b["status"] if b["status"] == "dead" else b["stage"] for b in bots
                                if b["bot_strategy"] == s] for s in STRATEGIES}}


def summary(seeds=20, companies=20, ticks=30):
    runs = [season(seed, companies, ticks) for seed in range(seeds)]
    total = seeds * companies

    def mean(key):
        return statistics.mean(r[key] for r in runs)
    return {"runs": runs, "death_rate": sum(r["dead"] for r in runs) / total,
            "seed_rate": sum(r["seed_or_more"] for r in runs) / total, "ipos_per_season": mean("ipos"),
            "max_cash": max(r["max_cash"] for r in runs), "paid_per_season": mean("paid"),
            "paid_max": max(r["paid"] for r in runs), "minted_per_season": mean("minted"),
            "minted_max": max(r["minted"] for r in runs), "tokens_in_per_season": mean("tokens_in"),
            "waiting_max": max(r["waiting"] for r in runs)}


def report():
    s = summary()
    lines = [f"⚖️ Ventures balance: {len(s['runs'])} seasons x {s['runs'][0]['companies']} bot companies x 30 days",
             f"  died: {s['death_rate']:.0%}   reached Seed or later: {s['seed_rate']:.0%}   "
             f"IPOs per season: {s['ipos_per_season']:.2f}   richest cash: ${s['max_cash'] / 1e6:,.0f}M",
             f"  🪙 into the fund (founding + angels): {s['tokens_in_per_season']:,.0f} a season",
             f"  🪙 exits pay (after tax and the {config.EXIT_MAX_TOKENS} cap): {s['paid_per_season']:,.0f} a season "
             f"on average, {s['paid_max']:,} at most",
             f"  🪙 newly created (after the fund, cap {config.VENTURES_MINT_SEASON_CAP:,}): "
             f"{s['minted_per_season']:,.0f} on average, {s['minted_max']:,} at most; waiting at most {s['waiting_max']:,}"]
    for strategy in STRATEGIES:
        ends = [x for r in s["runs"] for x in r["by_strategy"][strategy]]
        counts = {k: ends.count(k) for k in ["dead"] + config.STAGES}
        lines.append(f"  {strategy:8} " + "  ".join(f"{k}: {v}" for k, v in counts.items() if v))
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
