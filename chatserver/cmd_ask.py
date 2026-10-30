"""
🥔 Asking Hashbrown privately.
"""
from chatserver import chat, config, hashbrown_ai, registry


@registry.command("/ask", "/ask question", f"ask Hashbrown, the AI ({config.HASHBROWN_COST} 🪙)", "🥔 Hashbrown")
def cmd_ask(client, args):
    if chat.post_chat(client, "@hashbrown " + args):
        hashbrown_ai.ask_hashbrown(client, args)
