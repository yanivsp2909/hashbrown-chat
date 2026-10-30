"""
🪙 Token commands.
"""
import random
import time

from chatserver import achievements, config, history, registry, rooms, state, storage, textutil


# ----- 🪙 Tokens

@registry.command("/balance", "/balance [name]", "how many tokens 🪙", "🪙 Tokens")
def cmd_balance(client, args):
    key = rooms.find_account(args.strip()) if args.strip() else client.key
    if key is None:
        client.say(f"❓ No one called {args.strip()}.", "error")
        return
    client.say(f"🪙 {rooms.shown(key)} has {state.accounts[key]['tokens']} tokens.", "money")


@registry.command("/top", "/top", "richest players 🏆", "🪙 Tokens")
def cmd_top(client, args):
    # Hashbrown is on the list too (its tips), as ("🥔 Hashbrown", tokens) next to everyone's (shown name, tokens)
    everyone = [(rooms.shown(key), account["tokens"]) for key, account in state.accounts.items()]
    ranking = sorted(everyone + [("🥔 Hashbrown", state.hashbrown_tokens)], key=lambda row: row[1], reverse=True)[:10]
    medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, 11)]
    lines = ["🏆 Richest players:"]
    for medal, (name, tokens) in zip(medals, ranking):
        lines.append(f"  {medal} {name}  {tokens} 🪙")
    client.say("\n".join(lines), "money")


