"""
🏅 Unlocking achievements.
"""
from chatserver import config, rooms, state


# ---------------------------------------------------------------- achievements

def unlock(key, achievement):
    """Give an achievement (once) and its reward."""
    account = state.accounts[key]
    if achievement in account["achievements"]:
        return
    icon, title, how, reward = config.ACHIEVEMENTS[achievement]
    account["achievements"].append(achievement)
    account["tokens"] += reward
    rooms.tell(key, f"🏅 ACHIEVEMENT UNLOCKED: {icon} {title} ({how})  +{reward} 🪙", "money")
    rooms.announce(f"🏅 {rooms.shown(key)} unlocked {icon} {title}!", exclude={key})
    check_rich(key)

def check_rich(key):
    if state.accounts[key]["tokens"] >= 1000:
        unlock(key, "rich")
