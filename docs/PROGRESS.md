# 🧭 Build progress

The checklist for the big build run. Each feature: **not started**, **in progress**, **done** (with the commit) or **skipped** (with the reason).
If you're picking this up after a break: read the rules, then continue from the first item that isn't done or skipped.

## Rules for every feature

- **Failing test first** (tdd-workflow): write the test, see it fail for the right reason, then build.
- **Compatible protocol:** only new *optional* fields or new packet types. Old `client.py` copies must keep working:
  they ignore unknown packet types and unknown fields (checked: `client.py show_message`, the website's
  `handleMessage` and the server's `handle_message` all skip unknown types). Check this again for each feature.
- **Exact wording:** `web/static/js/patterns.js` matches server text word for word. If a message it reads changes,
  `web/tests/test_bridge.py` says which pattern to update. Run the web tests when server text or `web/` changes.
- **No encryption** anywhere (teacher's rule): no TLS, packets stay readable.
- `client.py` stays one file, standard library only. The server may use the `openai` package (from Group 1, item 3),
  and must still start without it (Hashbrown off).
- **Tests never call the real AI** (a fake local server in `tests/helpers.py`), never print or log the API key, never open
  `hashbrown_config.json` by hand, never run `test_hashbrown.py` or `start.sh`.
- **Readable for a student:** small functions, plain names, a comment where the *why* isn't obvious.
  Settings go in `chatserver/config.py` and are read as `config.NAME`; shared data in `chatserver/state.py` as `state.x`.
- **Per feature:** `python3 -m pytest -q` (+ `python3 -m unittest discover -s web/tests` if `web/` or server text changed),
  then commit (Conventional Commits, ending with the Co-Authored-By line).
- **Per group:** full suite, web tests, a code review, update `README.md` and `docs/GUIDE.md`, then `git push`.
- **Stop and ask the owner only if:** a secret turns up, something can't stay compatible with old clients,
  the real AI key would be needed, or user data would be deleted. Otherwise decide, write the choice here, keep going.
- A feature that turns out much bigger than expected: mark it **skipped** with the reason and move on.

## Before the groups

| Item | Status |
|---|---|
| Erase the Azure endpoint and 192.168.0.52 from all history (git filter-repo), client.py default 127.0.0.1 | done (`fd6a711`, history rewritten) |
| Secrets scan of the rewritten history (all commits, messages and stored objects) | done: clean |
| Public repo https://github.com/yanivsp2909/hashbrown-chat, pushed | done |

## Group 1: Phase 5 core

| # | Feature | Status |
|---|---|---|
| 1 | SQLite chat history (`history.db`, message ids, survives restarts, room history + history upgrade keep working) | not started |
| 2 | Private `/ask`, "thinking" notice replaced by the answer (`temp_id` / `replaces`), Hashbrown prompt upgrade | not started |
| 3 | Streaming with the `openai` package (`requirements.txt`); old clients get one full message | not started |
| 4 | `server.py` starts the website; `client.py` asks terminal or website (`--web`) | not started |

## Group 2: for the teacher

| # | Feature | Status |
|---|---|---|
| 5 | Packet X-ray (Packets tab + TCP tab), `client.py --packets` | not started |
| 6 | UDP auto-discovery (`client.py` with no IP finds the server, else asks) | not started |
| 7 | `/ping`, the network lab (console lag/loss), `/netstats` | not started |

## Group 3: chat switcher

| # | Feature | Status |
|---|---|---|
| 8 | Chat switcher (b): the room list (a) first, then all-rooms messages for clients that ask for it | not started |

## Group 4: first round

| # | Feature | Status |
|---|---|---|
| 9 | Typing indicator (exempt from the spam limit) | not started |
| 10 | Reactions | not started |
| 11 | Rematch + `/claim` | not started |
| 12 | `/tldr` | not started |
| 13 | `/poll` | not started |

## Group 5: Hashbrown extras

| # | Feature | Status |
|---|---|---|
| 14 | Game commentator | not started |
| 15 | Group personality upgrade | not started |
| 16 | `/judge` | not started |
| 17 | Wordle `/hint` | not started |
| 18 | `/tr` | not started |
| 19 | Question of the day | not started |

## Group 6: second round

| # | Feature | Status |
|---|---|---|
| 20 | Chunked files up to 15 MB with a progress bar | not started |
| 21 | Connect 4 | not started |
| 22 | Battleship | not started |
| 23 | Spectating | not started |
| 24 | ELO + leaderboards | not started |
| 25 | Offline messages | not started |
| 26 | Edit/delete | not started |
| 27 | Jackpot pool | not started |
| 28 | Hashbrown trivia | not started |
| 29 | Group wars | not started |

## Decisions made on the way

(Choices made without asking, so the owner can review them.)
