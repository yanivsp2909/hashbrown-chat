"""
💰 Funding rounds (Phase 2): the investors, term sheets, bridge rounds and angel investing.
(Phase 1 only needs the names; the rest comes with Phase 2.)
"""


def status_lines(co):
    return []


def investor_title(investor_id):
    return f"💼 {investor_id}"


def bridge(client, co, args):
    client.say("🌉 Bridge rounds come with the funding update.", "error")


def list_angels(client, co, args):
    client.say("😇 Angel investing comes with the funding update.", "error")


def answer_angel(client, co, args):
    list_angels(client, co, args)
