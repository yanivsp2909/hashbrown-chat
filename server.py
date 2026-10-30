"""
🥔 Hashbrown chat server: accounts, groups, tokens, casino, games, files and an AI bot.

Run:   python server.py        (games.py must be in the same folder)
Saves: chat_data.json next to this file (accounts, tokens, groups survive restarts)
AI:    fill in hashbrown_config.json (created on first run) to wake up Hashbrown
Type   help   in this window for server console commands.
"""
import hashlib
import json
import os
import queue
import random
import re
import secrets
import socket
import threading
import time
import traceback
import unicodedata
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime

import games

HOST = "0.0.0.0"
PORT = 8820
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "chat_data.json")
HASHBROWN_CONFIG = os.path.join(BASE_DIR, "hashbrown_config.json")

MAX_LINE = 4 * 1024 * 1024   # biggest single message in bytes (room for a 2 MB file)
MAX_FILE_B64 = 2_800_000     # a 2 MB file is about 2.7 MB after base64
MAX_TEXT = 500               # longest chat message, in characters
RESERVED_NAMES = {"hashbrown", "server", "admin", "lobby"}
START_TOKENS = 100
TOKENS_PER_MINUTE = 5        # every logged-in user
GROUP_INCOME = 10            # every group bank, while at least one member is online
GROUP_COST = 50
DAILY_BONUS, STREAK_BONUS, DAILY_MAX = 150, 50, 500   # day 1: 150, day 2: 200 ... up to 500
WIN_REWARD, MAX_REWARDED_WINS = 25, 10                # +25 per win, for the first 10 wins a day
SOLO_MAX_REWARDS = 5                                  # rewarded Wordle wins per day
HISTORY_SIZE, BIG_HISTORY_SIZE = 15, 50
SPAM_LIMIT, SPAM_WINDOW = 8, 5   # at most 8 messages per 5 seconds
MAX_OWNED_GROUPS = 2             # groups one person can own
TEAM_PLAYER_DONATION = 50        # one donation this big unlocks 🤝 Team Player
MIN_MOVES_FOR_BONUS = 2          # moves EACH player must make before a resign/disconnect win earns the +25

# Protection against broken or abusive connections
MAX_CONNECTIONS = 200            # connections at the same time
MAX_LOGIN_LINE = 64 * 1024       # biggest message from someone who hasn't logged in yet
LOGIN_TIMEOUT = 120              # seconds a new connection has to log in (in total)
OUTBOX_LIMIT = 1000              # messages waiting for one person; more = they stopped reading, disconnect them
LOGIN_FAIL_LIMIT, LOGIN_FAIL_WINDOW = 5, 300   # 5 wrong passwords for one username in 5 minutes...
LOGIN_LOCK_SECONDS = 300                       # ...lock that username for 5 minutes
HASHING_AT_ONCE = 4              # password checks running at the same time (they're slow on purpose)
ACCEPT_WAKEUP = 1                # seconds; the accept loop wakes up this often (so Ctrl+C works on Windows)

# /admin <password> makes your account an admin. Change it here, or set the
# HASHBROWN_ADMIN_PASSWORD environment variable (that one wins). An empty password switches /admin off.
DEFAULT_ADMIN_PASSWORD = ""
ADMIN_PASSWORD = "123"
ADMIN_FAIL_LIMIT, ADMIN_FAIL_WINDOW = 3, 600   # 3 wrong /admin tries by ANYONE in 10 minutes locks /admin
ADMIN_TOKENS = 1000              # what /admintokens gives

HASHBROWN_COST = 20          # tokens per question
HASHBROWN_COOLDOWN = 15      # seconds between questions, per person
HASHBROWN_DAILY_LIMIT = 30   # questions per person per day
HASHBROWN_DAILY_CAP = 100    # questions for EVERYONE together per day (each one costs real money)
HASHBROWN_MAX_BUSY = 3       # questions being answered at the same time
HASHBROWN_PROMPT = (
    "You are Hashbrown 🥔, a friendly, funny AI living in a terminal group chat of teenagers in Israel. "
    "Answer in the same language as the question. Keep it short: at most 4 sentences, plain text, "
    "no markdown, a few emojis are fine. Be kind, don't insult anyone, and refuse anything dangerous, "
    "sexual or hateful. You can see the recent chat for context.")

GROUP_UPGRADES = {  # name: (icon, price paid from the group bank, what it does)
    "income": ("💰", 300, "members earn +2 🪙/min while inside the group"),
    "history": ("📜", 200, "chat history 15 -> 50 messages"),
    "emoji": ("🎨", 150, "a custom emoji next to the group name (/groupemoji)"),
    "hashbrown": ("🥔", 250, "Hashbrown questions asked here are paid by the bank"),
}
ACHIEVEMENTS = {  # id: (icon, title, how to get it, reward)
    "first_win": ("🥇", "First Blood", "win a game", 50),
    "ten_wins": ("🏆", "Champion", "win 10 games", 200),
    "founder": ("🏗️", "Founder", "create a group", 50),
    "team_player": ("🤝", "Team Player", f"donate {TEAM_PLAYER_DONATION}+ to a group bank", 50),
    "chatty": ("💬", "Chatterbox", "send 100 messages", 100),
    "rich": ("💰", "Rich", "have 1000 tokens", 100),
    "jackpot": ("🎰", "Jackpot", "hit 3 of a kind in slots", 100),
    "high_roller": ("🎲", "High Roller", "bet 500+ in the casino", 100),
    "bandit": ("🦹", "Bandit", "rob someone successfully", 50),
    "on_fire": ("🔥", "On Fire", "reach a 7 day /daily streak", 300),
    "potato": ("🥔", "Potato Whisperer", "ask Hashbrown something", 25),
    "wordsmith": ("🟩", "Wordsmith", "solve a Wordle", 50),
    "genius": ("🧠", "Genius", "solve a Wordle in 3 tries or less", 150),
}
SHOP = {"🔥": 100, "😎": 250, "🎮": 400, "💎": 1000, "👑": 5000, "🐐": 10000}
SLOT_SYMBOLS = ["🍒", "🍋", "🍇", "🔔", "⭐", "💎"]
GAMES = {"ttt": games.TicTacToe, "tictactoe": games.TicTacToe,
         "checkers": games.Checkers, "damka": games.Checkers,
         "math": games.MathDuel, "mathduel": games.MathDuel}

# ---------------------------------------------------------------- shared state
# Every thread reads and writes these, so ALL access happens while holding `lock`.
lock = threading.RLock()
accounts = {}   # login name (lowercase) -> account dict      (saved to disk)
groups = {}     # group name (lowercase) -> group dict        (saved to disk)
online = {}     # login name -> Client, only people connected right now
history = {"lobby": deque(maxlen=HISTORY_SIZE)}  # room -> last chat messages
mutes = {}      # (group, login) -> time the mute ends
invites = {}    # login -> game challenges waiting for that person
matches = {}    # login -> the Match they're playing
last_rob = {}   # login -> time of their last /rob
solo = {}       # login -> their Wordle game
login_fails = {}         # login -> times of recent wrong passwords
admin_fail_times = []    # times of recent wrong /admin passwords, from anyone
connections = 0          # open connections right now
hashing = threading.BoundedSemaphore(HASHING_AT_ONCE)
quiz = None     # the open quick-math question, if any
hashbrown = None        # Foundry settings, or None if Hashbrown isn't set up
hashbrown_busy = 0      # questions being answered right now
hashbrown_last = {}     # login -> time of their last question
hashbrown_today = {}    # login -> (date, questions asked that day)
hashbrown_all_today = ("", 0)  # (date, questions asked by everyone that day)


# ---------------------------------------------------------------- logging

def log(text):
    """print() that can't crash the server on a console that can't show emoji."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode())


# ---------------------------------------------------------------- cleaning text from the network

# Control characters (new lines, terminal escape codes...) and the invisible "flip the text
# direction" marks. In a chat line they could fake a second line or mess up someone's screen.
CONTROL_CHARS = re.compile("[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")


def clean_text(text, keep_newlines=False):
    """Make text from the network safe to store, save and show."""
    # A lone half of an emoji ("\ud800") can't be saved or sent: turn it into "?"
    text = str(text).encode("utf-8", "replace").decode("utf-8")
    if keep_newlines:
        return "\n".join(CONTROL_CHARS.sub("", line.replace("\t", " ")) for line in text.split("\n"))
    return CONTROL_CHARS.sub("", re.sub("[\t\r\n]", " ", text))


# ---------------------------------------------------------------- saving / loading

def load_data():
    """Read chat_data.json. Returns False if the file is damaged: then the server must NOT
    start, or the next save would overwrite everyone's accounts."""
    global accounts, groups
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                data = json.load(f)
            accounts, groups = dict(data.get("accounts", {})), dict(data.get("groups", {}))
        except (OSError, ValueError, AttributeError, TypeError) as e:
            log(f"[SERVER] ❌ Can't read {DATA_FILE} ({type(e).__name__}). It may be damaged. "
                f"The server did not start, so nothing was overwritten. Fix the file or move it away.")
            return False
    # Files saved by an older version are missing the newer fields: fill them in
    for account in accounts.values():
        for field, default in new_account("", "", "").items():
            account.setdefault(field, default)
    for key, group in groups.items():
        for field, default in new_group(key, "", False).items():
            group.setdefault(field, default)
        history[key] = deque(maxlen=history_size(group))
    log(f"[SERVER] Loaded {len(accounts)} accounts and {len(groups)} groups")
    return True


def history_size(group):
    return BIG_HISTORY_SIZE if "history" in group["upgrades"] else HISTORY_SIZE


def save_data():
    """Write everything to chat_data.json. Returns False (and logs why) if it couldn't:
    the data stays in memory and the next save tries again."""
    with lock:
        tmp = DATA_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"accounts": accounts, "groups": groups}, f, ensure_ascii=False, indent=1)
                f.flush()
                os.fsync(f.fileno())  # really on the disk, even if the power goes out right after
            for attempt in range(3):
                try:
                    os.replace(tmp, DATA_FILE)  # swap in one step, so a crash never leaves a half file
                    break
                except PermissionError:  # Windows: an antivirus can hold the file for a moment
                    if attempt == 2:
                        raise
                    time.sleep(0.1)
            return True
        except (OSError, ValueError) as e:
            log(f"[SERVER] ⚠️ Couldn't save {DATA_FILE}: {e}")
            return False


# ---------------------------------------------------------------- passwords

def hash_password(password, salt_hex=None):
    """Never store the password itself: store a salted, slow hash of it."""
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex(), digest.hex()


# ---------------------------------------------------------------- one connected person

