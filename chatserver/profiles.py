"""
👤 Profiles: what people choose to show about themselves. New optional fields in each account (old saves get
the defaults when they load): an emoji avatar, a bio, a status (online / away / busy + a custom line), a name
colour, a favourite game, a theme (remembered on every device) and privacy switches (hide "last seen", who
may send you private messages). The display name is /nick; the badge is /badge; the username never changes.
"""
import secrets
import time
import unicodedata
from datetime import datetime

from chatserver import config, rooms, state, storage

GAMES = {"ttt": "Tic-Tac-Toe", "damka": "Damka", "math": "Math Duel", "connect4": "Connect 4",
         "battleship": "Battleship", "wordle": "Wordle"}
STATUSES = ("online", "away", "busy")
DMS = ("everyone", "groups", "nobody")
COLORS = 8   # the website's eight name colours, 0-7


def defaults():
    """The profile fields a new (or old) account starts with."""
    return {"avatar": "", "bio": "", "status": "online", "status_text": "", "color": None, "fav_game": "",
            "theme": "", "privacy": {"last_seen": True, "dms": "everyone"}, "last_seen": 0}


def one_emoji(text):
    """True for a single emoji (one picture: letters and digits don't count; a flag or 👍🏽 is fine)."""
    text = text.strip()
    if not text or len(text) > 8 or any(ch.isalnum() for ch in text):
        return False
    if any(unicodedata.category(ch) in ("Mn", "Me", "Cf") and ch not in "\u200d\ufe0f" for ch in text):
        return False   # invisible marks and combining "zalgo" don't belong in an avatar
    pictures = [ch for ch in text if ord(ch) >= 0x2100 and ch not in "‍️" and not 0x1F3FB <= ord(ch) <= 0x1F3FF]
    return len(pictures) == 1 or (len(pictures) == 2 and all(0x1F1E6 <= ord(ch) <= 0x1F1FF for ch in pictures))


def set_field(key, field, value):
    """/setprofile field value. Returns (ok, message). ("name" and "badge" are /nick and /badge.)"""
    account = state.accounts[key]
    value = value.strip()
    privacy = dict(account["privacy"])
    if field == "avatar":
        if value and not one_emoji(value):
            return False, "👤 The avatar is one emoji, like 🍟 (or nothing: /setprofile avatar)"
        account["avatar"] = value
    elif field == "bio":
        if len(value) > config.BIO_MAX:
            return False, f"👤 The bio is at most {config.BIO_MAX} characters."
        account["bio"] = value
    elif field == "status":
        if value not in STATUSES:
            return False, f"👤 Status: {', '.join(STATUSES)}"
        account["status"] = value
    elif field == "statustext":
        if len(value) > config.STATUS_TEXT_MAX:
            return False, f"👤 The status line is at most {config.STATUS_TEXT_MAX} characters."
        account["status_text"] = value
    elif field == "color":
        if value not in ("", "auto") and not (value.isdecimal() and int(value) < COLORS):
            return False, f"👤 Colour: a number from 0 to {COLORS - 1}, or auto"
        account["color"] = int(value) if value.isdecimal() else None
    elif field == "game":
        if value and value not in GAMES:
            return False, f"👤 Favourite game: {', '.join(GAMES)}"
        account["fav_game"] = value
    elif field == "theme":
        if value not in ("light", "dark", ""):
            return False, "👤 Theme: light or dark"
        account["theme"] = value
    elif field == "lastseen":
        if value not in ("show", "hide"):
            return False, "👤 Last seen: show or hide"
        account["privacy"] = {**privacy, "last_seen": value == "show"}
    elif field == "dms":
        if value not in DMS:
            return False, f"👤 Who can send you private messages: {', '.join(DMS)}"
        account["privacy"] = {**privacy, "dms": value}
    else:
        return False, ("👤 Fields: avatar, name, bio, status, statustext, color, game, badge, theme, lastseen, dms. "
                       "Like: /setprofile bio I love fries")
    storage.save_data()
    return True, f"👤 Saved your {field}."


