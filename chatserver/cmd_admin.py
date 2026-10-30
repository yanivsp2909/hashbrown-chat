"""
🛠️ Server admin commands.
"""
import secrets
import time

from chatserver import achievements, config, registry, rooms, state, storage, textutil


@registry.command("/admin", "/admin password", "become a server admin", "🛠️ Admin")
def cmd_admin(client, args):
    account = state.accounts[client.key]
    if account["admin"]:
        client.say("🛠️ You're already an admin. Try /admintokens")
        return
    password = config.admin_password()
    if password == config.DEFAULT_ADMIN_PASSWORD:
        client.say("🔒 /admin is disabled until the host changes the admin password.", "error")
        return
    # Wrong tries from ALL accounts count together, so making extra accounts doesn't give more guesses
    now = time.time()
    state.admin_fail_times[:] = [t for t in state.admin_fail_times if now - t < config.ADMIN_FAIL_WINDOW]
    if len(state.admin_fail_times) >= config.ADMIN_FAIL_LIMIT:
        client.say("🔒 Too many wrong admin passwords. Try again in 10 minutes.", "error")
        return
    if not secrets.compare_digest(args.strip().encode("utf-8", "replace"), password.encode("utf-8", "replace")):
        state.admin_fail_times.append(now)
        client.say("❌ Wrong admin password.", "error")
        textutil.log(f"[SERVER] ⚠️ {rooms.nick(client.key)} typed a wrong /admin password")
        return
    account["admin"] = True
    storage.save_data()
    client.say("🛠️ You're now an admin! Try /admintokens", "event")
    textutil.log(f"[SERVER] {rooms.nick(client.key)} became an admin")


@registry.command("/admintokens", "/admintokens [name]", f"admin: +{config.ADMIN_TOKENS} 🪙", "🛠️ Admin")
def cmd_admintokens(client, args):
    if not state.accounts[client.key]["admin"]:
        client.say("🛠️ Admins only. Use /admin password first.", "error")
        return
    target = rooms.find_account(args.strip()) if args.strip() else client.key
    if target is None:
        client.say(f"❓ No one called {args.strip()}.", "error")
        return
    state.accounts[target]["tokens"] += config.ADMIN_TOKENS
    client.say(f"🛠️ +{config.ADMIN_TOKENS} 🪙 to {rooms.shown(target)}.", "money")
    if target != client.key:
        rooms.tell(target, f"🎁 An admin gave you {config.ADMIN_TOKENS} 🪙!", "money")
    textutil.log(f"[SERVER] {rooms.nick(client.key)} used /admintokens on {rooms.nick(target)}")
    achievements.check_rich(target)
    storage.save_data()