class Client:
    def __init__(self, sock, address):
        self.sock = sock
        self.address = address
        self.key = None          # login name once logged in
        self.room = "lobby"
        self.quitting = False
        self.login_deadline = time.time() + LOGIN_TIMEOUT  # strangers must log in before this
        self.recent = deque()    # times of recent messages, for spam protection
        # Sending goes through a queue + its own thread, so a slow connection
        # can never freeze the server while it holds the lock.
        self.outbox = queue.Queue(maxsize=OUTBOX_LIMIT)
        self.writer = threading.Thread(target=self._write_loop, daemon=True)
        self.writer.start()

    def _write_loop(self):
        while True:
            obj = self.outbox.get()
            if obj is None:
                return
            try:
                # "replace": a broken character becomes "?" instead of killing this thread
                self.sock.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8", "replace"))
            except OSError:  # the connection is gone: make the reading side notice too
                hang_up(self)
                return
            except Exception:  # a bug in one message must never leave this person deaf
                log("[SERVER] Error while sending:\n" + traceback.format_exc())
                hang_up(self)
                return

    def send(self, obj):
        try:
            self.outbox.put_nowait(obj)
        except queue.Full:
            # They stopped reading. Dropping messages would break their game board, so disconnect them.
            hang_up(self)

    def say(self, text, kind="system"):
        self.send({"type": "msg", "kind": kind, "text": text})

    def kick(self, text):
        """Tell them why, then hang up half a second later (so the message gets there first)."""
        self.say(text, "error")
        threading.Timer(0.5, hang_up, args=(self,)).start()

    def close(self):
        try:
            self.outbox.put_nowait(None)
        except queue.Full:
            pass  # the writer is stuck or gone; closing the socket below stops it
        self.writer.join(timeout=1)  # let the last messages go out first
        try:
            self.sock.close()
        except OSError:
            pass


def recv_lines(sock, client):
    """Yield complete lines from the socket (one JSON message per line)."""
    buffer = bytearray()
    while True:
        if client.key is None:  # not logged in: the clock keeps running, sending bytes doesn't reset it
            left = client.login_deadline - time.time()
            if left <= 0:
                return
            sock.settimeout(left)
        chunk = sock.recv(65536)
        if not chunk:  # empty = the other side closed the connection
            return
        start = len(buffer)
        buffer += chunk
        while True:
            end = buffer.find(b"\n", start)
            if end == -1:
                break
            line = bytes(buffer[:end])
            del buffer[:end + 1]
            start = 0
            yield line
        limit = MAX_LINE if client.key else MAX_LOGIN_LINE  # strangers can't send 4 MB
        if len(buffer) > limit:  # no newline that far: broken or abusive client
            return


def parse_message(raw):
    """One line from the network -> a dict, or None if it isn't a JSON object."""
    try:
        msg = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):  # RecursionError: [[[[... nested very deep
        return None
    return msg if isinstance(msg, dict) else None


# ---------------------------------------------------------------- small helpers

def valid_name(name):
    return (3 <= len(name) <= 16 and all(ch.isalnum() or ch == "_" for ch in name)
            and name.lower() not in RESERVED_NAMES)


def today():
    return datetime.now().strftime("%Y-%m-%d")


def nick(key):
    return accounts[key]["nick"]


def shown(key):
    """Name with badge, like '👑 Yaniv'."""
    account = accounts[key]
    return f"{account['badge']} {account['nick']}" if account["badge"] else account["nick"]


def find_account(name):
    name = name.lower().lstrip("@")
    for key, account in accounts.items():
        if account["nick"].lower() == name:
            return key
    return None


def find_online(client, name):
    key = find_account(name) if name else None
    if key is None or key not in online:
        client.say(f"❓ {name or 'Who'} isn't online. See /users", "error")
        return None
    return key


def room_title(room):
    if room == "lobby":
        return "🏠 Lobby"
    group = groups[room]
    emoji = group["emoji"] + " " if group["emoji"] else ""
    return emoji + ("🔒" if group["private"] else "#") + group["name"]


def send_room(room, obj, exclude=None):
    for c in list(online.values()):
        if c.room == room and c is not exclude:
            c.send(obj)


def notify_room(room, text, exclude=None, kind="system"):
    send_room(room, {"type": "msg", "kind": kind, "text": text}, exclude)


def announce(text, kind="event", exclude=()):
    for key, c in list(online.items()):
        if key not in exclude:
            c.say(text, kind)


def tell(key, text, kind="system"):
    if key in online:
        online[key].say(text, kind)


def parse_amount(client, text):
    """Turn '50' or 'all' into a number of tokens the client actually has."""
    balance = accounts[client.key]["tokens"]
    text = text.strip().lower()
    if text == "all":
        amount = balance
    elif text.isdecimal() and len(text) < 10:
        amount = int(text)
    else:
        client.say("💰 The amount must be a number (or 'all').", "error")
        return None
    if amount <= 0:
        client.say("💰 The amount must be more than 0.", "error")
        return None
    if amount > balance:
        client.say(f"💸 You only have {balance} 🪙.", "error")
        return None
    return amount


def move_to_room(client, room):
    old = client.room
    client.room = room
    if old != room:  # groups get enter/leave notices; the lobby would be too noisy
        if old != "lobby":
            notify_room(old, f"🚪 {shown(client.key)} left the room")
        if room != "lobby":
            notify_room(room, f"➡️ {shown(client.key)} entered", exclude=client)
    client.send({"type": "history", "room": room_title(room), "messages": list(history[room])})


def spam_ok(client):
    now = time.time()
    while client.recent and now - client.recent[0] > SPAM_WINDOW:
        client.recent.popleft()
    if len(client.recent) >= SPAM_LIMIT:
        client.say("🐢 Slow down! You're sending too fast.", "error")
        return False
    client.recent.append(now)
    return True


# ---------------------------------------------------------------- login / register

def new_account(username, salt, digest):
    return {"login": username, "nick": username, "salt": salt, "hash": digest,
            "tokens": START_TOKENS, "badge": "", "badges": [], "wins": 0, "losses": 0,
            "draws": 0, "last_daily": 0, "streak": 0, "messages": 0, "achievements": [],
            "win_day": "", "rewarded_wins": 0, "solo_day": "", "solo_rewarded": 0,
            "admin": False, "joined": today()}


def new_group(name, owner, private):
    return {"name": name, "owner": owner, "admins": [], "members": [owner] if owner else [],
            "banned": [], "requests": [], "private": private, "bank": 0, "upgrades": [], "emoji": ""}


def login_locked(key):
    """True if this username had too many wrong passwords lately (per username, never per IP:
    every website user comes from the same address)."""
    now = time.time()
    recent = [t for t in login_fails.get(key, []) if now - t < LOGIN_FAIL_WINDOW]
    login_fails[key] = recent
    return len(recent) >= LOGIN_FAIL_LIMIT and now - recent[-1] < LOGIN_LOCK_SECONDS


def check_password(password, salt_hex):
    """Slow on purpose. At most a few run at once, so password guessing can't eat every CPU."""
    with hashing:
        return hash_password(password, salt_hex)


# ---------------------------------------------------------------- achievements

def unlock(key, achievement):
    """Give an achievement (once) and its reward."""
    account = accounts[key]
    if achievement in account["achievements"]:
        return
    icon, title, how, reward = ACHIEVEMENTS[achievement]
    account["achievements"].append(achievement)
    account["tokens"] += reward
    tell(key, f"🏅 ACHIEVEMENT UNLOCKED: {icon} {title} ({how})  +{reward} 🪙", "money")
    announce(f"🏅 {shown(key)} unlocked {icon} {title}!", exclude={key})
    check_rich(key)


def check_rich(key):
    if accounts[key]["tokens"] >= 1000:
        unlock(key, "rich")


def handle_auth(client, msg):
    """Log in or create an account. Returns True on success."""
    action = msg.get("action")
    username = clean_text(msg.get("username", "")).strip()
    password = str(msg.get("password", ""))

    def fail(text):
        client.send({"type": "auth_result", "ok": False, "text": text})
        return False

    if action not in ("login", "register"):
        return fail("Bad request.")
    if action == "register" and username.lower() in RESERVED_NAMES:
        return fail("❌ That name is reserved.")
    if action == "register" and not valid_name(username):
        return fail("❌ Username: 3-16 letters, numbers or _")
    if not 1 <= len(username) <= 16:
        return fail("❌ Wrong username or password.")
    if not 4 <= len(password) <= 64:
        return fail("❌ Password: 4 to 64 characters.")
    try:
        password.encode("utf-8")
    except UnicodeEncodeError:  # a broken half-emoji character
        return fail("❌ That password has a character that can't be used.")
    key = username.lower()

    # Hashing is slow on purpose (it makes guessing passwords slow), so do it OUTSIDE the lock.
    if action == "register":
        with lock:
            if key in accounts or find_account(username):
                return fail("❌ That username is taken.")
        salt, digest = check_password(password, None)
        with lock:
            if key in accounts or find_account(username):
                return fail("❌ That username is taken.")
            accounts[key] = new_account(username, salt, digest)
            save_data()
    else:
        with lock:
            if login_locked(key):
                return fail("🔒 Too many wrong passwords for this account. Try again in 5 minutes.")
            account = accounts.get(key)
        # Unknown names get a hash too, so the answer time doesn't reveal who has an account
        _, digest = check_password(password, account["salt"] if account else "00" * 16)
        if account is None or not secrets.compare_digest(digest, account["hash"]):
            with lock:
                login_fails.setdefault(key, []).append(time.time())
            return fail("❌ Wrong username or password.")

    with lock:
        login_fails.pop(key, None)
        old = online.get(key)
        if old is not None:
            # The right password wins: the old window is probably a dead Wi-Fi connection
            # or a closed browser tab. It can't do anything as this account anymore
            # (with key None it's treated as logged out until it's hung up half a second later).
            notify_room(old.room, f"👋 {shown(key)} left the chat", exclude=old)
            old.key = None
            old.kick("🔁 You logged in from another window, so this one was disconnected.")
            log(f"[SERVER] {nick(key)} logged in again, closing the old connection")
        client.key = key
        online[key] = client
        greeting = "Welcome back" if action == "login" else "Account created! Welcome"
        client.send({"type": "auth_result", "ok": True, "text": f"✅ {greeting}, {nick(key)}!"})
        client.say(f"🪙 You have {accounts[key]['tokens']} tokens and earn {TOKENS_PER_MINUTE} "
                   f"every minute you're online.", "money")
        hint = "🥔 Say @hashbrown + a question to ask the AI. " if hashbrown else ""
        client.say(f"✨ {hint}Type /help to see everything you can do.")
        move_to_room(client, "lobby")
        notify_room("lobby", f"👋 {shown(key)} joined the chat", exclude=client)
        log(f"[SERVER] {nick(key)} logged in from {client.address}")
    return True


# ---------------------------------------------------------------- commands
# @command registers a function as a /command and puts it in /help automatically.

COMMANDS = {}


def command(name, usage, description, category):
    def register(function):
        COMMANDS[name] = (function, usage, description, category)
        return function
    return register


# ----- 💬 Chat

@command("/help", "/help", "show this list", "💬 Chat")
def cmd_help(client, args):
    by_category = {}
    for function, usage, description, category in COMMANDS.values():
        by_category.setdefault(category, []).append(f"  {usage:<32} {description}")
    lines = ["📖 COMMANDS"]
    for category, items in by_category.items():
        lines.append(f"\n{category}")
        lines += items
    lines.append("\nAnything that isn't a command is a chat message to the room you're in.")
    lines.append(f"🥔 Start a message with @hashbrown to ask the AI ({HASHBROWN_COST} 🪙).")
    client.say("\n".join(lines), "help")


