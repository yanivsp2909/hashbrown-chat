"""
🧹 Small text helpers: printing to the console, cleaning text from the network, today's date.
"""
import re
from datetime import datetime


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


def today():
    return datetime.now().strftime("%Y-%m-%d")
