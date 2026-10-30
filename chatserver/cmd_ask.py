"""
🥔 Asking Hashbrown privately.
"""
from chatserver import config, hashbrown_ai, hashbrown_extras, registry, state, textutil


@registry.command("/ask", "/ask question", f"ask Hashbrown, the AI ({config.HASHBROWN_COST} 🪙)", "🥔 Hashbrown")
def cmd_ask(client, args):
    # Nothing is posted to the room, so even a muted user may ask: only they see the answer.
    hashbrown_ai.ask_hashbrown(client, args, private=True)


@registry.command("/tldr", "/tldr", f"Hashbrown sums up the chat, only for you ({config.HASHBROWN_COST} 🪙)",
                  "🥔 Hashbrown")
def cmd_tldr(client, args):
    # "Too long, didn't read": like a private /ask, but it reads more of the room's history
    hashbrown_ai.ask_hashbrown(client, config.TLDR_QUESTION, private=True, lines=config.TLDR_HISTORY)


@registry.command("/judge", "/judge", f"Hashbrown judges the argument, everyone sees it ({config.HASHBROWN_COST} 🪙)",
                  "🥔 Hashbrown")
def cmd_judge(client, args):
    hashbrown_ai.ask_hashbrown(client, config.JUDGE_QUESTION, lines=config.JUDGE_HISTORY)


@registry.command("/tr", "/tr text", f"translate Hebrew <-> English, only for you ({config.HASHBROWN_COST} 🪙)",
                  "🥔 Hashbrown")
def cmd_tr(client, args):
    if not args.strip():
        client.say("🌐 Use: /tr text", "error")
        return
    hashbrown_ai.ask_hashbrown(client, config.TR_QUESTION.format(text=args.strip()), private=True)


@registry.command("/qotd", "/qotd", "today's question of the day ❓", "🥔 Hashbrown")
def cmd_qotd(client, args):
    qotd = state.qotd
    if qotd and qotd[0] == textutil.today() and qotd[1]:
        client.say(f"❓ Question of the day: {qotd[1]}")
    else:
        client.say("❓ No question of the day yet. Hashbrown asks one in the lobby every day.")


assert hashbrown_extras  # imported so the game commentator hooks itself into finished matches
