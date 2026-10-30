"""
🥔 Asking Hashbrown privately.
"""
from chatserver import config, hashbrown_ai, registry


@registry.command("/ask", "/ask question", f"ask Hashbrown, the AI ({config.HASHBROWN_COST} 🪙)", "🥔 Hashbrown")
def cmd_ask(client, args):
    # Nothing is posted to the room, so even a muted user may ask: only they see the answer.
    hashbrown_ai.ask_hashbrown(client, args, private=True)


@registry.command("/tldr", "/tldr", f"Hashbrown sums up the chat, only for you ({config.HASHBROWN_COST} 🪙)",
                  "🥔 Hashbrown")
def cmd_tldr(client, args):
    # "Too long, didn't read": like a private /ask, but it reads more of the room's history
    hashbrown_ai.ask_hashbrown(client, config.TLDR_QUESTION, private=True, lines=config.TLDR_HISTORY)