@command("/users", "/users", "who's online and where", "💬 Chat")
def cmd_users(client, args):
    lines = [f"🟢 Online now ({len(online)}):"]
    for key in sorted(online, key=lambda k: nick(k).lower()):
        playing = "  🎮 playing" if key in matches else ""
        lines.append(f"  {shown(key)}  {room_title(online[key].room)}{playing}")
    client.say("\n".join(lines))


@command("/send", "/send name message", "private message 💌", "💬 Chat")
def cmd_send(client, args):
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        client.say("Usage: /send name message", "error")
        return
    target = find_online(client, parts[0])
    if target is None:
        return
    if target == client.key:
        client.say("🙃 You can't message yourself.", "error")
        return
    stamp = datetime.now().strftime("%H:%M")
    tell(target, f"💌 [{stamp}] {shown(client.key)} → you: {parts[1]}", "private")
    client.say(f"💌 [{stamp}] you → {shown(target)}: {parts[1]}", "private")


@command("/me", "/me action", "act it out: * Yaniv dances", "💬 Chat")
def cmd_me(client, args):
    if args:
        post_chat(client, args, action=True)


@command("/nick", "/nick newname", "change your display name", "💬 Chat")
def cmd_nick(client, args):
    new = args.strip()
    if not valid_name(new):
        client.say("❌ Names: 3-16 letters, numbers or _", "error")
        return
    owner = find_account(new)
    login_owner = new.lower() if new.lower() in accounts else None
    if (owner and owner != client.key) or (login_owner and login_owner != client.key):
        client.say("❌ Someone already has that name.", "error")
        return
    old = nick(client.key)
    accounts[client.key]["nick"] = new
    save_data()
    notify_room(client.room, f"✏️ {old} is now called {shown(client.key)}")
    client.say(f"(You still log in as {accounts[client.key]['login']}.)")


@command("/whois", "/whois name", "someone's profile", "💬 Chat")
def cmd_whois(client, args):
    key = find_account(args.strip()) if args.strip() else client.key
    if key is None:
        client.say(f"❓ No one called {args.strip()}.", "error")
        return
    a = accounts[key]
    status = f"🟢 online in {room_title(online[key].room)}" if key in online else "⚫ offline"
    member_of = [g["name"] for g in groups.values() if key in g["members"]]
    client.say(f"👤 {shown(key)}\n"
               f"   🪙 {a['tokens']} tokens   🏆 {a['wins']}W {a['losses']}L {a['draws']}D\n"
               f"   {status}\n"
               f"   👥 groups: {', '.join(member_of) or 'none'}\n"
               f"   📅 joined {a['joined']}   🔥 daily streak: {a['streak']}\n"
               f"   🏅 badges: {' '.join(a['badges']) or 'none'}   "
               f"achievements: {len(a['achievements'])}/{len(ACHIEVEMENTS)}")


@command("/quit", "/quit", "leave the chat", "💬 Chat")
def cmd_quit(client, args):
    client.quitting = True


# ----- 👥 Groups

def current_group(client):
    if client.room == "lobby":
        client.say("🏠 You're in the lobby. /join a group first.", "error")
        return None, None
    return client.room, groups[client.room]


def is_admin(group, key):
    return key == group["owner"] or key in group["admins"]


@command("/groups", "/groups", "list all groups", "👥 Groups")
def cmd_groups(client, args):
    if not groups:
        client.say(f"No groups yet. Make one: /create name  (costs {GROUP_COST} 🪙)")
        return
    lines = ["👥 Groups:"]
    for key in sorted(groups):
        g = groups[key]
        here = sum(1 for m in g["members"] if m in online)
        mine = "  ✅ member" if client.key in g["members"] else ""
        lines.append(f"  {room_title(key)}  👥 {len(g['members'])} members, {here} online{mine}")
    lines.append("🔒 = private (needs approval). Join with /join name")
    client.say("\n".join(lines))


@command("/create", "/create name [private]", f"new group ({GROUP_COST} 🪙)", "👥 Groups")
def cmd_create(client, args):
    parts = args.split()
    if not parts:
        client.say("Usage: /create name   or   /create name private", "error")
        return
    name, key = parts[0], parts[0].lower()
    private = len(parts) > 1 and parts[1].lower() in ("private", "p")
    if not valid_name(name) or key == "lobby":
        client.say("❌ Group names: 3-16 letters, numbers or _", "error")
        return
    if key in groups:
        client.say("❌ That group already exists.", "error")
        return
    if sum(1 for g in groups.values() if g["owner"] == client.key) >= MAX_OWNED_GROUPS:
        client.say(f"👑 You can own at most {MAX_OWNED_GROUPS} groups. /disband one first.", "error")
        return
    account = accounts[client.key]
    if account["tokens"] < GROUP_COST:
        client.say(f"💸 Creating a group costs {GROUP_COST} 🪙, you have {account['tokens']}.", "error")
        return
    account["tokens"] -= GROUP_COST
    groups[key] = new_group(name, client.key, private)
    history[key] = deque(maxlen=HISTORY_SIZE)
    client.say(f"🎉 Created {room_title(key)} for {GROUP_COST} 🪙. You're the owner 👑\n"
               f"🏦 The group bank earns {GROUP_INCOME} 🪙/min while a member is online. See /bank", "event")
    announce(f"✨ New group: {room_title(key)} by {shown(client.key)}", exclude={client.key})
    move_to_room(client, key)
    unlock(client.key, "founder")
    save_data()


@command("/join", "/join name", "enter a group (or ask to)", "👥 Groups")
def cmd_join(client, args):
    name = args.strip()
    if not name:
        client.say("Usage: /join name   (see /groups)", "error")
        return
    if name.lower() == "lobby":
        cmd_lobby(client, "")
        return
    key = name.lower()
    group = groups.get(key)
    if group is None:
        client.say(f"❓ No group called {name}. See /groups", "error")
        return
    if client.key in group["banned"]:
        client.say(f"🚫 You're banned from {room_title(key)}.", "error")
        return
    if client.key in group["members"]:
        if client.room == key:
            client.say("You're already here.")
        else:
            move_to_room(client, key)
        return
    if not group["private"]:
        group["members"].append(client.key)
        save_data()
        move_to_room(client, key)
        return
    if client.key in group["requests"]:
        client.say("⏳ Your request is still waiting for an admin.")
        return
    group["requests"].append(client.key)
    save_data()
    client.say(f"📨 Request sent! An admin of {room_title(key)} has to approve you.")
    for admin in [group["owner"]] + group["admins"]:
        tell(admin, f"📨 {shown(client.key)} wants to join {room_title(key)}.  "
                    f"/approve {nick(client.key)} {group['name']}  or  /reject {nick(client.key)} {group['name']}",
             "event")


@command("/lobby", "/lobby", "go back to the lobby", "👥 Groups")
def cmd_lobby(client, args):
    if client.room == "lobby":
        client.say("You're already in the lobby.")
    else:
        move_to_room(client, "lobby")


@command("/leave", "/leave", "quit the group you're in", "👥 Groups")
def cmd_leave(client, args):
    key, group = current_group(client)
    if group is None:
        return
    if client.key == group["owner"]:
        client.say("👑 You own this group. Use /disband to delete it.", "error")
        return
    group["members"].remove(client.key)
    if client.key in group["admins"]:
        group["admins"].remove(client.key)
    save_data()
    move_to_room(client, "lobby")
    client.say(f"👋 You left {room_title(key)}.")


@command("/members", "/members", "who's in this group", "👥 Groups")
def cmd_members(client, args):
    key, group = current_group(client)
    if group is None:
        return
    lines = [f"👥 {room_title(key)}:"]
    for member in group["members"]:
        role = "👑 owner" if member == group["owner"] else "🛡️ admin" if member in group["admins"] else ""
        status = "🟢" if member in online else "⚫"
        muted = " 🔇" if mutes.get((key, member), 0) > time.time() else ""
        lines.append(f"  {status} {shown(member)} {role}{muted}")
    client.say("\n".join(lines))


@command("/requests", "/requests", "join requests (admins)", "👥 Groups")
def cmd_requests(client, args):
    key, group = current_group(client)
    if group is None:
        return
    if not is_admin(group, client.key):
        client.say("🛡️ Only group admins can see requests.", "error")
        return
    if not group["requests"]:
        client.say("📭 No one is waiting to join.")
        return
    names = ", ".join(nick(k) for k in group["requests"])
    client.say(f"📨 Waiting: {names}\nUse /approve name or /reject name")


def request_target(client, args):
    """For /approve and /reject: returns (group key, group, user) or None."""
    parts = args.split()
    if not parts:
        client.say("Usage: /approve name [group]", "error")
        return None
    key = parts[1].lower() if len(parts) > 1 else client.room
    group = groups.get(key)
    if group is None:
        client.say("❓ Which group? Use /approve name group", "error")
        return None
    if not is_admin(group, client.key):
        client.say("🛡️ Only group admins can do that.", "error")
        return None
    target = find_account(parts[0])
    if target not in group["requests"]:
        client.say(f"❓ {parts[0]} didn't ask to join {room_title(key)}.", "error")
        return None
    return key, group, target


@command("/approve", "/approve name [group]", "let someone in (admins)", "👥 Groups")
def cmd_approve(client, args):
    found = request_target(client, args)
    if found is None:
        return
    key, group, target = found
    group["requests"].remove(target)
    group["members"].append(target)
    save_data()
    tell(target, f"✅ You were accepted into {room_title(key)}! Type /join {group['name']}", "event")
    client.say(f"✅ {shown(target)} can now join.")
    notify_room(key, f"🎉 {shown(target)} is now a member of {room_title(key)}", exclude=client)


@command("/reject", "/reject name [group]", "turn down a request (admins)", "👥 Groups")
def cmd_reject(client, args):
    found = request_target(client, args)
    if found is None:
        return
    key, group, target = found
    group["requests"].remove(target)
    save_data()
    tell(target, f"❌ Your request to join {room_title(key)} was turned down.", "error")
    client.say(f"❌ Rejected {shown(target)}.")


# ----- 🛡️ Group admin

def admin_target(client, args, owner_only=False, must_be_member=True):
    """Checks for every admin command. Returns (group key, group, target) or None."""
    key, group = current_group(client)
    if group is None:
        return None
    allowed = client.key == group["owner"] if owner_only else is_admin(group, client.key)
    if not allowed:
        client.say("👑 Only the owner can do that." if owner_only else "🛡️ Only group admins can do that.",
                   "error")
        return None
    name = args.split()[0] if args.split() else ""
    target = find_account(name) if name else None
    if target is None:
        client.say(f"❓ No user called {name or '...'}.", "error")
        return None
    if target == client.key:
        client.say("🙃 You can't do that to yourself.", "error")
        return None
    if target == group["owner"]:
        client.say("👑 You can't do that to the owner.", "error")
        return None
    if target in group["admins"] and client.key != group["owner"]:
        client.say("🛡️ Only the owner can do that to another admin.", "error")
        return None
    if must_be_member and target not in group["members"]:
        client.say(f"❓ {nick(target)} isn't in this group.", "error")
        return None
    return key, group, target