def give_allowed(client, amount):
    """🎁 Against farming tokens with extra accounts: no giving in an account's first GIVE_MIN_AGE_HOURS, and at
    most GIVE_DAILY_MAX a day in total. If it's allowed, it's counted in today's total."""
    account = state.accounts[client.key]
    age = time.time() - account["created"]
    if age < config.GIVE_MIN_AGE_HOURS * 3600:
        left = config.GIVE_MIN_AGE_HOURS - int(age // 3600)
        client.say(f"🐣 New accounts can't give tokens in their first {config.GIVE_MIN_AGE_HOURS} hours "
                   f"({left}h left).", "error")
        return False
    day, given = account["given"]
    given = given if day == textutil.today() else 0
    if given + amount > config.GIVE_DAILY_MAX:
        client.say(f"🎁 You can give at most {config.GIVE_DAILY_MAX} 🪙 a day. "
                   f"You have {config.GIVE_DAILY_MAX - given} left today.", "error")
        return False
    account["given"] = [textutil.today(), given + amount]
    return True


@registry.command("/give", "/give name amount", "send tokens to someone", "🪙 Tokens")
def cmd_give(client, args):
    parts = args.split()
    if len(parts) != 2:
        client.say("Usage: /give name amount", "error")
        return
    if parts[0].lower().lstrip("@") == "hashbrown":
        tip_hashbrown(client, parts[1])
        return
    target = rooms.find_account(parts[0])
    if target is None or target == client.key:
        client.say("❓ Give to who?", "error")
        return
    amount = rooms.parse_amount(client, parts[1])
    if amount is None or not give_allowed(client, amount):
        return
    state.accounts[client.key]["tokens"] -= amount
    state.accounts[target]["tokens"] += amount
    client.say(f"🎁 You gave {amount} 🪙 to {rooms.shown(target)}.", "money")
    rooms.tell(target, f"🎁 {rooms.shown(client.key)} gave you {amount} 🪙!", "money")
    achievements.check_rich(target)
    storage.save_data()


THANKS = ("Thanks {nick}! {amount} 🪙 straight into my fry fund 🍟", "Aww {nick}, {amount} 🪙 for me? You're the best 🥔",
          "{nick} just tipped me {amount} 🪙. Crispy and grateful!")


def tip_hashbrown(client, amount_text):
    """🥔 /give hashbrown N: the tokens stay with Hashbrown (state.hashbrown_tokens); a canned thanks, no AI."""
    amount = rooms.parse_amount(client, amount_text)
    if amount is None or not give_allowed(client, amount):
        return
    state.accounts[client.key]["tokens"] -= amount
    state.hashbrown_tokens += amount
    client.say(f"🎁 You gave {amount} 🪙 to 🥔 Hashbrown.", "money")
    msg = rooms.chat_message("Hashbrown", "🥔", random.choice(THANKS).format(nick=rooms.nick(client.key), amount=amount))
    history.add(client.room, msg)
    rooms.send_room(client.room, msg)
    storage.save_data()


@registry.command("/daily", "/daily", "free tokens every day, more for streaks 🔥", "🪙 Tokens")
def cmd_daily(client, args):
    account = state.accounts[client.key]
    since = time.time() - account["last_daily"]
    if since < 20 * 3600:
        wait = 20 * 3600 - since
        client.say(f"⏳ Come back in {int(wait // 3600)}h {int(wait % 3600 // 60)}m. "
                   f"🔥 Streak: {account['streak']} days", "error")
        return
    # Claim again within 48 hours to keep the streak going
    account["streak"] = account["streak"] + 1 if since < 48 * 3600 else 1
    reward = min(config.DAILY_BONUS + config.STREAK_BONUS * (account["streak"] - 1), config.DAILY_MAX)
    account["last_daily"] = time.time()
    account["tokens"] += reward
    tomorrow = min(reward + config.STREAK_BONUS, config.DAILY_MAX)
    client.say(f"🎁 +{reward} 🪙 daily bonus!  🔥 {account['streak']} day streak\n"
               f"   Come back in 20-48 hours for {tomorrow} 🪙 (wait longer and the streak resets).", "money")
    if account["streak"] >= 7:
        achievements.unlock(client.key, "on_fire")
    achievements.check_rich(client.key)
    storage.save_data()


@registry.command("/rob", "/rob name", "40% chance to steal, or pay a fine 🦹", "🪙 Tokens")
def cmd_rob(client, args):
    target = rooms.find_online(client, args.strip())
    if target is None:
        return
    if target == client.key:
        client.say("🙃 Robbing yourself? Bold.", "error")
        return
    wait = state.last_rob.get(client.key, 0) + config.ROB_COOLDOWN - time.time()
    if wait > 0:
        client.say(f"🚓 Lay low for {int(wait // 60)}m {int(wait % 60)}s before robbing again.", "error")
        return
    victim, robber = state.accounts[target], state.accounts[client.key]
    if victim["tokens"] < 50:
        client.say(f"🤷 {rooms.nick(target)} is too broke to rob.", "error")
        return
    state.last_rob[client.key] = time.time()
    if random.random() < 0.4:
        stolen = min(500, max(1, victim["tokens"] * random.randint(5, 15) // 100))
        victim["tokens"] -= stolen
        robber["tokens"] += stolen
        client.say(f"🦹 Success! You stole {stolen} 🪙 from {rooms.shown(target)}.", "money")
        rooms.tell(target, f"🚨 {rooms.shown(client.key)} robbed you and got away with {stolen} 🪙!", "error")
        achievements.unlock(client.key, "bandit")
        achievements.check_rich(client.key)
    else:
        fine = min(50, robber["tokens"])
        robber["tokens"] -= fine
        victim["tokens"] += fine
        client.say(f"🚓 Caught! You paid {fine} 🪙 to {rooms.shown(target)}.", "error")
        rooms.tell(target, f"🛡️ {rooms.shown(client.key)} tried to rob you and failed. You got {fine} 🪙!",
                   "money")
    storage.save_data()


@registry.command("/shop", "/shop", "badges for your name", "🪙 Tokens")
def cmd_shop(client, args):
    owned = state.accounts[client.key]["badges"]
    lines = ["🛒 Badge shop (shows next to your name):"]
    for badge, price in config.SHOP.items():
        lines.append(f"  {badge}  {price} 🪙{'  ✅ owned' if badge in owned else ''}")
    lines.append("Buy with /buy 🔥   Switch with /badge 😎   Hide with /badge off")
    client.say("\n".join(lines), "money")


@registry.command("/buy", "/buy badge", "buy a badge from /shop", "🪙 Tokens")
def cmd_buy(client, args):
    badge = args.strip()
    account = state.accounts[client.key]
    if badge not in config.SHOP:
        client.say("❓ That's not in the /shop. Copy the emoji exactly.", "error")
        return
    if badge in account["badges"]:
        client.say("You already own it. Wear it with /badge " + badge)
        return
    if account["tokens"] < config.SHOP[badge]:
        client.say(f"💸 {badge} costs {config.SHOP[badge]} 🪙, you have {account['tokens']}.", "error")
        return
    account["tokens"] -= config.SHOP[badge]
    account["badges"].append(badge)
    account["badge"] = badge
    storage.save_data()
    client.say(f"🛍️ You bought {badge}! You're now {rooms.shown(client.key)}", "money")
    if config.SHOP[badge] >= 1000:
        rooms.announce(f"💸 {rooms.shown(client.key)} just bought the {badge} badge!", exclude={client.key})


@registry.command("/badge", "/badge emoji|off", "wear a badge you own", "🪙 Tokens")
def cmd_badge(client, args):
    choice = args.strip()
    account = state.accounts[client.key]
    if choice == "off":
        account["badge"] = ""
    elif choice in account["badges"]:
        account["badge"] = choice
    else:
        client.say(f"You don't own that. Yours: {' '.join(account['badges']) or 'none, see /shop'}", "error")
        return
    storage.save_data()
    client.say(f"✨ You're now {rooms.shown(client.key)}")


# ----- 🏅 Achievements

@registry.command("/achievements", "/achievements", "your trophies and how to get the rest", "🪙 Tokens")
def cmd_achievements(client, args):
    owned = state.accounts[client.key]["achievements"]
    lines = [f"🏅 Achievements ({len(owned)}/{len(config.ACHIEVEMENTS)}):"]
    for name, (icon, title, how, reward) in config.ACHIEVEMENTS.items():
        mark = "✅" if name in owned else "🔒"
        lines.append(f"  {mark} {icon} {title:<17} {how}  (+{reward} 🪙)")
    client.say("\n".join(lines), "money")
