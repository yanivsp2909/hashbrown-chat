"""
🌐 Network commands: see the network at work.
"""
import time

from chatserver import registry


# ----- 🌐 Network

@registry.command("/ping", "/ping", "how long a packet takes there and back 🏓", "🌐 Network")
def cmd_ping(client, args):
    # New clients don't send "/ping" as a chat line: they send a {"type": "ping"} packet and time the
    # {"type": "pong"} that comes back. An old client gets this text answer instead.
    client.say("🏓 Pong! (Your client can't time it. The website and the new client.py show the milliseconds.)")


def size(count):
    return f"{count} bytes" if count < 10_000 else f"{count // 1024} KB ({count} bytes)"


@registry.command("/netstats", "/netstats", "packets and bytes on your connection 📊", "🌐 Network")
def cmd_netstats(client, args):
    minutes = int(time.time() - client.connected_at) // 60
    average = client.bytes_in // client.packets_in if client.packets_in else 0
    client.say(f"📊 Your connection, as the server sees it (connected {minutes} min):\n"
               f"  ⬇ The server got from you: {client.packets_in} packets, {size(client.bytes_in)} "
               f"(about {average} bytes each)\n"
               f"  ⬆ The server sent you: {client.packets_out} packets, {size(client.bytes_out)}\n"
               f"  Every packet is one line of JSON. TCP may split or join them on the way.")
