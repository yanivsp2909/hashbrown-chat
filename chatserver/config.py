"""
⚙️ Every setting you can change: ports, prices, limits, the admin password, Hashbrown's prompt.
Edit them here, then restart the server (python server.py).
Other files read them as config.NAME (never `from chatserver.config import NAME`: tests and the
server change some of them while running, and a copied value wouldn't see the change).
"""
import os


# Keep these two lines exactly like this: the website tests look for them to run a copy on another port
HOST = "0.0.0.0"
PORT = 8820
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the folder with server.py
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
ROB_COOLDOWN = 300           # seconds between two /rob tries by the same person
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


# ----- 🛠️ Admin

def admin_password():
    """HASHBROWN_ADMIN_PASSWORD wins, otherwise ADMIN_PASSWORD. Never print this."""
    return os.environ.get("HASHBROWN_ADMIN_PASSWORD", "").strip() or ADMIN_PASSWORD
