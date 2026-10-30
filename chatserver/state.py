"""
🗃️ Everything the server keeps in memory while it runs (shared by all the other modules).

Always use it as state.accounts, state.quiz...: never `from chatserver.state import quiz`,
or you'd keep an old copy when the server replaces the value.
"""
import threading

from chatserver import config


# ---------------------------------------------------------------- shared state
# Every thread reads and writes these, so ALL access happens while holding `lock`.
lock = threading.RLock()
accounts = {}   # login name (lowercase) -> account dict      (saved to disk)
groups = {}     # group name (lowercase) -> group dict        (saved to disk)
online = {}     # login name -> Client, only people connected right now
mutes = {}      # (group, login) -> time the mute ends
invites = {}    # login -> game challenges waiting for that person
matches = {}    # login -> the Match they're playing
last_rob = {}   # login -> time of their last /rob
qotd = None      # ❓ (day, question) of the question of the day
commentator_today = ("", 0)   # 🎙️ (day, how many comments)
transfers = {}  # 📦 big file transfers on their way: their key -> details
polls = {}      # room -> its poll: {by, question, options, votes: {login: option index}}
last_match = {}  # login -> (opponent, game class, bet) of their last finished match, for /rematch
solo = {}       # login -> their Wordle game
login_fails = {}         # login -> times of recent wrong passwords
admin_fail_times = []    # times of recent wrong /admin passwords, from anyone
connections = 0          # open connections right now
hashing = threading.BoundedSemaphore(config.HASHING_AT_ONCE)
quiz = None     # the open quick-math question, if any
hashbrown = None        # Foundry settings, or None if Hashbrown isn't set up
hashbrown_busy = 0      # questions being answered right now
hashbrown_last = {}     # login -> time of their last question
hashbrown_today = {}    # login -> (date, questions asked that day)
hashbrown_all_today = ("", 0)  # (date, questions asked by everyone that day)
hashbrown_no_reasoning = False  # True once the AI said no to the "reasoning" setting: stop sending it
hashbrown_questions = 0        # counts questions: gives each "thinking" notice its temp_id


# 🧪 The network lab (console: lag / loss / lab off): makes every packet the server sends slow or "lost"
lab_lag_ms = 0          # extra delay for every packet
lab_loss_percent = 0    # this % of packets arrive LAB_RESEND_MS late, like a TCP resend after a loss


def reset_state():
    """Forget everything in memory (the tests use this to start each test from zero)."""
    global quiz, hashbrown, hashbrown_busy, hashbrown_all_today, hashbrown_questions, hashbrown_no_reasoning
    global lab_lag_ms, lab_loss_percent, qotd, commentator_today
    with lock:
        for table in (accounts, groups, online, mutes, invites, matches, last_rob, last_match, polls, transfers, solo, login_fails,
                      admin_fail_times, hashbrown_last, hashbrown_today):
            table.clear()
        quiz, hashbrown, hashbrown_busy, hashbrown_all_today = None, None, 0, ("", 0)
        hashbrown_questions, hashbrown_no_reasoning = 0, False
        lab_lag_ms, lab_loss_percent = 0, 0
        qotd, commentator_today = None, ("", 0)
