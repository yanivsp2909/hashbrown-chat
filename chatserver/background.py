"""
⏰ Background jobs (income, quiz) and the server console.
"""
import random
import time
import traceback

from chatserver import achievements, config, hashbrown_extras, rooms, state, storage, textutil, transfers, wars


# ---------------------------------------------------------------- background threads
# Each loop sleeps, then runs one "tick" through run_safely(): if a tick crashes, the error
# is logged and the loop keeps going (a dead income thread would mean no more tokens, silently).

def run_safely(job, *args):
    try:
        return job(*args)
    except Exception:
        textutil.log("[SERVER] Error in a background job (it keeps running):\n" + traceback.format_exc())
        return None


def income_tick():
    """Online users get tokens, and so does every group with a member online. (And stalled big files stop.)"""
    with state.lock:
        transfers.expire_stalled()
        wars.end_due()
        for key, c in state.online.items():
            group = state.groups.get(c.room)
            bonus = 2 if group and "income" in group["upgrades"] else 0
            state.accounts[key]["tokens"] += config.TOKENS_PER_MINUTE + bonus
            achievements.check_rich(key)
        for group in state.groups.values():
            if any(member in state.online for member in group["members"]):
                group["bank"] += config.GROUP_INCOME
        now = time.time()
        old = [k for k, times in state.login_fails.items() if not times or now - times[-1] > config.LOGIN_FAIL_WINDOW]
        for key in old:
            del state.login_fails[key]  # old wrong-password records: forget them
        if state.online:
            storage.save_data()


def income_loop():
    while True:
        time.sleep(60)
        run_safely(income_tick)


def quiz_open():
    """Ask a quick math question in the lobby. Returns (the quiz, who was asked), or None."""
    with state.lock:
        free = [c for c in state.online.values()
                if c.room == "lobby" and c.key not in state.matches and c.key not in state.solo]
        if not free:
            return None
        a, b = random.randint(2, 20), random.randint(2, 20)
        op = random.choice("+-×")
        answer = a + b if op == "+" else a - b if op == "-" else a * b
        state.quiz = {"answer": str(answer), "reward": 50 if op == "×" else 30}
        for c in free:  # people in the middle of a game don't get interrupted
            c.say(f"⚡ QUICK MATH! First to answer wins {state.quiz['reward']} 🪙:   {a} {op} {b} = ?", "event")
        return state.quiz, free


def quiz_close(current, free):
    """Nobody answered in time: tell the people who were asked."""
    with state.lock:
        if state.quiz is not current:
            return
        for c in free:
            # online.get(c.key) is c: they're still on the SAME connection (not logged in again)
            if state.online.get(c.key) is c and c.key not in state.matches and c.key not in state.solo:
                c.say(f"⏰ Time's up! The answer was {current['answer']}.", "event")
        state.quiz = None


def quiz_loop():
    """Every few minutes, a quick math question pops up in the lobby."""
    while True:
        time.sleep(random.randint(180, 420))
        opened = run_safely(quiz_open)
        if opened:
            time.sleep(45)
            run_safely(quiz_close, *opened)


def qotd_loop():
    """❓ Once a minute: is it time for Hashbrown's question of the day?"""
    while True:
        time.sleep(60)
        run_safely(hashbrown_extras.question_of_the_day_tick)


def network_lab(cmd, value):
    """🧪 lag 300 / loss 10 / lab / lab off: make the network worse on purpose and watch what happens."""
    if cmd == "lab":
        if value == "off":
            state.lab_lag_ms, state.lab_loss_percent = 0, 0
            rooms.tell_everyone_about_the_lab()
        textutil.log(f"[LAB] 🧪 lag {state.lab_lag_ms} ms, loss {state.lab_loss_percent}% "
                     f"(a lost packet arrives {config.LAB_RESEND_MS} ms late, like a TCP resend)")
        return
    limit = 5000 if cmd == "lag" else 100
    if not value.isdecimal() or int(value) > limit:
        textutil.log("[LAB] Use: lag <milliseconds> (0-5000)  or  loss <percent> (0-100)")
        return
    if cmd == "lag":
        state.lab_lag_ms = int(value)
    else:
        state.lab_loss_percent = int(value)
    rooms.tell_everyone_about_the_lab()
    network_lab("lab", "")


def console_command(line):
    """One command typed into the server window. Only whoever runs the server can use these."""
    cmd, _, rest = line.strip().partition(" ")
    with state.lock:
        if cmd == "say" and rest:
            rooms.announce(f"📢 [SERVER] {rest}")
        elif cmd == "give":
            parts = rest.split()
            key = rooms.find_account(parts[0]) if parts else None
            try:
                amount = int(parts[1]) if len(parts) == 2 else None
            except ValueError:
                amount = None
            if key and amount is not None:
                account = state.accounts[key]
                account["tokens"] = max(0, account["tokens"] + amount)  # negative takes tokens away
                storage.save_data()
                rooms.tell(key, f"🎁 The server gave you {amount} 🪙!" if amount >= 0
                           else f"💸 The server took {-amount} 🪙.", "money")
                textutil.log(f"[CONSOLE] {rooms.nick(key)} now has {account['tokens']}")
            else:
                textutil.log("[CONSOLE] Usage: give <name> <amount>")
        elif cmd == "kick":
            key = rooms.find_account(rest)
            if key in state.online:
                state.online[key].kick("👢 You were kicked by the server.")
            else:
                textutil.log("[CONSOLE] Not online.")
        elif cmd == "list":
            for key, c in state.online.items():
                textutil.log(f"  {rooms.nick(key)} {c.address} in {c.room}, {state.accounts[key]['tokens']} tokens")
        elif cmd == "save":
            if storage.save_data():
                textutil.log("[CONSOLE] Saved.")
        elif cmd in ("lag", "loss", "lab"):
            network_lab(cmd, rest.strip())
        elif cmd:
            textutil.log("[CONSOLE] Commands: say, give, kick, list, save, lag, loss, lab")


def console_loop():
    textutil.log("[CONSOLE] Commands: say <text> | give <name> <amount> | kick <name> | list | save\n"
                 "[CONSOLE] Network lab: lag <milliseconds> | loss <percent> | lab (show) | lab off")
    while True:
        try:
            line = input()
        except (EOFError, OSError):
            textutil.log("[CONSOLE] No keyboard here, so console commands are off.")
            return
        except ValueError:  # a key the console couldn't decode
            continue
        run_safely(console_command, line)