def remove_from_group(key, group, target):
    group["members"].remove(target)
    if target in group["admins"]:
        group["admins"].remove(target)
    if target in online and online[target].room == key:
        move_to_room(online[target], "lobby")


@command("/kick", "/kick name", "remove from group", "🛡️ Group admin")
def cmd_kick(client, args):
    found = admin_target(client, args)
    if found:
        key, group, target = found
        remove_from_group(key, group, target)
        save_data()
        tell(target, f"👢 You were kicked from {room_title(key)} by {shown(client.key)}.", "error")
        notify_room(key, f"👢 {shown(target)} was kicked by {shown(client.key)}")


@command("/ban", "/ban name", "kick + can't come back", "🛡️ Group admin")
def cmd_ban(client, args):
    found = admin_target(client, args, must_be_member=False)
    if found:
        key, group, target = found
        if target in group["members"]:
            remove_from_group(key, group, target)
        if target in group["requests"]:
            group["requests"].remove(target)
        if target not in group["banned"]:
            group["banned"].append(target)
        save_data()
        tell(target, f"🔨 You were banned from {room_title(key)}.", "error")
        notify_room(key, f"🔨 {shown(target)} was banned by {shown(client.key)}")


@command("/unban", "/unban name", "allow back in", "🛡️ Group admin")
def cmd_unban(client, args):
    found = admin_target(client, args, must_be_member=False)
    if found:
        key, group, target = found
        if target not in group["banned"]:
            client.say(f"{nick(target)} isn't banned.")
            return
        group["banned"].remove(target)
        save_data()
        client.say(f"🕊️ {shown(target)} is unbanned.")


@command("/mute", "/mute name [minutes]", "silence someone (default 5)", "🛡️ Group admin")
def cmd_mute(client, args):
    found = admin_target(client, args)
    if found:
        key, group, target = found
        parts = args.split()
        minutes = int(parts[1]) if len(parts) > 1 and parts[1].isdecimal() else 5
        minutes = max(1, min(minutes, 1440))
        mutes[(key, target)] = time.time() + minutes * 60
        notify_room(key, f"🔇 {shown(target)} was muted for {minutes} min by {shown(client.key)}")
        if target not in online or online[target].room != key:
            tell(target, f"🔇 You were muted in {room_title(key)} for {minutes} min.", "error")


@command("/unmute", "/unmute name", "let them talk again", "🛡️ Group admin")
def cmd_unmute(client, args):
    found = admin_target(client, args)
    if found:
        key, group, target = found
        mutes.pop((key, target), None)
        notify_room(key, f"🔊 {shown(target)} can talk again")


@command("/promote", "/promote name", "make admin (owner)", "🛡️ Group admin")
def cmd_promote(client, args):
    found = admin_target(client, args, owner_only=True)
    if found:
        key, group, target = found
        if target in group["admins"]:
            client.say(f"{nick(target)} is already an admin.")
            return
        group["admins"].append(target)
        save_data()
        notify_room(key, f"🛡️ {shown(target)} is now an admin of {room_title(key)}")
        tell(target, f"🛡️ You're now an admin of {room_title(key)}!", "event")


@command("/demote", "/demote name", "remove admin (owner)", "🛡️ Group admin")
def cmd_demote(client, args):
    found = admin_target(client, args, owner_only=True)
    if found:
        key, group, target = found
        if target not in group["admins"]:
            client.say(f"{nick(target)} isn't an admin.")
            return
        group["admins"].remove(target)
        save_data()
        notify_room(key, f"⬇️ {shown(target)} is no longer an admin")


@command("/disband", "/disband", "delete your group (owner)", "🛡️ Group admin")
def cmd_disband(client, args):
    key, group = current_group(client)
    if group is None:
        return
    if client.key != group["owner"]:
        client.say("👑 Only the owner can disband the group.", "error")
        return
    title = room_title(key)
    for member in group["members"]:
        tell(member, f"💥 {title} was disbanded by its owner.", "event")
    if group["bank"]:
        accounts[client.key]["tokens"] += group["bank"]
        client.say(f"🏦 The group bank's {group['bank']} 🪙 went to you.", "money")
    for c in list(online.values()):
        if c.room == key:
            c.room = "lobby"
            c.send({"type": "history", "room": room_title("lobby"), "messages": list(history["lobby"])})
    del groups[key]
    del history[key]
    for mute in [m for m in mutes if m[0] == key]:
        del mutes[mute]
    save_data()


# ----- 🏦 Group bank

@command("/bank", "/bank", "the group's bank and upgrades", "🏦 Group bank")
def cmd_bank(client, args):
    key, group = current_group(client)
    if group is None:
        return
    online_members = sum(1 for m in group["members"] if m in online)
    lines = [f"🏦 {room_title(key)} bank: {group['bank']} 🪙",
             f"   earns {GROUP_INCOME} 🪙/min while a member is online ({online_members} online now)",
             "⬆️ Upgrades:"]
    for name, (icon, price, what) in GROUP_UPGRADES.items():
        state = "✅ owned" if name in group["upgrades"] else f"{price} 🪙"
        lines.append(f"  {icon} {name:<10} {state:<10} {what}")
    lines.append("Admins buy with /upgrade name.  Anyone can chip in with /donate amount.")
    client.say("\n".join(lines), "money")


@command("/donate", "/donate amount", "put your tokens in the group bank", "🏦 Group bank")
def cmd_donate(client, args):
    key, group = current_group(client)
    if group is None:
        return
    amount = parse_amount(client, args)
    if amount is None:
        return
    accounts[client.key]["tokens"] -= amount
    group["bank"] += amount
    notify_room(key, f"🤝 {shown(client.key)} donated {amount} 🪙 to the bank (now {group['bank']} 🪙)",
                kind="money")
    if amount >= TEAM_PLAYER_DONATION:  # a 1-token donation shouldn't earn a 50-token achievement
        unlock(client.key, "team_player")
    save_data()


@command("/upgrade", "/upgrade name", "buy an upgrade with the bank (admins)", "🏦 Group bank")
def cmd_upgrade(client, args):
    key, group = current_group(client)
    if group is None:
        return
    name = args.strip().lower()
    if name not in GROUP_UPGRADES:
        cmd_bank(client, "")
        return
    if not is_admin(group, client.key):
        client.say("🛡️ Only group admins can spend the bank.", "error")
        return
    icon, price, what = GROUP_UPGRADES[name]
    if name in group["upgrades"]:
        client.say(f"{icon} {room_title(key)} already has that.")
        return
    if group["bank"] < price:
        client.say(f"💸 {icon} {name} costs {price} 🪙, the bank has {group['bank']}.", "error")
        return
    group["bank"] -= price
    group["upgrades"].append(name)
    if name == "history":
        history[key] = deque(history[key], maxlen=BIG_HISTORY_SIZE)
    save_data()
    notify_room(key, f"⬆️ {shown(client.key)} bought {icon} {name}: {what}!", kind="event")
    if name == "emoji":
        client.say("🎨 Now pick it: /groupemoji 🔥")


@command("/groupemoji", "/groupemoji emoji", "set the group emoji (needs 🎨)", "🏦 Group bank")
def cmd_groupemoji(client, args):
    key, group = current_group(client)
    if group is None:
        return
    if not is_admin(group, client.key):
        client.say("🛡️ Only group admins can do that.", "error")
        return
    if "emoji" not in group["upgrades"]:
        client.say("🎨 Buy the emoji upgrade first: /upgrade emoji", "error")
        return
    emoji = args.strip()
    # Only emoji pieces: symbols (So, Sk) plus the invisible joiners and variation marks (Mn, Cf)
    if not emoji or len(emoji) > 8 or any(unicodedata.category(ch) not in ("So", "Sk", "Mn", "Cf")
                                          for ch in emoji):
        client.say("🎨 Send a single emoji, like /groupemoji 🔥", "error")
        return
    group["emoji"] = emoji
    save_data()
    notify_room(key, f"🎨 The group is now {room_title(key)}", kind="event")


@command("/topgroups", "/topgroups", "richest groups", "🏦 Group bank")
def cmd_topgroups(client, args):
    if not groups:
        client.say("No groups yet.")
        return
    ranking = sorted(groups, key=lambda k: groups[k]["bank"], reverse=True)[:10]
    lines = ["🏦 Richest groups:"]
    for i, key in enumerate(ranking, 1):
        g = groups[key]
        lines.append(f"  {i}. {room_title(key)}  {g['bank']} 🪙  ⬆️ {len(g['upgrades'])} upgrades")
    client.say("\n".join(lines), "money")


# ----- 🪙 Tokens

@command("/balance", "/balance [name]", "how many tokens 🪙", "🪙 Tokens")
def cmd_balance(client, args):
    key = find_account(args.strip()) if args.strip() else client.key
    if key is None:
        client.say(f"❓ No one called {args.strip()}.", "error")
        return
    client.say(f"🪙 {shown(key)} has {accounts[key]['tokens']} tokens.", "money")


@command("/top", "/top", "richest players 🏆", "🪙 Tokens")
def cmd_top(client, args):
    ranking = sorted(accounts, key=lambda k: accounts[k]["tokens"], reverse=True)[:10]
    medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, 11)]
    lines = ["🏆 Richest players:"]
    for medal, key in zip(medals, ranking):
        lines.append(f"  {medal} {shown(key)}  {accounts[key]['tokens']} 🪙")
    client.say("\n".join(lines), "money")


@command("/give", "/give name amount", "send tokens to someone", "🪙 Tokens")
def cmd_give(client, args):
    parts = args.split()
    if len(parts) != 2:
        client.say("Usage: /give name amount", "error")
        return
    target = find_account(parts[0])
    if target is None or target == client.key:
        client.say("❓ Give to who?", "error")
        return
    amount = parse_amount(client, parts[1])
    if amount is None:
        return
    accounts[client.key]["tokens"] -= amount
    accounts[target]["tokens"] += amount
    client.say(f"🎁 You gave {amount} 🪙 to {shown(target)}.", "money")
    tell(target, f"🎁 {shown(client.key)} gave you {amount} 🪙!", "money")
    check_rich(target)
    save_data()