def looks(account):
    """🎨 The avatar and name colour that go on someone's chat bubbles: only the ones they set (new optional
    fields in "chat" packets; old clients ignore them)."""
    shown = {}
    if account.get("avatar"):
        shown["avatar"] = account["avatar"]
    if isinstance(account.get("color"), int) and not isinstance(account.get("color"), bool):
        shown["color"] = account["color"]
    return shown


def last_seen_text(key):
    seen = state.accounts[key].get("last_seen") or 0
    if not seen:
        return ""
    minutes = int((time.time() - seen) // 60)
    if minutes < 60:
        return f"{minutes} min ago" if minutes else "just now"
    if minutes < 24 * 60:
        return f"{minutes // 60} h ago"
    return datetime.fromtimestamp(seen).strftime("%d/%m")


def public(key, viewer):
    """What anyone may see (never the password, the theme or the privacy switches)."""
    account = state.accounts[key]
    shown = {"name": account["nick"], "login": account["login"], "avatar": account["avatar"], "badge": account["badge"],
             "bio": account["bio"], "status": account["status"], "status_text": account["status_text"],
             "color": account["color"], "fav_game": GAMES.get(account["fav_game"], ""), "online": key in state.online,
             "joined": account.get("joined", ""), "wins": account.get("wins", 0), "elo": account.get("elo", 0),
             "achievements": len(account.get("achievements", [])), "you": key == viewer}
    if key not in state.online and account["privacy"]["last_seen"]:
        shown["last_seen"] = last_seen_text(key)
    return shown


def mine(key):
    """Your own profile with the settings only you see."""
    account = state.accounts[key]
    return {**public(key, key), "theme": account["theme"], "privacy": dict(account["privacy"])}


def card_text(key, viewer):
    p = public(key, viewer)
    head = f"👤 {p['avatar'] + ' ' if p['avatar'] else ''}{rooms.shown(key)}  (@{p['login']})"
    status = p["status"] + (f": {p['status_text']}" if p["status_text"] else "")
    lines = [head, f"  Status  {'🟢 ' if p['online'] else ''}{status}"]
    if p["bio"]:
        lines.append(f"  Bio  {p['bio']}")
    if p["fav_game"]:
        lines.append(f"  Favourite game  {p['fav_game']}")
    lines.append(f"  Record  {p['wins']} wins · 📈 ELO {p['elo']} · 🏅 {p['achievements']}")
    if p.get("last_seen"):
        lines.append(f"  Last seen  {p['last_seen']}")
    return "\n".join(lines)


def dm_refusal(sender, target):
    """Why `sender` may not send `target` a private message, or None."""
    rule = state.accounts[target]["privacy"]["dms"]
    if rule == "nobody":
        return f"🔕 {rooms.nick(target)} doesn't take private messages or files."
    if rule == "groups" and not any(sender in g["members"] and target in g["members"] for g in state.groups.values()):
        return f"🔕 {rooms.nick(target)} only takes private messages from people in their groups."
    return None


def change_password(client, old, new, check_password):
    """/password old new (or the website's change_password packet). check_password(password, salt) -> (salt, hash)."""
    from chatserver import auth, resume   # (they use profiles: importing them at the top would loop)
    account = state.accounts[client.key]
    if auth.login_locked(client.key):
        client.say("🔒 Too many wrong passwords. Try again in 5 minutes.", "error")
        return
    try:
        old.encode("utf-8"), new.encode("utf-8")
    except UnicodeEncodeError:
        client.say("🔑 That password has a character that can't be used.", "error")
        return
    _, digest = check_password(old, account["salt"])
    if not secrets.compare_digest(digest, account["hash"]):
        state.login_fails.setdefault(client.key, []).append(time.time())   # counts like a wrong login
        client.say("🔑 The old password is wrong.", "error")
        return
    if not config.PASSWORD_MIN <= len(new) <= 64:
        client.say(f"🔑 The new password: {config.PASSWORD_MIN} to 64 characters.", "error")
        return
    salt, digest = check_password(new, None)
    account["salt"], account["hash"] = salt, digest
    resume.forget(client.key)   # no old reconnect token works after a password change
    storage.save_data()
    client.say("🔑 Password changed. Use the new one next time you log in.")
