"""
🥔 Asking Hashbrown privately.
"""
from chatserver import config, hashbrown_ai, registry


@registry.command("/ask", "/ask question", f"ask Hashbrown, the AI ({config.HASHBROWN_COST} 🪙)", "🥔 Hashbrown")
def cmd_ask(client, args):
    # Nothing is posted to the room, so even a muted user may ask: only they see the answer.
    hashbrown_ai.ask_hashbrown(client, args, private=True)