@command("/daily", "/daily", "free tokens every day, more for streaks 🔥", "🪙 Tokens")
def cmd_daily(client, args):
    account = accounts[client.key]
    since = time.time() - account["last_daily"]
    if since < 20 * 3600:
        wait = 20 * 3600 - since
        client.say(f"⏳ Come back in {int(wait // 3600)}h {int(wait % 3600 // 60)}m. "
                   f"🔥 Streak: {account['streak']} days", "error")
        return
    # Claim again within 48 hours to keep the streak going
    account["streak"] = account["streak"] + 1 if since < 48 * 3600 else 1
    reward = min(DAILY_BONUS + STREAK_BONUS * (account["streak"] - 1), DAILY_MAX)
    account["last_daily"] = time.time()
    account["tokens"] += reward
    tomorrow = min(reward + STREAK_BONUS, DAILY_MAX)
    client.say(f"🎁 +{reward} 🪙 daily bonus!  🔥 {account['streak']} day streak\n"
               f"   Come back in 20-48 hours for {tomorrow} 🪙 (wait longer and the streak resets).", "money")
    if account["streak"] >= 7:
        unlock(client.key, "on_fire")
    check_rich(client.key)
    save_data()


@command("/rob", "/rob name", "40% chance to steal, or pay a fine 🦹", "🪙 Tokens")
def cmd_rob(client, args):
    target = find_online(client, args.strip())
    if target is None:
        return
    if target == client.key:
        client.say("🙃 Robbing yourself? Bold.", "error")
        return
    wait = last_rob.get(client.key, 0) + 300 - time.time()
    if wait > 0:
        client.say(f"🚓 Lay low for {int(wait // 60)}m {int(wait % 60)}s before robbing again.", "error")
        return
    victim, robber = accounts[target], accounts[client.key]
    if victim["tokens"] < 50:
        client.say(f"🤷 {nick(target)} is too broke to rob.", "error")
        return
    last_rob[client.key] = time.time()
    if random.random() < 0.4:
        stolen = min(500, max(1, victim["tokens"] * random.randint(5, 15) // 100))
        victim["tokens"] -= stolen
        robber["tokens"] += stolen
        client.say(f"🦹 Success! You stole {stolen} 🪙 from {shown(target)}.", "money")
        tell(target, f"🚨 {shown(client.key)} robbed you and got away with {stolen} 🪙!", "error")
        unlock(client.key, "bandit")
        check_rich(client.key)
    else:
        fine = min(50, robber["tokens"])
        robber["tokens"] -= fine
        victim["tokens"] += fine
        client.say(f"🚓 Caught! You paid {fine} 🪙 to {shown(target)}.", "error")
        tell(target, f"🛡️ {shown(client.key)} tried to rob you and failed. You got {fine} 🪙!", "money")
    save_data()


@command("/shop", "/shop", "badges for your name", "🪙 Tokens")
def cmd_shop(client, args):
    owned = accounts[client.key]["badges"]
    lines = ["🛒 Badge shop (shows next to your name):"]
    for badge, price in SHOP.items():
        lines.append(f"  {badge}  {price} 🪙{'  ✅ owned' if badge in owned else ''}")
    lines.append("Buy with /buy 🔥   Switch with /badge 😎   Hide with /badge off")
    client.say("\n".join(lines), "money")


@command("/buy", "/buy badge", "buy a badge from /shop", "🪙 Tokens")
def cmd_buy(client, args):
    badge = args.strip()
    account = accounts[client.key]
    if badge not in SHOP:
        client.say("❓ That's not in the /shop. Copy the emoji exactly.", "error")
        return
    if badge in account["badges"]:
        client.say("You already own it. Wear it with /badge " + badge)
        return
    if account["tokens"] < SHOP[badge]:
        client.say(f"💸 {badge} costs {SHOP[badge]} 🪙, you have {account['tokens']}.", "error")
        return
    account["tokens"] -= SHOP[badge]
    account["badges"].append(badge)
    account["badge"] = badge
    save_data()
    client.say(f"🛍️ You bought {badge}! You're now {shown(client.key)}", "money")
    if SHOP[badge] >= 1000:
        announce(f"💸 {shown(client.key)} just bought the {badge} badge!", exclude={client.key})


@command("/badge", "/badge emoji|off", "wear a badge you own", "🪙 Tokens")
def cmd_badge(client, args):
    choice = args.strip()
    account = accounts[client.key]
    if choice == "off":
        account["badge"] = ""
    elif choice in account["badges"]:
        account["badge"] = choice
    else:
        client.say(f"You don't own that. Yours: {' '.join(account['badges']) or 'none, see /shop'}", "error")
        return
    save_data()
    client.say(f"✨ You're now {shown(client.key)}")


# ----- 🎰 Casino

def gamble_result(client, bet, payout, text, game):
    """payout = total tokens returned (0 = lost the bet)."""
    account = accounts[client.key]
    account["tokens"] += payout - bet
    net = payout - bet
    if net > 0:
        outcome = f"🎉 You won {net} 🪙!"
    elif net == 0:
        outcome = "😐 You got your bet back."
    else:
        outcome = f"😢 You lost {bet} 🪙."
    client.say(f"{text}\n{outcome}  Balance: {account['tokens']} 🪙", "money" if net >= 0 else "error")
    if net >= 500:
        announce(f"🎰💥 {shown(client.key)} just won {net} 🪙 on {game}!", exclude={client.key})
    if bet >= 500:
        unlock(client.key, "high_roller")
    check_rich(client.key)
    save_data()


@command("/coinflip", "/coinflip amount heads|tails", "double or nothing", "🎰 Casino")
def cmd_coinflip(client, args):
    parts = args.split()
    if len(parts) != 2 or parts[1].lower() not in ("heads", "tails", "h", "t"):
        client.say("Usage: /coinflip amount heads   (or tails)", "error")
        return
    bet = parse_amount(client, parts[0])
    if bet is None:
        return
    guess = "heads" if parts[1].lower().startswith("h") else "tails"
    side = random.choice(["heads", "tails"])
    gamble_result(client, bet, bet * 2 if side == guess else 0, f"🪙 The coin spins... {side.upper()}!", "coinflip")


@command("/dice", "/dice amount", "2 dice vs the house 🎲", "🎰 Casino")
def cmd_dice(client, args):
    bet = parse_amount(client, args)
    if bet is None:
        return
    faces = "⚀⚁⚂⚃⚄⚅"
    you = [random.randint(1, 6) for _ in range(2)]
    house = [random.randint(1, 6) for _ in range(2)]
    text = (f"🎲 You: {faces[you[0] - 1]} {faces[you[1] - 1]} = {sum(you)}   "
            f"House: {faces[house[0] - 1]} {faces[house[1] - 1]} = {sum(house)}")
    payout = bet * 2 if sum(you) > sum(house) else bet if sum(you) == sum(house) else 0
    gamble_result(client, bet, payout, text, "dice")


@command("/slots", "/slots amount", "3 same = x10, 💎💎💎 = x25", "🎰 Casino")
def cmd_slots(client, args):
    bet = parse_amount(client, args)
    if bet is None:
        return
    reels = random.choices(SLOT_SYMBOLS, k=3)
    if reels == ["💎"] * 3:
        multiplier = 25
    elif len(set(reels)) == 1:
        multiplier = 10
    elif len(set(reels)) == 2:
        multiplier = 1.5
    else:
        multiplier = 0
    gamble_result(client, bet, int(bet * multiplier), f"🎰 [ {' | '.join(reels)} ]", "slots")
    if multiplier >= 10:
        unlock(client.key, "jackpot")
        save_data()  # gamble_result already saved, before this achievement


# ----- 🎮 Games

class Match:
    def __init__(self, game_class, p1, p2, bet):
        first, second = random.sample([p1, p2], 2)  # random player goes first
        self.game = game_class(first, second)
        self.players = [first, second]
        self.bet = bet
        self.over = False
        self.moves = {first: 0, second: 0}  # accepted moves per player

    def opponent(self, key):
        return self.players[1] if key == self.players[0] else self.players[0]


def push_board(match, note=""):
    p1, p2 = match.players
    header = f"{match.game.title}   {shown(p1)} vs {shown(p2)}"
    for p in match.players:
        if p in online:
            text = f"\n{header}\n{match.game.render(p)}" + (f"\n{note}" if note else "")
            # "state" is the board as data: the terminal ignores it, the website draws it
            online[p].send({"type": "msg", "kind": "board", "text": text, "state": match.game.state(p)})


def start_match(game_class, p1, p2, bet):
    match = Match(game_class, p1, p2, bet)
    for p in (p1, p2):
        accounts[p]["tokens"] -= bet  # both bets go into the pot
    matches[p1] = matches[p2] = match
    pot = f"   💰 pot: {bet * 2} 🪙" if bet else ""
    for p in match.players:
        tell(p, f"🎮 {game_class.title}: {shown(p1)} vs {shown(p2)}{pot}\n"
                f"📜 {game_class.help}\n🏳️ /resign to give up", "game")
    push_board(match)


def finish_match(match, winner, reason=""):
    if match.over:
        return
    match.over = True
    for p in match.players:
        matches.pop(p, None)
    p1, p2 = match.players
    title = match.game.title
    reason = f" ({reason})" if reason else ""
    if winner == "draw" or winner is None:
        for p in match.players:
            accounts[p]["tokens"] += match.bet
            accounts[p]["draws"] += 1
            tell(p, f"🤝 Draw!{reason}" + (" Bets refunded." if match.bet else ""), "game")
    else:
        loser = match.opponent(winner)
        account = accounts[winner]
        pot = match.bet * 2
        account["tokens"] += pot
        account["wins"] += 1
        accounts[loser]["losses"] += 1
        # Free reward for winning, capped per day so two friends can't farm each other.
        # A resign or disconnect before both really played earns no reward (only the pot).
        if account["win_day"] != today():
            account["win_day"], account["rewarded_wins"] = today(), 0
        really_played = match.game.finished or min(match.moves.values()) >= MIN_MOVES_FOR_BONUS
        bonus = ""
        if really_played and account["rewarded_wins"] < MAX_REWARDED_WINS:
            account["rewarded_wins"] += 1
            account["tokens"] += WIN_REWARD
            bonus = f" +{WIN_REWARD} 🪙 win reward ({account['rewarded_wins']}/{MAX_REWARDED_WINS} today)"
        tell(winner, f"🏆 YOU WON!{reason}" + (f" +{pot} 🪙 pot" if pot else "") + bonus, "money")
        tell(loser, f"💀 You lost.{reason}", "error")
        prize = f" and took {pot} 🪙" if pot else ""
        announce(f"🏆 {shown(winner)} beat {shown(loser)} at {title}{prize}!", exclude={p1, p2})
        unlock(winner, "first_win")
        if account["wins"] >= 10:
            unlock(winner, "ten_wins")
        check_rich(winner)
    save_data()


def end_all_matches():
    """The server is stopping: cancel every running game and give the bets back."""
    for match in set(matches.values()):
        match.over = True
        for p in match.players:
            matches.pop(p, None)
            accounts[p]["tokens"] += match.bet
            tell(p, "🛑 The server is stopping, so your game was cancelled."
                 + (" Your bet was refunded." if match.bet else ""), "game")


def do_move(client, text):
    match = matches.get(client.key)
    if match is None:
        client.say("🎮 You're not in a game. /challenge someone!", "error")
        return
    ok, info = match.game.move(client.key, text)
    if not ok:
        client.say(info, "error")
        return
    match.moves[client.key] += 1
    push_board(match, info)
    if match.game.finished:
        finish_match(match, match.game.winner)


@command("/games", "/games", "what you can play", "🎮 Games")
def cmd_games(client, args):
    client.say("🎮 Games (1v1, optional token bet):\n"
               "  ❌⭕ ttt        Tic-Tac-Toe\n"
               "  🔴🔵 damka      Checkers (also: checkers)\n"
               "  ➗   math       Math duel: first to 3 right answers\n"
               "Challenge: /challenge name game [bet]   e.g.  /challenge Adi damka 100\n\n"
               "🟩 Solo: /wordle  guess the word, win up to 60 🪙", "game")


@command("/challenge", "/challenge name game [bet]", "invite to a 1v1", "🎮 Games")
def cmd_challenge(client, args):
    parts = args.split()
    if len(parts) < 2:
        client.say("Usage: /challenge name game [bet]   games: ttt, damka, math", "error")
        return
    target = find_online(client, parts[0])
    if target is None:
        return
    game_class = GAMES.get(parts[1].lower())
    if game_class is None:
        client.say("❓ Games: ttt, damka (checkers), math", "error")
        return
    if target == client.key:
        client.say("🙃 You can't challenge yourself.", "error")
        return
    bet = 0
    if len(parts) > 2:
        bet = parse_amount(client, parts[2])
        if bet is None:
            return
    if client.key in matches or target in matches:
        client.say("⏳ One of you is already in a game.", "error")
        return
    if accounts[target]["tokens"] < bet:
        client.say(f"💸 {nick(target)} can't afford a {bet} 🪙 bet.", "error")
        return
    waiting = [i for i in invites.get(target, []) if i["from"] != client.key]
    waiting.append({"from": client.key, "game": game_class, "bet": bet, "time": time.time()})
    invites[target] = waiting
    stake = f" for {bet} 🪙" if bet else ""
    tell(target, f"⚔️ {shown(client.key)} challenges you to {game_class.title}{stake}!  "
                 f"/accept {nick(client.key)}  or  /decline {nick(client.key)}", "event")
    client.say(f"⚔️ Challenge sent to {shown(target)}. Waiting for them...")


def pick_invite(client, args):
    fresh = [i for i in invites.get(client.key, []) if time.time() - i["time"] < 180]
    invites[client.key] = fresh
    if not fresh:
        client.say("📭 No challenges waiting for you.", "error")
        return None
    if args.strip():
        invite = next((i for i in fresh if nick(i["from"]).lower() == args.strip().lower()), None)
        if invite is None:
            client.say(f"❓ No challenge from {args.strip()}.", "error")
            return None
    else:
        invite = fresh[-1]
    fresh.remove(invite)
    return invite


@command("/accept", "/accept [name]", "accept a challenge", "🎮 Games")
def cmd_accept(client, args):
    invite = pick_invite(client, args)
    if invite is None:
        return
    challenger, bet = invite["from"], invite["bet"]
    if challenger not in online:
        client.say("😕 They left already.", "error")
        return
    if challenger in matches or client.key in matches:
        client.say("⏳ One of you is already in a game.", "error")
        return
    if accounts[challenger]["tokens"] < bet or accounts[client.key]["tokens"] < bet:
        client.say("💸 Someone can't afford the bet anymore.", "error")
        return
    start_match(invite["game"], challenger, client.key, bet)


@command("/decline", "/decline [name]", "say no to a challenge", "🎮 Games")
def cmd_decline(client, args):
    invite = pick_invite(client, args)
    if invite:
        client.say("👎 Declined.")
        tell(invite["from"], f"👎 {shown(client.key)} declined your challenge.", "error")


@command("/move", "/move ...", "a move (or just type it)", "🎮 Games")
def cmd_move(client, args):
    do_move(client, args)


@command("/board", "/board", "show the board again", "🎮 Games")
def cmd_board(client, args):
    match = matches.get(client.key)
    if match is None:
        client.say("🎮 You're not in a game.", "error")
        return
    p1, p2 = match.players
    client.send({"type": "msg", "kind": "board", "state": match.game.state(client.key),
                 "text": f"{match.game.title}   {shown(p1)} vs {shown(p2)}\n{match.game.render(client.key)}"})


@command("/resign", "/resign", "give up the game 🏳️", "🎮 Games")
def cmd_resign(client, args):
    match = matches.get(client.key)
    if match is None:
        client.say("🎮 You're not in a game.", "error")
        return
    finish_match(match, match.opponent(client.key), f"{nick(client.key)} resigned 🏳️")


# ----- 🟩 Solo: Wordle

def send_wordle(client, game, text):
    client.send({"type": "msg", "kind": "board", "text": text, "state": game.state()})


@command("/wordle", "/wordle", "solo word game, win tokens 🟩", "🎮 Games")
def cmd_wordle(client, args):
    game = solo.get(client.key)
    if game and not game.finished:
        send_wordle(client, game, f"{games.Wordle.title} (still going)\n{game.render()}")
        return
    solo[client.key] = game = games.Wordle()
    account = accounts[client.key]
    left = SOLO_MAX_REWARDS - (account["solo_rewarded"] if account["solo_day"] == today() else 0)
    prize = f"Win up to 60 🪙 ({left} rewarded games left today)" if left > 0 else \
        "No more rewards today, but you can still play for fun"
    send_wordle(client, game, f"{games.Wordle.title}\n📜 {games.Wordle.help}\n🪙 {prize}\n\n{game.render()}")


@command("/g", "/g word", "guess in your Wordle", "🎮 Games")
def cmd_guess(client, args):
    game = solo.get(client.key)
    if game is None or game.finished:
        client.say("🟩 Start a game first: /wordle", "error")
        return
    ok, info = game.guess(args)
    if not ok:
        client.say(info, "error")
        return
    send_wordle(client, game, f"\n{game.render()}")
    if not game.finished:
        return
    del solo[client.key]
    if not game.won:
        client.say(f"💀 Out of tries! The word was {game.answer.upper()}.", "error")
        return
    account = accounts[client.key]
    tries = len(game.guesses)
    if account["solo_day"] != today():
        account["solo_day"], account["solo_rewarded"] = today(), 0
    if account["solo_rewarded"] < SOLO_MAX_REWARDS:
        account["solo_rewarded"] += 1
        account["tokens"] += game.reward()
        client.say(f"🎉 Solved in {tries}/6! +{game.reward()} 🪙 "
                   f"({account['solo_rewarded']}/{SOLO_MAX_REWARDS} rewarded today)", "money")
    else:
        client.say(f"🎉 Solved in {tries}/6! (No more token rewards today.)", "money")
    announce(f"🟩 {shown(client.key)} solved Wordle in {tries}/6!\n{game.share()}", exclude={client.key})
    unlock(client.key, "wordsmith")
    if tries <= 3:
        unlock(client.key, "genius")
    check_rich(client.key)
    save_data()


@command("/giveup", "/giveup", "quit your Wordle", "🎮 Games")
def cmd_giveup(client, args):
    game = solo.pop(client.key, None)
    if game is None:
        client.say("🟩 You're not playing Wordle.", "error")
        return
    client.say(f"🏳️ The word was {game.answer.upper()}.")


# ----- 🛠️ Admin

def admin_password():
    """HASHBROWN_ADMIN_PASSWORD wins, otherwise ADMIN_PASSWORD at the top. Never print this."""
    return os.environ.get("HASHBROWN_ADMIN_PASSWORD", "").strip() or ADMIN_PASSWORD


@command("/admin", "/admin password", "become a server admin", "🛠️ Admin")
def cmd_admin(client, args):
    account = accounts[client.key]
    if account["admin"]:
        client.say("🛠️ You're already an admin. Try /admintokens")
        return
    password = admin_password()
    if password == DEFAULT_ADMIN_PASSWORD:
        client.say("🔒 /admin is disabled until the host changes the admin password.", "error")
        return
    # Wrong tries from ALL accounts count together, so making extra accounts doesn't give more guesses
    now = time.time()
    admin_fail_times[:] = [t for t in admin_fail_times if now - t < ADMIN_FAIL_WINDOW]
    if len(admin_fail_times) >= ADMIN_FAIL_LIMIT:
        client.say("🔒 Too many wrong admin passwords. Try again in 10 minutes.", "error")
        return
    if not secrets.compare_digest(args.strip().encode("utf-8", "replace"), password.encode("utf-8", "replace")):
        admin_fail_times.append(now)
        client.say("❌ Wrong admin password.", "error")
        log(f"[SERVER] ⚠️ {nick(client.key)} typed a wrong /admin password")
        return
    account["admin"] = True
    save_data()
    client.say("🛠️ You're now an admin! Try /admintokens", "event")
    log(f"[SERVER] {nick(client.key)} became an admin")


@command("/admintokens", "/admintokens [name]", f"admin: +{ADMIN_TOKENS} 🪙", "🛠️ Admin")
def cmd_admintokens(client, args):
    if not accounts[client.key]["admin"]:
        client.say("🛠️ Admins only. Use /admin password first.", "error")
        return
    target = find_account(args.strip()) if args.strip() else client.key
    if target is None:
        client.say(f"❓ No one called {args.strip()}.", "error")
        return
    accounts[target]["tokens"] += ADMIN_TOKENS
    client.say(f"🛠️ +{ADMIN_TOKENS} 🪙 to {shown(target)}.", "money")
    if target != client.key:
        tell(target, f"🎁 An admin gave you {ADMIN_TOKENS} 🪙!", "money")
    log(f"[SERVER] {nick(client.key)} used /admintokens on {nick(target)}")
    check_rich(target)
    save_data()


# ----- 📁 Files

@command("/sendfile", "/sendfile name path", "send a file (up to 2 MB) 📁", "📁 Files")
def cmd_sendfile(client, args):
    client.say("📁 Your client.py is too old for files. Get the new one.", "error")


def handle_file(client, msg):
    target = find_online(client, clean_text(msg.get("to", "")))
    if target is None:
        return
    if target == client.key:
        client.say("🙃 You can't send a file to yourself.", "error")
        return
    data = msg.get("data")
    if not isinstance(data, str) or len(data) > MAX_FILE_B64:
        client.say("📁 Files must be 2 MB or less.", "error")
        return
    filename = os.path.basename(clean_text(msg.get("filename", "")).replace("\\", "/"))[:100] or "file"
    online[target].send({"type": "file", "from": nick(client.key), "filename": filename, "data": data})
    client.say(f"📤 Sent {filename} ({len(data) * 3 // 4 // 1024 + 1} KB) to {shown(target)}.")


# ----- 🏅 Achievements

@command("/achievements", "/achievements", "your trophies and how to get the rest", "🪙 Tokens")
def cmd_achievements(client, args):
    owned = accounts[client.key]["achievements"]
    lines = [f"🏅 Achievements ({len(owned)}/{len(ACHIEVEMENTS)}):"]
    for name, (icon, title, how, reward) in ACHIEVEMENTS.items():
        mark = "✅" if name in owned else "🔒"
        lines.append(f"  {mark} {icon} {title:<17} {how}  (+{reward} 🪙)")
    client.say("\n".join(lines), "money")


# ----- 🥔 Hashbrown (GPT on Microsoft Foundry)

def is_placeholder(value):
    """True if a setting is missing, empty, or still the template text (like PASTE-YOUR-KEY-HERE)."""
    value = str(value or "").strip()
    return not value or "PASTE" in value or "YOUR-" in value or "YOUR_" in value


def hashbrown_key(config):
    """The API key: the HASHBROWN_API_KEY environment variable wins, otherwise api_key from
    hashbrown_config.json. Returns "" if neither has a real key.
    Never print, log or save what this returns, not even part of it."""
    key = os.environ.get("HASHBROWN_API_KEY", "").strip() or str(config.get("api_key") or "").strip()
    return "" if is_placeholder(key) else key


def load_hashbrown():
    """Read hashbrown_config.json. Returns the settings, or None if Hashbrown is off."""
    if not os.path.exists(HASHBROWN_CONFIG):
        template = {"endpoint": "https://YOUR-RESOURCE.services.ai.azure.com/openai/v1",
                    "deployment": "gpt-6.1-terra",
                    "api_key": "PASTE-YOUR-KEY-HERE"}
        with open(HASHBROWN_CONFIG, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2)
        log(f"[HASHBROWN] 🥔 Created {HASHBROWN_CONFIG}.")
    try:
        with open(HASHBROWN_CONFIG, encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, ValueError) as e:
        # Only the error's type: its message could quote bytes from the file
        log(f"[HASHBROWN] Can't read {HASHBROWN_CONFIG} ({type(e).__name__}). Hashbrown is off.")
        return None
    if not isinstance(config, dict):
        log(f"[HASHBROWN] {HASHBROWN_CONFIG} should be a JSON object. Hashbrown is off.")
        return None
    config["api_key"] = hashbrown_key(config)
    if not config["api_key"]:
        log("[HASHBROWN] 🥔 No API key, so Hashbrown is off. Set the HASHBROWN_API_KEY environment variable "
            "and restart the server.")
        return None
    if is_placeholder(config.get("endpoint")) or is_placeholder(config.get("deployment")):
        log(f"[HASHBROWN] 🥔 Fill in endpoint and deployment in {HASHBROWN_CONFIG}. Hashbrown is off.")
        return None
    # Works with https://NAME.openai.azure.com/ or https://NAME.services.ai.azure.com/
    endpoint = str(config["endpoint"]).strip().rstrip("/")
    if not endpoint.endswith("/openai/v1"):
        endpoint += "/openai/v1"
    config["url"] = endpoint + "/responses"
    log(f"[HASHBROWN] 🥔 Awake! Using deployment '{config['deployment']}'")
    return config


HASHBROWN_HINTS = {401: "the API key (HASHBROWN_API_KEY) is wrong",
                   403: "this key isn't allowed to use the resource",
                   404: "the endpoint or deployment name in hashbrown_config.json is wrong",
                   429: "too many requests or out of quota, wait a bit"}


def call_hashbrown(messages):
    """Send the conversation to Foundry (Responses API, the same one as client.responses.create)
    and return the answer text. Slow: never call this while holding the lock."""
    if hashbrown is None:  # no key: never contact Foundry
        raise RuntimeError("Hashbrown is off (no API key)")
    body = json.dumps({
        "model": hashbrown["deployment"],
        "instructions": messages[0]["content"],  # the system prompt
        "input": messages[1:],                  # the chat + question
        "max_output_tokens": 4000,              # thinking models use some of this to think
    }).encode()
    request = urllib.request.Request(hashbrown["url"], data=body, method="POST", headers={
        "Content-Type": "application/json",
        "api-key": hashbrown["api_key"],
    })
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        hint = HASHBROWN_HINTS.get(e.code, "")
        raise RuntimeError(f"HTTP {e.code} ({hint}): {detail}") from None
    # The answer is in output -> items of type "message" -> parts of type "output_text"
    # (there can also be a "reasoning" item first, which we skip)
    parts = []
    for item in data.get("output", []):
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    parts.append(part.get("text", ""))
    answer = "".join(parts).strip()
    if not answer:
        raise RuntimeError(f"no answer text (status: {data.get('status')})")
    return answer[:1500]


def ask_hashbrown(client, question):
    global hashbrown_busy, hashbrown_all_today
    if hashbrown is None:
        client.say("🥔💤 Hashbrown is asleep (the server owner hasn't set it up yet).", "error")
        return
    if not question:
        client.say("🥔 Ask something! Like: @hashbrown tell me a joke", "error")
        return
    key, room = client.key, client.room
    wait = hashbrown_last.get(key, 0) + HASHBROWN_COOLDOWN - time.time()
    if wait > 0:
        client.say(f"🥔 Hashbrown needs a breather. Ask again in {int(wait) + 1}s.", "error")
        return
    day, asked = hashbrown_today.get(key, ("", 0))
    if day != today():
        day, asked = today(), 0
    if asked >= HASHBROWN_DAILY_LIMIT:
        client.say(f"🥔 You've asked {HASHBROWN_DAILY_LIMIT} questions today. Come back tomorrow!", "error")
        return
    all_day, all_asked = hashbrown_all_today
    if all_day != today():
        all_day, all_asked = today(), 0
    if all_asked >= HASHBROWN_DAILY_CAP:
        client.say(f"🥔😴 Hashbrown already answered {HASHBROWN_DAILY_CAP} questions today and is taking "
                   f"a nap. Ask again tomorrow!", "error")
        return
    if hashbrown_busy >= HASHBROWN_MAX_BUSY:
        client.say("🥔 Hashbrown is busy answering others. Try again in a few seconds.", "error")
        return

    # Give it the recent chat so it knows what everyone is talking about
    recent = "\n".join(f"{m['name']}: {m['text']}" for m in list(history[room])[-10:])
    messages = [{"role": "system", "content": HASHBROWN_PROMPT},
                {"role": "user", "content": f"Recent chat:\n{recent}\n\n{nick(key)} asks you: {question}"}]

    # Who pays: the group bank (with the 🥔 upgrade) or the person asking.
    # We remember the group itself, not just its name: it could be disbanded (and a new group
    # with the same name created) before the answer comes back.
    group = groups.get(room)
    if group and "hashbrown" in group["upgrades"] and group["bank"] >= HASHBROWN_COST:
        group["bank"] -= HASHBROWN_COST
        payer = ("group", group)
    elif accounts[key]["tokens"] >= HASHBROWN_COST:
        accounts[key]["tokens"] -= HASHBROWN_COST
        payer = ("user", key)
    else:
        client.say(f"💸 Asking Hashbrown costs {HASHBROWN_COST} 🪙.", "error")
        return

    hashbrown_last[key] = time.time()
    hashbrown_today[key] = (day, asked + 1)
    hashbrown_all_today = (all_day, all_asked + 1)
    hashbrown_busy += 1
    notify_room(room, "🥔 Hashbrown is thinking...", kind="event")
    threading.Thread(target=hashbrown_worker, args=(key, room, group, messages, payer), daemon=True).start()


def refund_hashbrown(asker, payer):
    """The question failed: give the tokens back and don't count it as one of today's questions."""
    global hashbrown_all_today
    kind, who = payer
    if kind == "user" and who in accounts:
        accounts[who]["tokens"] += HASHBROWN_COST
    elif kind == "group" and groups.get(who["name"].lower()) is who:
        who["bank"] += HASHBROWN_COST
    elif kind == "group" and who["owner"] in accounts:  # the group is gone: its bank went to the owner
        accounts[who["owner"]]["tokens"] += HASHBROWN_COST
    day, asked = hashbrown_today.get(asker, ("", 0))
    if day == today() and asked > 0:
        hashbrown_today[asker] = (day, asked - 1)
    all_day, all_asked = hashbrown_all_today
    if all_day == today() and all_asked > 0:
        hashbrown_all_today = (all_day, all_asked - 1)


def hashbrown_worker(asker, room, group, messages, payer):
    """Runs in its own thread so the chat keeps working while the AI thinks.
    `group` is the group the question was asked in (None in the lobby)."""
    global hashbrown_busy
    try:
        answer, error = clean_text(call_hashbrown(messages), keep_newlines=True), None
    except Exception as e:  # network down, bad key, timeout... the chat must survive all of it
        answer, error = None, e
    with lock:
        hashbrown_busy -= 1
        room_still_there = groups.get(room) is group  # True for the lobby too (None is None)
        if answer is None:
            log(f"[HASHBROWN] Error: {type(error).__name__}: {error}")
            refund_hashbrown(asker, payer)
            oops = "🥔💥 Hashbrown tripped over something and couldn't answer. The tokens were refunded."
            if room_still_there:
                notify_room(room, oops, kind="error")
            else:
                tell(asker, oops, "error")
            return
        if room_still_there:
            msg = chat_message("Hashbrown", "🥔", answer)
            history[room].append(msg)
            send_room(room, msg)
            log(f"[{room}] Hashbrown: {answer}")
        else:  # the group was disbanded while Hashbrown thought: answer just the asker
            tell(asker, f"🥔 Hashbrown (only you): {answer}", "private")
        if asker in accounts:
            unlock(asker, "potato")
            save_data()


@command("/ask", "/ask question", f"ask Hashbrown, the AI ({HASHBROWN_COST} 🪙)", "🥔 Hashbrown")
def cmd_ask(client, args):
    if post_chat(client, "@hashbrown " + args):
        ask_hashbrown(client, args)


# ---------------------------------------------------------------- chat lines

def hang_up(client):
    try:
        client.sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def chat_message(name, badge, text, action=False):
    return {"type": "chat", "time": datetime.now().strftime("%H:%M"), "name": name,
            "badge": badge, "text": text, "action": action}


def post_chat(client, text, action=False):
    """Send a chat line to the client's room. Returns False if they're muted."""
    room = client.room
    until = mutes.get((room, client.key), 0)
    if until > time.time():
        client.say(f"🔇 You're muted here for {int((until - time.time()) // 60) + 1} more min.", "error")
        return False
    account = accounts[client.key]
    msg = chat_message(account["nick"], account["badge"], text, action)
    history[room].append(msg)
    send_room(room, msg)  # the sender gets it too, so they see their own line with the time
    log(f"[{room}] {account['nick']}: {text}")
    account["messages"] += 1
    if account["messages"] >= 100:
        unlock(client.key, "chatty")
    return True


def check_quiz(client, text):
    global quiz
    if quiz and client.room == "lobby" and text.strip() == quiz["answer"] and client.key not in matches:
        accounts[client.key]["tokens"] += quiz["reward"]
        notify_room("lobby", f"🎉 {shown(client.key)} got it first! {quiz['answer']} is right, "
                             f"+{quiz['reward']} 🪙", kind="event")
        quiz = None
        save_data()


def handle_line(client, text):
    text = text.strip()
    if not text:
        return
    match = matches.get(client.key)
    if match and not text.startswith("/") and match.game.looks_like_move(text):
        do_move(client, text)  # in a game, "5" or "c3 d4" or "w" is a move, not chat
        return
    if text.startswith("/"):
        name, _, args = text.partition(" ")
        entry = COMMANDS.get(name.lower())
        if entry is None:
            client.say(f"❓ Unknown command {name}. Type /help", "error")
            return
        entry[0](client, args.strip())
        return
    if not post_chat(client, text):
        return
    if text.lower().startswith("@hashbrown"):
        ask_hashbrown(client, text[len("@hashbrown"):].lstrip(" ,:"))
    check_quiz(client, text)


# ---------------------------------------------------------------- background threads
# Each loop sleeps, then runs one "tick" through run_safely(): if a tick crashes, the error
# is logged and the loop keeps going (a dead income thread would mean no more tokens, silently).

def run_safely(job, *args):
    try:
        return job(*args)
    except Exception:
        log("[SERVER] Error in a background job (it keeps running):\n" + traceback.format_exc())
        return None


def income_tick():
    """Online users get tokens, and so does every group with a member online."""
    with lock:
        for key, c in online.items():
            group = groups.get(c.room)
            bonus = 2 if group and "income" in group["upgrades"] else 0
            accounts[key]["tokens"] += TOKENS_PER_MINUTE + bonus
            check_rich(key)
        for group in groups.values():
            if any(member in online for member in group["members"]):
                group["bank"] += GROUP_INCOME
        now = time.time()
        for key in [k for k, times in login_fails.items() if not times or now - times[-1] > LOGIN_FAIL_WINDOW]:
            del login_fails[key]  # old wrong-password records: forget them
        if online:
            save_data()


def income_loop():
    while True:
        time.sleep(60)
        run_safely(income_tick)


def quiz_open():
    """Ask a quick math question in the lobby. Returns (the quiz, who was asked), or None."""
    global quiz
    with lock:
        free = [c for c in online.values()
                if c.room == "lobby" and c.key not in matches and c.key not in solo]
        if not free:
            return None
        a, b = random.randint(2, 20), random.randint(2, 20)
        op = random.choice("+-×")
        answer = a + b if op == "+" else a - b if op == "-" else a * b
        quiz = {"answer": str(answer), "reward": 50 if op == "×" else 30}
        for c in free:  # people in the middle of a game don't get interrupted
            c.say(f"⚡ QUICK MATH! First to answer wins {quiz['reward']} 🪙:   {a} {op} {b} = ?", "event")
        return quiz, free


def quiz_close(current, free):
    """Nobody answered in time: tell the people who were asked."""
    global quiz
    with lock:
        if quiz is not current:
            return
        for c in free:
            # online.get(c.key) is c: they're still on the SAME connection (not logged in again)
            if online.get(c.key) is c and c.key not in matches and c.key not in solo:
                c.say(f"⏰ Time's up! The answer was {current['answer']}.", "event")
        quiz = None


def quiz_loop():
    """Every few minutes, a quick math question pops up in the lobby."""
    while True:
        time.sleep(random.randint(180, 420))
        opened = run_safely(quiz_open)
        if opened:
            time.sleep(45)
            run_safely(quiz_close, *opened)


def console_command(line):
    """One command typed into the server window. Only whoever runs the server can use these."""
    cmd, _, rest = line.strip().partition(" ")
    with lock:
        if cmd == "say" and rest:
            announce(f"📢 [SERVER] {rest}")
        elif cmd == "give":
            parts = rest.split()
            key = find_account(parts[0]) if parts else None
            try:
                amount = int(parts[1]) if len(parts) == 2 else None
            except ValueError:
                amount = None
            if key and amount is not None:
                account = accounts[key]
                account["tokens"] = max(0, account["tokens"] + amount)  # negative takes tokens away
                save_data()
                tell(key, f"🎁 The server gave you {amount} 🪙!" if amount >= 0
                     else f"💸 The server took {-amount} 🪙.", "money")
                log(f"[CONSOLE] {nick(key)} now has {account['tokens']}")
            else:
                log("[CONSOLE] Usage: give <name> <amount>")
        elif cmd == "kick":
            key = find_account(rest)
            if key in online:
                online[key].kick("👢 You were kicked by the server.")
            else:
                log("[CONSOLE] Not online.")
        elif cmd == "list":
            for key, c in online.items():
                log(f"  {nick(key)} {c.address} in {c.room}, {accounts[key]['tokens']} tokens")
        elif cmd == "save":
            if save_data():
                log("[CONSOLE] Saved.")
        elif cmd:
            log("[CONSOLE] Commands: say, give, kick, list, save")


def console_loop():
    log("[CONSOLE] Commands: say <text> | give <name> <amount> | kick <name> | list | save")
    while True:
        try:
            line = input()
        except (EOFError, OSError):
            log("[CONSOLE] No keyboard here, so console commands are off.")
            return
        except ValueError:  # a key the console couldn't decode
            continue
        run_safely(console_command, line)


# ---------------------------------------------------------------- connections

def disconnect(client):
    try:
        with lock:
            key = client.key
            if key and online.get(key) is client:
                del online[key]
                match = matches.get(key)
                if match:
                    finish_match(match, match.opponent(key), f"{nick(key)} disconnected")
                invites.pop(key, None)
                solo.pop(key, None)
                for waiting in invites.values():
                    waiting[:] = [i for i in waiting if i["from"] != key]
                notify_room(client.room, f"👋 {shown(key)} left the chat")
                log(f"[SERVER] {nick(key)} disconnected")
                save_data()
    except Exception:
        log("[SERVER] Error while disconnecting:\n" + traceback.format_exc())
    finally:
        client.close()  # always, or the socket and its writer thread would stay open forever


def handle_client(sock, address):
    """Runs in its own thread, one per connection."""
    global connections
    with lock:
        too_many = connections >= MAX_CONNECTIONS
        if not too_many:
            connections += 1
    if too_many:
        log(f"[SERVER] ⚠️ Too many connections ({MAX_CONNECTIONS}), turned away {address}")
        sock.close()
        return
    try:
        talk_to(sock, address)
    finally:
        with lock:
            connections -= 1


def try_auth(client, msg):
    """handle_auth(), but a bug in it answers "something went wrong" instead of dropping the person."""
    try:
        return handle_auth(client, msg)
    except Exception:
        log("[SERVER] Error while logging someone in:\n" + traceback.format_exc())
        client.send({"type": "auth_result", "ok": False, "text": "💥 Something went wrong. Try again."})
        return False


def handle_message(client, msg):
    """A message from someone who is logged in. Called while holding the lock."""
    try:
        text = clean_text(msg.get("text", ""))[:MAX_TEXT]
        if not is_game_move(client, text) and not spam_ok(client):
            return  # game moves don't count as spam
        if msg.get("type") == "line":
            handle_line(client, text)
        elif msg.get("type") == "file":
            handle_file(client, msg)
    except Exception:  # a bug in one command must not kick the person out
        log("[SERVER] Error while handling a message:\n" + traceback.format_exc())
        client.say("💥 Something went wrong on the server with that. Try something else.", "error")


def talk_to(sock, address):
    """Read one connection's messages until it closes."""
    try:
        client = Client(sock, address)
    except RuntimeError:  # couldn't start its writer thread
        sock.close()
        return
    failed_logins = 0
    try:
        for raw in recv_lines(sock, client):
            msg = parse_message(raw)
            if msg is None:
                continue
            if client.key is None:  # not logged in yet (or replaced by a newer login): only auth
                if msg.get("type") != "auth":
                    continue
                if try_auth(client, msg):
                    sock.settimeout(None)  # logged in: no more time limit
                    continue
                failed_logins += 1
                if failed_logins >= 5:
                    client.say("🚫 Too many failed attempts. Bye.", "error")
                    break
                continue
            with lock:
                if client.key is not None:
                    handle_message(client, msg)
            if client.quitting:
                break
    except OSError:
        pass  # connection dropped or timed out (ConnectionResetError and timeouts are OSErrors)
    finally:
        disconnect(client)


def is_game_move(client, text):
    match = matches.get(client.key)
    return bool(match) and not text.startswith("/") and match.game.looks_like_move(text)


def reset_state():
    """Forget everything in memory (the tests use this to start each test from zero)."""
    global quiz, hashbrown, hashbrown_busy, hashbrown_all_today
    with lock:
        for table in (accounts, groups, online, mutes, invites, matches, last_rob, solo, login_fails,
                      admin_fail_times, hashbrown_last, hashbrown_today, history):
            table.clear()
        history["lobby"] = deque(maxlen=HISTORY_SIZE)
        quiz, hashbrown, hashbrown_busy, hashbrown_all_today = None, None, 0, ("", 0)


def start_server(host=HOST, port=PORT, run_loops=True, run_console=True):
    """Load the data, wake Hashbrown, start the helper threads and open the port.
    Returns the listening socket, or None if the server can't start.
    (The tests call this with port 0 and without the loops and the console.)"""
    global hashbrown
    if not load_data():
        return None
    hashbrown = load_hashbrown()
    if admin_password() == DEFAULT_ADMIN_PASSWORD:  # never print the password itself
        log("[SERVER] 🔒 /admin is off. To turn it on, set the HASHBROWN_ADMIN_PASSWORD environment "
            "variable (or put a password in ADMIN_PASSWORD in server.py).")
    loops = ([income_loop, quiz_loop] if run_loops else []) + ([console_loop] if run_console else [])
    for loop in loops:
        threading.Thread(target=loop, daemon=True).start()

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name != "nt":  # on Windows this option would let two servers share the port by accident
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind((host, port))
    except OSError as e:
        log(f"[SERVER] ❌ Can't use port {port} ({e}). Is the server already running in another window?")
        server_socket.close()
        return None
    server_socket.listen()
    log(f"[SERVER] 💬 Chat server running on port {server_socket.getsockname()[1]} (Ctrl+C to stop)")
    return server_socket


def serve_forever(server_socket):
    """Accept connections until Ctrl+C (or until the socket is closed). Everyone gets their own thread."""
    server_socket.settimeout(ACCEPT_WAKEUP)  # wake up now and then, so Ctrl+C works on Windows too
    try:
        while True:
            try:
                sock, address = server_socket.accept()
            except socket.timeout:
                continue
            except OSError as e:
                if server_socket.fileno() == -1:  # the socket was closed: time to stop
                    break
                # e.g. someone gave up halfway through connecting: just carry on
                log(f"[SERVER] ⚠️ Couldn't accept a connection ({e}). Still running.")
                time.sleep(0.1)
                continue
            try:
                threading.Thread(target=handle_client, args=(sock, address), daemon=True).start()
            except RuntimeError:  # the computer can't start more threads right now
                log("[SERVER] ⚠️ Too many threads, turned a connection away.")
                sock.close()
    except KeyboardInterrupt:
        log("\n[SERVER] Shutting down.")
    finally:
        with lock:
            run_safely(end_all_matches)  # nobody loses their bet because the server stopped
        save_data()
        server_socket.close()


def main():
    server_socket = start_server()
    if server_socket is not None:
        serve_forever(server_socket)


if __name__ == "__main__":
    main()
