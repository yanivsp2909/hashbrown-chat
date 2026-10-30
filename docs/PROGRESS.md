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
| 1 | SQLite chat history (`history.db`, message ids, survives restarts, room history + history upgrade keep working) | done |
| 2 | Private `/ask`, "thinking" notice replaced by the answer (`temp_id` / `replaces`), Hashbrown prompt upgrade | done (`3003112` private /ask, `1cee762` temp_id/replaces, `cd6ee20` prompt upgrade) |
| 3 | Streaming with the `openai` package (`requirements.txt`); old clients get one full message | done (`4b29931`) |
| 4 | `server.py` starts the website; `client.py` asks terminal or website (`--web`) | done: chatserver/website.py (no secrets passed, busy port/missing web/ handled, stops on Ctrl+C or SIGTERM); client asks only at a keyboard |

## Group 2: for the teacher

| # | Feature | Status |
|---|---|---|
| 5 | Packet X-ray (Packets tab + TCP tab), `client.py --packets` | done: bridge records raw recv()/sendall() only while the tab's X-ray is open (never login packets); `<dialog>` with Packets/TCP tabs; client --packets |
| 6 | UDP auto-discovery (`client.py` with no IP finds the server, else asks) | done: chatserver/discovery.py on UDP 8821 (tiny fixed reply, rate-limited); client broadcasts, then tries 127.0.0.1, then asks |
| 7 | `/ping`, the network lab (console lag/loss), `/netstats` | done: ping/pong packets (own limit, skip spam limit; old clients get a text /ping); lab \"loss\" = late resend, not dropped (that's what TCP does); new /help section 🌐 Network |

## Group 3: chat switcher

| # | Feature | Status |
|---|---|---|
| 8 | Chat switcher (b): the room list (a) first, then all-rooms messages for clients that ask for it | done: login feature \"rooms\" → `rooms` packet + other rooms' chat tagged \"room\"; website 💬 Chats list with unread + preview; clicking = /join (history from SQLite) |

## Group 4: first round

| # | Feature | Status |
|---|---|---|
| 9 | Typing indicator (exempt from the spam limit) | done: `typing` packet, own limit (TYPING_EVERY), only to clients with the \"typing\" feature in your room |
| 10 | Reactions | done: `react` toggles one of config.REACTIONS on a message id (reactions table in history.db), room gets `reactions` counts, history carries them; website chips + picker |
| 11 | Rematch + `/claim` | done: /rematch (same opponent, game, bet), /claim after CLAIM_AFTER s on the other's turn (not Math Duel: no turns) |
| 12 | `/tldr` | done: private, paid like /ask, reads TLDR_HISTORY (50) lines |
| 13 | `/poll` | done: one poll per room, /vote (can change), /poll shows counts, /endpoll (creator or group admin); website vote buttons from the optional `poll` field |

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
- Item 1: `chat_data.json` never held history, so there was nothing to migrate and its format is unchanged. A disbanded group's rows are deleted from `history.db` so a new group with the same name starts empty. Falls back to in-memory history if the DB can't open.
- Item 2: `/ask` is always paid by the asker (never the group bank) and works while muted. `temp_id` is `hb-N` from a counter in `state`; `replaces` is only on the copy sent to clients, the saved history line stays plain. The website removes the "thinking" card on `replaces`, or after 2 minutes. The private answer card is labelled "🥔 Only you" (`hashbrownPrivate` in `patterns.js`, a plain `startsWith`, not a regex). The prompt, `HASHBROWN_REASONING`, `HASHBROWN_MAX_OUTPUT`, `HASHBROWN_HISTORY` (15), `HASHBROWN_MAX_CHARS` (700) and `HASHBROWN_MAX_CODE_LINES` (50) are at the top of `config.py`. `clean_answer` and the Israel time (zoneinfo, with a UTC+2/+3 fallback for Python 3.8) live in `chatserver/hashbrown_text.py`. Any 400 while `reasoning` was sent means: retry once without it and never send it again until restart (one log line). The old 1500-character cut of raw answers is gone (it could cut a code block); `clean_answer` limits the length instead. A code block cut to 50 lines gets its note after the closing fence.
- Item 3: `openai>=1.66,<2` in `requirements.txt`, pinned below 2 because 2.x needs a newer Python than 3.8. It is imported only inside `hashbrown_ai.import_openai()`; without it the server starts, Hashbrown is off and one line says `pip install -r requirements.txt`. `client.py` never imports it. The client is made per question with `max_retries=0` (a failed question is refunded, no hidden waits); errors are logged as class name + HTTP status only, never `str(e)`. The settings dict now has `base_url` (ending `/openai/v1`) instead of `url`. The login packet has an optional `features` list (at most 8 strings of 20 characters, otherwise ignored; `Client.features`); the website sends `["stream"]` and `web/bridge.py` refuses a malformed list with 400. Stream packets: `{"type":"stream","stream_id":"hb-N","name","badge","time","append"}`, the first also has `"replaces": "hb-N"`; the stream_id is the thinking notice's temp_id. At the end everybody in the audience gets the usual final message plus `stream_id` and `done: true`; a broken stream sends `{"type":"stream","stream_id","done":true,"failed":true}` first, then the usual refund error. Pieces are batched (0.15 s or 40 characters). Live text is the raw AI text; the final is the `clean_answer` text. A stream that ends without `response.completed` counts as broken. A runaway answer is cut off after 4x `HASHBROWN_MAX_CHARS` + 100 characters per allowed code line. Website: the live bubble is updated in place by the final message; for `/ask` it is removed when the private card arrives.
