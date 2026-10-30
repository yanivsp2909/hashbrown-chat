"""
📁 File commands.
"""
from chatserver import registry


# ----- 📁 Files

@registry.command("/sendfile", "/sendfile name path", "send a file (up to 2 MB) 📁", "📁 Files")
def cmd_sendfile(client, args):
    client.say("📁 Your client.py is too old for files. Get the new one.", "error")
