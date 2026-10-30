"""
🔑 Logging in and creating accounts.
"""
import hashlib
import secrets
import time

from chatserver import config, group_view, offers, reminders, rooms, state, storage, textutil, transfers


# ---------------------------------------------------------------- passwords

def hash_password(password, salt_hex=None):
    """Never store the password itself: store a salted, slow hash of it."""
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex(), digest.hex()


def login_locked(key):
    """True if this username had too many wrong passwords lately (per username, never per IP:
    every website user comes from the same address)."""
    now = time.time()
    recent = [t for t in state.login_fails.get(key, []) if now - t < config.LOGIN_FAIL_WINDOW]
    state.login_fails[key] = recent
    return len(recent) >= config.LOGIN_FAIL_LIMIT and now - recent[-1] < config.LOGIN_LOCK_SECONDS


def check_password(password, salt_hex):
    """Slow on purpose. At most a few run at once, so password guessing can't eat every CPU."""
    with state.hashing:
        return hash_password(password, salt_hex)


def clean_features(value):
    """The optional "features" list of the auth packet -> a set. Anything that isn't a list of at most
    MAX_FEATURES strings of at most MAX_FEATURE_LENGTH characters is ignored (an empty set)."""
    if (not isinstance(value, list) or len(value) > config.MAX_FEATURES
            or not all(isinstance(f, str) and len(f) <= config.MAX_FEATURE_LENGTH for f in value)):
        return frozenset()
    return frozenset(value)


def deliver_inbox(key):
    """📬 Private messages that came while you were offline (the same format as a live /send)."""
    inbox = state.accounts[key].get("inbox") or []
    for note in inbox:
        rooms.tell(key, f"💌 [{note['time']}] {note['from']} → you: {note['text']} (while you were away)", "private")
    if inbox:
        state.accounts[key]["inbox"] = []
        storage.save_data()


def handle_auth(client, msg):
    """Log in or create an account. Returns True on success."""
    action = msg.get("action")
    username = textutil.clean_text(msg.get("username", "")).strip()
    password = str(msg.get("password", ""))

    def fail(text):
        client.send({"type": "auth_result", "ok": False, "text": text})
        return False

    if action not in ("login", "register"):
        return fail("Bad request.")
    if action == "register" and username.lower() in config.RESERVED_NAMES:
        return fail("❌ That name is reserved.")
    if action == "register" and not rooms.valid_name(username):
        return fail(f"❌ Username: {rooms.NAME_RULE}")
    if not 1 <= len(username) <= 16:
        return fail("❌ Wrong username or password.")
    if action == "register" and not config.PASSWORD_MIN <= len(password) <= 64:
        return fail(f"❌ Password: {config.PASSWORD_MIN} to 64 characters.")
    if not config.OLD_PASSWORD_MIN <= len(password) <= 64:   # older accounts may have a shorter one
        return fail("❌ Wrong username or password.")
    try:
        password.encode("utf-8")
    except UnicodeEncodeError:  # a broken half-emoji character
        return fail("❌ That password has a character that can't be used.")
    key = username.lower()

    # Hashing is slow on purpose (it makes guessing passwords slow), so do it OUTSIDE the lock.
    if action == "register":
        with state.lock:
            if key in state.accounts or rooms.find_account(username):
                return fail("❌ That username is taken.")
        salt, digest = check_password(password, None)
        with state.lock:
            if key in state.accounts or rooms.find_account(username):
                return fail("❌ That username is taken.")
            state.accounts[key] = storage.new_account(username, salt, digest)
            storage.save_data()
    else:
        with state.lock:
            if login_locked(key):
                return fail("🔒 Too many wrong passwords for this account. Try again in 5 minutes.")
            account = state.accounts.get(key)
        # Unknown names get a hash too, so the answer time doesn't reveal who has an account
        _, digest = check_password(password, account["salt"] if account else "00" * 16)
        if account is None or not secrets.compare_digest(digest, account["hash"]):
            with state.lock:
                state.login_fails.setdefault(key, []).append(time.time())
            return fail("❌ Wrong username or password.")

    with state.lock:
        state.login_fails.pop(key, None)
        old = state.online.get(key)
        if old is not None:
            # The right password wins: the old window is probably a dead Wi-Fi connection
            # or a closed browser tab. It can't do anything as this account anymore
            # (with key None it's treated as logged out until it's hung up half a second later).
            rooms.notify_room(old.room, f"👋 {rooms.shown(key)} left the chat", exclude=old)
            old.key = None
            offers.drop_all_of(key)      # the old window's file offers and transfers end with it
            transfers.drop_all_of(key)
            old.kick("🔁 You logged in from another window, so this one was disconnected.")
            textutil.log(f"[SERVER] {rooms.nick(key)} logged in again, closing the old connection")
        client.key = key
        client.features = clean_features(msg.get("features"))
        state.online[key] = client
        greeting = "Welcome back" if action == "login" else "Account created! Welcome"
        client.send({"type": "auth_result", "ok": True, "text": f"✅ {greeting}, {rooms.nick(key)}!"})
        client.say(f"🪙 You have {state.accounts[key]['tokens']} tokens and earn {config.TOKENS_PER_MINUTE} "
                   f"every minute you're online.", "money")
        hint = "🥔 Say @hashbrown + a question to ask the AI. " if state.hashbrown else ""
        client.say(f"✨ {hint}Type /help to see everything you can do.")
        rooms.move_to_room(client, "lobby")
        if state.lab_lag_ms or state.lab_loss_percent:
            client.send(rooms.lab_packet())   # 🧪 the network lab is on: show the banner
        rooms.notify_room("lobby", f"👋 {rooms.shown(key)} joined the chat", exclude=client)
        deliver_inbox(key)
        reminders.deliver_at_login(key)
        group_view.mark_dirty()   # 👥 one more online
        textutil.log(f"[SERVER] {rooms.nick(key)} logged in from {client.address}")
    return True
