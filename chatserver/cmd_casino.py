"""
🎰 Casino commands.
"""
import random

from chatserver import achievements, config, registry, rooms, state, storage


# ----- 🎰 Casino

def gamble_result(client, bet, payout, text, game):
    """payout = total tokens returned (0 = lost the bet)."""
    account = state.accounts[client.key]
    account["tokens"] += payout - bet
    net = payout - bet
    if net > 0:
        outcome = f"🎉 You won {net} 🪙!"
    elif net == 0:
        outcome = "😐 You got your bet back."
    else:
        outcome = f"😢 You lost {bet} 🪙."
        state.jackpot += -net * config.JACKPOT_SHARE // 100   # 💰 part of every loss goes into the pot
    client.say(f"{text}\n{outcome}  Balance: {account['tokens']} 🪙", "money" if net >= 0 else "error")
    if net >= 500:
        rooms.announce(f"🎰💥 {rooms.shown(client.key)} just won {net} 🪙 on {game}!", exclude={client.key})
    if bet >= 500:
        achievements.unlock(client.key, "high_roller")
    achievements.check_rich(client.key)
    storage.save_data()


@registry.command("/coinflip", "/coinflip amount heads|tails", "double or nothing", "🎰 Casino")
def cmd_coinflip(client, args):
    parts = args.split()
    if len(parts) != 2 or parts[1].lower() not in ("heads", "tails", "h", "t"):
        client.say("Usage: /coinflip amount heads   (or tails)", "error")
        return
    bet = rooms.parse_amount(client, parts[0])
    if bet is None:
        return
    guess = "heads" if parts[1].lower().startswith("h") else "tails"
    side = random.choice(["heads", "tails"])
    gamble_result(client, bet, bet * 2 if side == guess else 0, f"🪙 The coin spins... {side.upper()}!", "coinflip")


@registry.command("/dice", "/dice amount", "2 dice vs the house 🎲", "🎰 Casino")
def cmd_dice(client, args):
    bet = rooms.parse_amount(client, args)
    if bet is None:
        return
    faces = "⚀⚁⚂⚃⚄⚅"
    you = [random.randint(1, 6) for _ in range(2)]
    house = [random.randint(1, 6) for _ in range(2)]
    text = (f"🎲 You: {faces[you[0] - 1]} {faces[you[1] - 1]} = {sum(you)}   "
            f"House: {faces[house[0] - 1]} {faces[house[1] - 1]} = {sum(house)}")
    payout = bet * 2 if sum(you) > sum(house) else bet if sum(you) == sum(house) else 0
    gamble_result(client, bet, payout, text, "dice")


@registry.command("/slots", "/slots amount", "3 same = x10, 💎💎💎 = x25", "🎰 Casino")
def cmd_slots(client, args):
    bet = rooms.parse_amount(client, args)
    if bet is None:
        return
    reels = random.choices(config.SLOT_SYMBOLS, k=3)
    if reels == ["💎"] * 3:
        multiplier = 25
    elif len(set(reels)) == 1:
        multiplier = 10
    elif len(set(reels)) == 2:
        multiplier = 1.5
    else:
        multiplier = 0
    gamble_result(client, bet, int(bet * multiplier), f"🎰 [ {' | '.join(reels)} ]", "slots")
    if reels == ["💎"] * 3 and state.jackpot:   # 💰 the big one: the whole pot as well
        pot, state.jackpot = state.jackpot, 0
        state.accounts[client.key]["tokens"] += pot
        rooms.announce(f"💰💎 {rooms.shown(client.key)} hit the JACKPOT and won the pot: {pot} 🪙!")
    if multiplier >= 10:
        achievements.unlock(client.key, "jackpot")
        storage.save_data()  # gamble_result already saved, before this achievement and the pot


@registry.command("/jackpot", "/jackpot", "the pot that three 💎 on /slots wins 💰", "🎰 Casino")
def cmd_jackpot(client, args):
    client.say(f"💰 The jackpot is {state.jackpot} 🪙. {config.JACKPOT_SHARE}% of every casino loss goes in; "
               "three 💎 on /slots wins all of it.", "money")
