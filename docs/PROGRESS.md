# 🧭 Build progress

**Status (2026-10-30): all 29 features and the 19 round-3 items done and pushed. 813 server tests + 39 website tests.**

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
| 14 | Game commentator | done: after every match both players get one line (matches.finish_hooks, server pays, COMMENTATOR_PER_DAY) |
| 15 | Group personality upgrade | done: 🎭 bank upgrade + /personality (admins), added to Hashbrown's instructions in that group |
| 16 | `/judge` | done: public verdict on the last JUDGE_HISTORY messages, paid like @hashbrown |
| 17 | Wordle `/hint` | done: one per game, private; the word is masked in code (and not streamed); no AI: a letter |
| 18 | `/tr` | done: private Hebrew <-> English translation, paid like /ask |
| 19 | Question of the day | done: once a day after QOTD_HOUR (Israel) with 2+ online, posted in the lobby (server pays), /qotd |

## Group 6: second round

| # | Feature | Status |
|---|---|---|
| 20 | Chunked files up to 15 MB with a progress bar | done: file_start/file_chunk/file_ack/file_end/file_cancel, 1 MB chunks, one in flight (acks = flow control), receiver needs the \"chunks\" feature; ≤2 MB still the old packet; bridge keeps chunks out of the replay log |
| 21 | Connect 4 | done: games.Connect4 (columns 1-7, gravity, 4 in a row, draw when full), /challenge name connect4 (or c4), website column buttons |
| 22 | Battleship | done: 6x6 seas, ships 3-2-2-1 placed for you, fire like c3; each player's state hides the other's ships; website: their sea = buttons |
| 23 | Spectating | done: /watch name (boards + result, players are told), /watch alone stops; spectator view hides Battleship ships; website shows 👀 Watching |
| 24 | ELO + leaderboards | done: START_ELO 1000, K 32, after every match (old saves get 1000 on load), /leaderboard [elo|wins|tokens], ELO in /whois |
| 25 | Offline messages | done: /send to someone offline is kept in their account's inbox (OFFLINE_MAX 20), delivered at login as a normal 💌 line |
| 26 | Edit/delete | done: edit/delete packets for your own messages for EDIT_MINUTES (author login stored in history.db, old DBs get the columns), room gets edited/deleted; website ✏️ 🗑️ (delete asks twice) |
| 27 | Jackpot pool | done: JACKPOT_SHARE (10%) of casino losses into state.jackpot (saved as a new top-level key), three 💎 on /slots wins it, /jackpot |
| 28 | Hashbrown trivia | done: /trivia (asker pays), reply parsed by regex QUESTION:/ANSWER: (refund if it doesn't fit), first right answer in TRIVIA_SECONDS wins TRIVIA_REWARD |
| 29 | Group wars | done: /war group, /war accept group (admins, 10 min), WAR_MINUTES of match wins between the groups, the winner takes WAR_PRIZE from the loser's bank; /war shows the score |

## Round 3 (after the hand test)

### Part A: fixes from the hand test

| # | Item | Status |
|---|---|---|
| R1 | Chats switcher: each chat its own conversation | done: root cause: the website had ONE message list and a room switch added the new history under the old room's messages; now a switch starts a fresh list, history packets carry an optional `key`, previews per room (roomlogic.js, tested in Node) |
| R2 | Sidebar scrolls on its own | done: the app grid has one screen-tall row, the sidebar scrolls on its own (contained, sections never squeezed, no scrollbar jump), the phone drawer is exactly the screen with home-bar padding and freezes the chat behind it; checked at 375, 900 and 1280 wide |
| R3 | Faster "is typing…" | done: new packet `typing_stop` (old clients ignore it); the first "typing" goes out at once, refreshes every TYPING_EVERY (2 s), stop on send or an empty box, the line hides exactly SHOW_FOR (4 s) after the last packet; flood cap TYPING_LIMIT per TYPING_WINDOW, outside the spam limit |
| R4 | @ autocomplete | done: typing @ (at the start or after a space) lists @hashbrown + the people online in this room (mentions.js, tested in Node), same keys as / ; a11y review applied: arrows move the highlight without rebuilding (scrolled into view), a status line says "3 people to mention", a usage hint on the box, Escape only closes the list, Tab inserts a person only after arrowing, a non-colour selected marker |
| R5 | `/answer` for the question of the day | done: /answer text (one per person per day, posted in the lobby as "💡 Nick's answer: ...", no author so it can't be edited), votes = other people's reactions; the next question settles it first: most votes (earliest on a tie, at least 1) wins QOTD_PRIZE 50 and Hashbrown says so (no AI); question + answers saved under "qotd" in chat_data.json; website 💡 Answer button + answer card |
| R6 | Network lab banner + reliable lab test | done: new packet {"type": "lab", lag_ms, loss_percent} to everyone when lag/loss/lab off change in the server window, and at login while it's on; website banner "🧪 Network lab: 300 ms lag, 20% loss" (banners.js). The flaky test was the side-by-side one (all three late packets in < 0.8 s, tight on a busy computer): now 0.6 s resend and 0.6-1.5 s allowed vs 1.8 s for one-after-another; 10/10 runs pass |
| R7 | start.sh uses .venv/bin/python | done (by the owner, 7d1fa8f): checked, `.venv/bin/python` if it exists, else `python3` |

### Part B: admin password

| # | Item | Status |
|---|---|---|
| R8 | Admin password from the Keychain | done: `ADMIN_PASSWORD = "123"` removed from config.py (it was in the public repo: don't reuse 123); the password only comes from HASHBROWN_ADMIN_PASSWORD, which start.sh loads from the Keychain item "hashbrown-admin" (warning line if missing); any length works, under 8 gets one startup warning (no value, no length printed); none = /admin off. start.sh only syntax-checked (zsh -n), never run |

### Part C: bug-hunt items

| # | Item | Status |
|---|---|---|
| R9 | /give limits for new accounts | done: accounts keep "created" (old saves get 0 = old) and "given" [day, total]; /give refused in the first GIVE_MIN_AGE_HOURS (24) with "🐣 ... (Nh left)", and over GIVE_DAILY_MAX (500) a day with how much is left. Not limited (noted for later): group bank deposits and game bets also move tokens between accounts |
| R10 | Look-alike names | done: rooms.valid_name: English letters/digits/_ OR Hebrew letters/digits/_ (never both, no accents, other alphabets or non-ASCII digits); for registering, /nick and new groups; login doesn't check it, so old names still log in; the website's login check and hint match |
| R11 | File offers (Accept/Decline) | done: clients that say "offers" at login (the website and today's client.py) get "📎 Dana wants to send you photo.jpg (2.3 MB).  /accept Dana  or  /decline Dana" with an optional `offer` field (website Accept/Decline buttons -> "/accept file N"); small files wait in memory, big files wait before their first chunk (not counted as stalled); OFFER_SECONDS 120 (checked every 5 s), OFFERS_WAITING_MAX 3 per receiver, one waiting offer per sender, gone when either side leaves. /accept and /decline take the newest of a challenge or an offer ("/accept file" = the file). Old client.py copies (no "offers") get files directly as before. Test-only: web_server --new-sessions-per-minute (default still 30) |
| R12 | Minimum password length | done: PASSWORD_MIN 6 when registering ("❌ Password: 6 to 64 characters."); logging in still accepts 4+ (OLD_PASSWORD_MIN) so older accounts work; the website checks 6 on Create account and 4 on Log in |

### Part D: chat features

| # | Item | Status |
|---|---|---|
| R13 | Read receipts for private messages | done: /send to someone online: your copy gets "pm": {id, status "sent"}, theirs "pm_id"; new packet {"type": "receipt", id, status} "delivered" once their writer really sent it, "seen" after their app sends the new {"type": "seen", id} (only the receiver, once; the last RECEIPTS_KEEP 500 remembered); website ✓ / ✓✓ in the card head, "seen" when the card is 60% on screen and the tab is in front (receipts.js). Messages kept for offline people have no receipts. The terminal client never says "seen" |
| R14 | `/remind` | done: /remind 10m|2h|1h30m|90s text (up to REMIND_MAX_HOURS 24, REMIND_MAX 5 waiting each), /remind alone lists yours; "⏰ Reminder: ..." privately (event card), checked every 5 s; due while away -> at login "(it was due at HH:MM)"; saved under "reminders" in chat_data.json |
| R15 | `/pin` room topic | done: /pin text (TOPIC_MAX 120), /pin alone shows it, /pin clear; group admins in a group, a server admin in the lobby; saved as group "topic" / top-level "lobby_topic"; new packet {"type": "topic", room, text} on every room switch (empty clears) and to the room on change; "📌 Topic: ..." line when you enter a room that has one (also at login for the lobby); website banner at the top |
| R16 | `/search` | done: /search word (2-50 characters) in history.db of the lobby + your groups, any case, % and _ are plain letters (LIKE ... ESCAPE), newest first, SEARCH_MAX 20; the reply is a list (two-space rows: room, time, name: text cut at 80) so the website draws it as a list card |
| R17 | Daily quests | done: /quests; 3 a day from 5 (win a game +40, play 2 games +25, send 10 messages +20, finish a Wordle +30, send a private message +15), picked with the date as seed so everyone gets the same; each pays once; progress in the account ("quests"), yesterday's resets; games count only when really played (was_played) |

### Part E: Hashbrown extras

| # | Item | Status |
|---|---|---|
| R18 | Tip Hashbrown | done: /give hashbrown N (any case, @ ok): the usual /give limits, tokens go to state.hashbrown_tokens (saved as "hashbrown_tokens"), "🥔 Hashbrown" in /top, a canned thanks from Hashbrown in your room (random of 3, no AI) |
| R19 | `/hbstats` | done: /hbstats (server admins): answers today, the server-wide cap used, tokens from the API's own usage numbers (read on response.completed), cost = in x HASHBROWN_PRICE_IN + out x HASHBROWN_PRICE_OUT per million (example prices 0.25 / 2.00 $: set your deployment's). Counted in memory per day (a restart starts from zero); the fake test AI now sends usage too  |

## Round 4: the 👥 Groups screen (website)

| # | Step | Status |
|---|---|---|
| G1 | Server: `get_groups` / `get_group` / `groups_closed` -> `groups` / `group_info` (group_view.py), privacy rules, 1 s refresh of open screens | done: private groups you're not in show name/emoji/size only; `bank_details` for members; `admin` (requests, muted, banned) for that group's admins only |
| G2 | Bank history in history.db (`bank_log` table): donations, upgrades, war prizes, Hashbrown payments/refunds, hourly snapshots for the chart; top donors; all upgrades with owned / can_buy / locked (+ missing) | done |
| G3 | Website screen: list, search, create, details, Bank & Upgrades, admin tools, phone layout | done: sidebar 👥 Groups button; the screen replaces the chat column (whole screen + Back on phones): search, create (inline form), your groups then the others, Open chat / Join / Request to join / Leave; details: members with role + online dot, 🏦 bank (big balance, earnings now and why, chart from 3 points, donate, top donors, history), ⬆️ all upgrades (owned / can buy / missing) with Buy + confirm for admins, war, 🛡️ admin tools (requests, kick/mute/ban/promote/demote, unmute/unban, topic/emoji/persona, disband with typed-name confirm); server replies show at the bottom; open screens refresh by themselves |
| G4 | Reviews (impeccable-finish-reviewer, a11y-architect, security-reviewer, code-reviewer), Chrome check, docs | done: impeccable-finish-reviewer (13 fixes: loading/empty states, no stuck details, busy buttons, request tickets, ketchup confirms, light contrast, offline dot, heading levels, Leave in details, phone header), a11y-architect (focus kept through redraws and dialogs, Enter confirms the typed name, busy without losing focus, reliable reply line (errors stay, role=alert), search keeps its box + a count, checkbox kept, labels, chart text; left: 4-5 tab stops per member for admins), security-reviewer (chart from snapshots only, pruning, refresh only after commands, unchanged packets not resent, per-viewer errors isolated, no online count for outsiders of private groups); Chrome: Adi admin + Ben request/approve/donate/mute/kick/disband, phone light |

Decision: group commands work on the room you're in, so a button for a group you're not in sends `/join X` first (option A, approved). The packets only show things; every button sends an existing command.

## Round 5 (overnight)

### Group A: picked features

| # | Feature | Status |
|---|---|---|
| N1 | 🔁 Reconnect and catch up (seq + resume) | done: packets kept for a client get an optional "seq" (the last RESUME_KEEP 500 / RESUME_SECONDS 600 per account; live-only ones like file pieces, typing, pongs, stream pieces, auth_result and the Groups screen get none); auth_result has an optional "resume_token" (random, new at every login, one use); after a drop the room keeps being collected for 10 min; {"type":"auth","action":"resume",username,token,seq} returns exactly the missed packets without the welcome burst (if some are gone: "resumed": false and a normal login); /quit ends it; kick notices carry "kicked": true so apps don't reconnect after them. The website and client.py reconnect by themselves (1-60 s backoff) and drop packets they already have. Choice: resume rides on the auth packet (not a separate "resume" packet after login), so the server can skip the welcome burst and nothing repeats |
| N2 | 👤 Profiles you can edit (+ change password) | done: new optional account fields (old saves get defaults): avatar (one emoji), bio (BIO_MAX 140), status online/away/busy + status_text (60), color 0-7 or auto, fav_game, theme light/dark (sent at login to clients with the "profiles" feature, so the website takes it on every device), privacy {last_seen show/hide, dms everyone/groups/nobody (enforced in /send)}, last_seen (set on disconnect). /profile [name], /setprofile field value (name = /nick, badge = /badge), /password old new; website: 👤 My profile, click a name (online list or chat) for a card, ✏️ Edit profile dialog; packets get_profile -> profile, change_password (kept out of X-ray). Not done: the name colour and avatar aren't shown on chat bubbles yet (only on the card) |
| N3 | 🗺️ Live network map | done: website 🗺️ Network map dialog (sidebar foot): the server in the middle, players around it, dots flying per packet (toward the server = sent, away = got; colour by kind; at most 6 per direction per second; none with reduced motion), ping under each name, and a table with the same numbers. Packets: get_netmap / netmap_closed -> netmap once a second while open (counts by type since the last map, never content); probe / probe_back every NETMAP_PROBE_EVERY 3 s to clients with the "probe" feature (the website and today's client.py answer; old clients: ping "?"). client.py got a send lock (two threads may send now) |
| N4 | 🎨 Drawing game (Pictionary) | done: /draw starts a round in your room (2+ people; one per room); the drawer gets the word privately; DRAW_SECONDS 90; strokes = {"type":"stroke", points 0-1000 (<= 64), color 0-7, size 1-3} or {"clear":true}, only from the drawer, DRAW_STROKES_PER_SECOND 20, outside the spam limit, passed to the room's "draw" clients, live-only (no seq, not in the reload replay) but visible in Packet X-ray; draw_round started/ended (word only at the end, strokes so far for latecomers); the server checks guesses: a right guess is never posted, wins DRAW_GUESS_PRIZE 30 (drawer DRAW_DRAWER_PRIZE 15); /draw stop gives up; time up shows the word. Website: a board above the chat with colours, size, clear, give up, timer. Login features limit raised 8 -> 16 |

### Group B: economy (stocks and taxes together)

| # | Feature | Status |
|---|---|---|
| N5 | 📈 Stock market (FRY, SPUD, SALT, KTCH) | done: FRY/SPUD/SALT/KTCH random walk every STOCK_TICK_SECONDS 60 (step ~2%, pull 2% to the start, max 6%/tick, min 1); /stocks, /buy FRY 5 (/buy 🔥 still buys badges), /sell FRY 5, /portfolio; TRADE_FEE_PERCENT 1 (min 1) to the fund; ONE "market" packet per tick to everyone; website 📈 Market dialog (live chart per stock, your shares, Buy/Sell) from get_market -> market_info; saved under "economy" |
| N6 | 🧾 Taxes into a public fund that pays prizes | done: public fund (saved): trading fees + 10% tax on casino wins of 200+ go in; quest, question-of-the-day and drawing prizes come out of it first (only what it can't cover is new tokens) |
| N7 | 👥 Group stocks with dividends | done: every group is a stock "#name" (/buy #Potatoes 3); each market tick its price moves GROUP_STOCK_FOLLOW_PERCENT 20% toward GROUP_STOCK_BASE 10 + bank/25 + 3 x members + 1 x chat lines in the last hour; a group that grew since yesterday (members or bank) pays GROUP_DIVIDEND_PERCENT 2% of its price per share a day from its bank (at most 10% of the bank); disbanding pays shareholders the last price (from the fund first); shown in /stocks and the website market screen |
| N8 | 📰 Hashbrown market news | not started |
| N9 | 🏦 Savings with interest | not started |
| N10 | 💳 Loans | not started |
| N11 | 🛒 Player marketplace | not started |
| N12 | 🔨 Auctions | not started |
| N13 | 📊 Economy dashboard (website) | not started |

### Round 5, group A reviews

- code-reviewer (Groups screen + reconnect): a fresh login now resets the website's seq, a locked resume goes back to login, open Groups screens resync after a reconnect, kicks end the token on the server, client.py closes a retry that got no answer, seq stamping and queueing happen together, bank details are cached, kept packets of accounts that never came back are freed.
- code-reviewer (network map + drawing): strokes keep the 4:3 shape and join up between packets; /draw has a 2-minute cooldown per person and no prize for a guess in the first 8 s; the round ends when the drawer leaves; the end packet has no drawing; the board resets on a room switch; the map counts only known packet types, hides private groups from outsiders and doesn't pile up dots in a hidden tab.
- security-reviewer (reconnect + profiles): someone kicked from a private group while away gets none of its chat; wrong resume tokens have their own lock-out (5 in 5 min) that never blocks the password login, and made-up names aren't remembered; a password login gives a fresh token (no old one keeps working) and a password change ends it; /password counts wrong old passwords like wrong logins; "who can message me" covers files too; typed /password lines and the resume token are kept out of Packet X-ray; avatars can't hide invisible marks. Left: /challenge invites and /give notices aren't covered by the "who can message me" setting.
- Chrome (two logins): profile edit + card + theme, drawing round (stroke, right guess not posted), network map with pings, both pages reconnecting by themselves after the website restarted.
- One test failed once in four full runs and never again (not identified).

### Round 3 reviews

- a11y-architect (the @ list, the file offer buttons): all findings fixed (see R4; offer buttons keep focus, announce the answer, come back on failure, live only).
- code-reviewer (the whole round, APPROVE, no critical/high): fixed /disband leaving the group's 📌 banner, logout not resetting the switcher and banners, waiting private messages and file offers vanishing on a room switch (they now come along), "is typing…" staying after a room switch or leaving, /answer and /remind saved right away, "file" is now a reserved name. Left: with history.db unusable (in-memory history), saved /answer ids could point at other messages after a restart.
- security-reviewer (Parts B and C): no critical issues, no secret leaks. Fixed: a bare /accept now prefers a waiting game challenge (a file only with "file", its sender's name or the website button); a 60 MB cap on all waiting small files; a waiting big file no longer blocks other senders; logging in again ends the old window's offers and transfers; accept re-checks the app can take big files. Left for the owner: look-alikes inside one alphabet still pass (I/l/1, O/0, rn/m, Hebrew ס/ם); any user can lock /admin for 10 minutes with 3 wrong tries (the chosen trade-off); a filename is free text in the offer line; tokens can still move between accounts without the /give limits through game bets, /rob, and /donate + /disband.

## Decisions made on the way

(Choices made without asking, so the owner can review them.)

- Group 6: Connect 4 and Battleship came before the 15 MB files (the files touch the same code a review was reading at the time).
- Group 5 was built as one commit: its six features share chatserver/hashbrown_extras.py.
- Item 1: `chat_data.json` never held history, so there was nothing to migrate and its format is unchanged. A disbanded group's rows are deleted from `history.db` so a new group with the same name starts empty. Falls back to in-memory history if the DB can't open.
- Item 2: `/ask` is always paid by the asker (never the group bank) and works while muted. `temp_id` is `hb-N` from a counter in `state`; `replaces` is only on the copy sent to clients, the saved history line stays plain. The website removes the "thinking" card on `replaces`, or after 2 minutes. The private answer card is labelled "🥔 Only you" (`hashbrownPrivate` in `patterns.js`, a plain `startsWith`, not a regex). The prompt, `HASHBROWN_REASONING`, `HASHBROWN_MAX_OUTPUT`, `HASHBROWN_HISTORY` (15), `HASHBROWN_MAX_CHARS` (700) and `HASHBROWN_MAX_CODE_LINES` (50) are at the top of `config.py`. `clean_answer` and the Israel time (zoneinfo, with a UTC+2/+3 fallback for Python 3.8) live in `chatserver/hashbrown_text.py`. Any 400 while `reasoning` was sent means: retry once without it and never send it again until restart (one log line). The old 1500-character cut of raw answers is gone (it could cut a code block); `clean_answer` limits the length instead. A code block cut to 50 lines gets its note after the closing fence.
- Item 3: `openai>=1.66,<2` in `requirements.txt`, pinned below 2 because 2.x needs a newer Python than 3.8. It is imported only inside `hashbrown_ai.import_openai()`; without it the server starts, Hashbrown is off and one line says `pip install -r requirements.txt`. `client.py` never imports it. The client is made per question with `max_retries=0` (a failed question is refunded, no hidden waits); errors are logged as class name + HTTP status only, never `str(e)`. The settings dict now has `base_url` (ending `/openai/v1`) instead of `url`. The login packet has an optional `features` list (at most 8 strings of 20 characters, otherwise ignored; `Client.features`); the website sends `["stream"]` and `web/bridge.py` refuses a malformed list with 400. Stream packets: `{"type":"stream","stream_id":"hb-N","name","badge","time","append"}`, the first also has `"replaces": "hb-N"`; the stream_id is the thinking notice's temp_id. At the end everybody in the audience gets the usual final message plus `stream_id` and `done: true`; a broken stream sends `{"type":"stream","stream_id","done":true,"failed":true}` first, then the usual refund error. Pieces are batched (0.15 s or 40 characters). Live text is the raw AI text; the final is the `clean_answer` text. A stream that ends without `response.completed` counts as broken. A runaway answer is cut off after 4x `HASHBROWN_MAX_CHARS` + 100 characters per allowed code line. Website: the live bubble is updated in place by the final message; for `/ask` it is removed when the private card arrives.
