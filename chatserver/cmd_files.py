"""
📁 File commands.
"""
from chatserver import registry


# ----- 📁 Files

@registry.command("/sendfile", "/sendfile name path", "send a file (up to 2 MB) 📁", "📁 Files")
def cmd_sendfile(client, args):
    # New clients send files as {"type": "file"} messages (see chat.handle_file). Only an old
    # client.py would send /sendfile as a chat line, so this just asks them to update.
    client.say("📁 Your client.py is too old for files. Get the new one.", "error")
