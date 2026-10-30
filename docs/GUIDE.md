# 🥔 Hashbrown Chat

> 📘 This is the full user guide. For the project overview, see the [README](../README.md).
>
> IP addresses in this guide, such as `192.168.1.20`, are examples. Use your host's IP.

A multiplayer chat that runs in the terminal (PyCharm, CMD, Terminal), with an AI bot called Hashbrown. One person runs the server, everyone else runs the client and joins over the same Wi-Fi.

Pure Python, no installs for the chat itself (only Hashbrown, the AI, needs the `openai` package: see "Waking up Hashbrown"). Python 3.8 or newer.

## What's inside

- 🔐 **Accounts**: register and log in with a password. Passwords are stored as salted hashes, never as plain text.
- 🥔 **Hashbrown**: an AI (GPT-5.6 on Microsoft Foundry). Start a message with `@hashbrown` and it answers in the room. It can see the recent chat, so it knows what everyone is talking about.
- 👥 **Groups**: public groups anyone can join, private 🔒 groups where an admin has to approve you.
- 🛡️ **Group admins**: kick, ban, mute, promote, demote, disband.
- 🏦 **Group bank and upgrades**: every group earns its own tokens and spends them on upgrades.
- 🪙 **Tokens**: earned every minute, from `/daily` streaks, game wins, achievements and quick-math questions.
- 🎰 **Casino**: coinflip, dice and slots (fake tokens only).
- 🏅 **Achievements and a badge shop**.
- 🎮 **1v1 games**: Tic-Tac-Toe, Damka (checkers) and a Math Duel, with optional token bets.
- 🟩 **Solo Wordle**: guess the word and win up to 60 🪙 (5 rewarded games a day).
- 🛠️ **Admins**: `/admin password`, then `/admintokens`.
- 📁 **File sending**: up to 2 MB.
- 💌 Private messages, `/me` actions, nicknames, timestamps, chat history (saved in `history.db`, so it survives a restart), colors and emojis.

## Files

| File | Who needs it |
|---|---|
| `server.py` + `games.py` + `chatserver/` | the person hosting (same folder) |
| `test_hashbrown.py` | the host, to check the AI key works |
| `client.py` | everyone who joins from a terminal |
| `web/` | the host, to run the website (`web/web_server.py`) for friends who join from a browser |
| `chat_data.json` | created by the server: accounts, tokens, groups |
| `hashbrown_config.json` | created by the server: **your API key. Never send this to anyone.** |

## How to run

**Host:**
```
python server.py
```
Allow incoming connections if your computer asks. Find your IP address (Mac: `ipconfig getifaddr en0`, Windows: `ipconfig`) and give it to your friends.

**Everyone else:**
```
python client.py 192.168.1.20
```
Use the host's IP address (with no IP it connects to this computer, 127.0.0.1). It asks **1) terminal 2) website**: Enter plays in the terminal, **2** opens the host's website in your browser (add `--web` to skip the question). Then pick **2** to create an account, or **1** to log in. Type `/help` once you're in.

## Website 🌐

Friends can also use the chat from a browser instead of `client.py`, on a phone or a laptop. Nothing to install.

**Host:** `python server.py` starts the website too (on port 8080). If you turned that off (`START_WEBSITE = False` in `chatserver/config.py`), keep `server.py` running and in a second window run:
```
python web/web_server.py
```
It prints the link to share, for example:
```
[WEB] 🔗 Share this link: http://192.168.1.20:8080
```
Send that link to your friends. They must be on the **same Wi-Fi**. The address is your computer's current Wi-Fi address, so it changes when you switch networks. Just restart `web_server.py` and it prints the new one. If your computer asks whether to allow incoming connections, say yes.

In the browser, friends create an account or log in (the same accounts as `client.py`), then:
- 🎟️ Challenges, your game and your Wordle hang as "order tickets" at the top of the chat. Press **Accept** to play.
- 🎮 Boards are clickable: tap a square in Tic-Tac-Toe, tap a piece and then a square in Damka, type the answer in Math Duel, and guess in Wordle.
- ⌨️ Type `/` to see every command. **Up** brings back what you sent before.
- 📎 The paperclip, or dragging a file onto the chat, sends a file (2 MB max). Files you get show up as **Download** buttons.
- 🌙 Dark and light mode, and it works on phones.

Options: `--port 8080` (website port), `--chat-port 8820` (where `server.py` listens), `--max-sessions 50`. Each browser tab is one login. A reloaded tab stays logged in. A closed tab logs out after 90 seconds (or right away with **Log out**).

**Tests:** `python -m unittest discover -s web/tests -v` runs a copy of the server in a temporary folder, so your real `chat_data.json` is never touched. The test also fails with a clear message if you reword a server message that the website relies on. Those messages are listed at the top of `web/static/js/patterns.js`.

Same warning as the terminal client: the website is plain HTTP, so anyone on the Wi-Fi could read messages and passwords.

## Waking up Hashbrown 🥔

0. Install the one package Hashbrown needs: `pip install -r requirements.txt`. (Everything else needs no install. It is pinned below version 2 because newer `openai` versions need a newer Python than 3.8.)
1. Put `hashbrown_config.json` next to `server.py`. If it's missing, the server creates it on first run.
2. Open it and replace `PASTE-YOUR-KEY-HERE` with your key:
   ```json
   {
     "endpoint": "https://YOUR-RESOURCE.services.ai.azure.com/openai/v1",
     "deployment": "gpt-6.1-terra",
     "api_key": "your key"
   }
   ```
3. Run `python test_hashbrown.py`. It asks Hashbrown one question and tells you if the key works.
4. Start the server. It should print `🥔 Awake!`.

Hashbrown uses the same Responses API as `client.responses.create(...)` in the Foundry sample, but with an API key instead of `az login`.

**Streaming:** the server asks for the answer in pieces (`stream=True`). Clients that say `"features": ["stream"]` when they log in (the website does) see the answer appear live, in a few updates per second, and then the final cleaned text replaces it. Other clients, like `client.py`, get one full message at the end, exactly as before. If the AI breaks halfway, the live text disappears and the tokens are refunded.

If you'd rather not keep the key in the file, set the environment variable `HASHBROWN_API_KEY` instead. It overrides the file.

**Costs and limits:** each question costs 20 🪙. There's a 15 second cooldown per person and a limit of 30 questions per person per day. If the AI call fails, the tokens are refunded. Remember that every question also costs **real money** on your Azure account.

## The economy

| Way to earn | Amount |
|---|---|
| Being online | 5 🪙 per minute |
| Being inside a group with the 💰 income upgrade | +2 🪙 per minute |
| `/daily` | 150 🪙, +50 for each day in a row, up to 500. Claim again within 20-48 hours or the streak resets. |
| Winning a game | +25 🪙 for each of your first 10 wins per day, plus the pot if there was a bet |
| Wordle (`/wordle`) | 60 🪙 for 1 try down to 10 🪙 for 6 tries, 5 rewarded games a day |
| Achievements (`/achievements`) | 25 to 300 🪙 each |
| Quick math in the lobby | 30-50 🪙 for the first right answer |
| Daily quests (`/quests`) | three small tasks a day (like "send 10 messages"), 15-40 🪙 each |
| Best answer to the question of the day (`/answer`) | 50 🪙 for the most reactions, paid when the next question comes |
| Casino and `/rob` | risky 😈 |

**Group bank:** every group earns 10 🪙 per minute while at least one member is online. Anyone can `/donate`, and admins spend the bank with `/upgrade`:

| Upgrade | Price | Effect |
|---|---|---|
| 💰 income | 300 | members earn +2 🪙/min while inside the group |
| 📜 history | 200 | chat history goes from 15 to 50 messages |
| 🎨 emoji | 150 | a custom emoji next to the group name (`/groupemoji 🍟`) |
| 🥔 hashbrown | 250 | Hashbrown questions asked in the group are paid by the bank |

If an owner disbands a group, whatever is left in the bank goes to them.

**`/give` limits** (against making extra accounts to farm tokens): an account can't give in its first 24 hours, and nobody gives more than 500 🪙 a day in total. Tipping Hashbrown (`/give hashbrown 10`) counts too; Hashbrown keeps its tips and shows up in `/top`.

## Commands

| | |
|---|---|
| 💬 Chat | `/help` `/users` `/send name msg` `/me action` `/nick name` `/whois name` `/pin text` (the room's topic; `/pin` shows it, `/pin clear`) `/search word` `/remind 10m text` (`/remind` lists yours) `/quit` |
| 📊 Polls | `/poll question \| option \| option` (2-6 options) `/vote 2` `/poll` (see the votes) `/endpoll` |
| 🥔 Hashbrown | `@hashbrown question` (everyone sees the answer) or `/ask question` (only you see it, you pay), `/tldr` (a summary of the chat, only for you), `/judge` (Hashbrown settles the argument, everyone sees it), `/tr text` (Hebrew ↔ English, only you), `/qotd` (today's question of the day), `/answer text` (your answer to it), `/hint` in a Wordle (one per game) |
| 👥 Groups | `/groups` `/create name [private]` `/join name` `/lobby` `/leave` `/members` `/requests` `/approve name` `/reject name` |
| 🛡️ Admin | `/kick` `/ban` `/unban` `/mute name [min]` `/unmute` `/promote` `/demote` `/disband` |
| 🏦 Group bank | `/bank` `/donate amount` `/upgrade name` `/groupemoji 🍟` `/topgroups` |
| 🪙 Tokens | `/balance` `/top` `/give name amount` `/daily` `/rob name` `/shop` `/buy 🔥` `/badge 🔥` `/achievements` |
| 🎰 Casino | `/coinflip amount heads` `/dice amount` `/slots amount` |
| 🎮 Games | `/games` `/quests` `/challenge name ttt\|damka\|math [bet]` `/accept` `/decline` (a challenge, or a file: `/accept file`) `/board` `/resign` `/wordle` `/g word` `/giveup` `/rematch` (same person, game and bet) `/claim` (win if they stopped moving for 2 min) `/watch name` (spectate; `/watch` stops) `/leaderboard [elo\|wins\|tokens]` |
| ⚔️ Group wars | `/war group` (an admin declares) `/war accept group` (their admin, within 10 min) `/war` (the score) |
| 🛠️ Admin | `/admin password` `/admintokens [name]` `/hbstats` (Hashbrown's questions, tokens and cost today) |
| 📁 Files | `/sendfile name path/to/file` |

**During a game**, just type your move:
- Tic-Tac-Toe: `5`
- Damka: `c3 d4`
- Math Duel: the number, like `42`

The admin password is never in the code (the repo is public). Save it in the Mac Keychain as `hashbrown-admin` and `start.sh` loads it into `HASHBROWN_ADMIN_PASSWORD`; no password means `/admin` is off. **Don't use 123**: it used to be the built-in one, so everyone who read the code knows it.

**New accounts** need a username of 3-16 English *or* Hebrew letters, digits or `_` (not both alphabets, so nobody can hide a look-alike letter in a name) and a password of at least 6 characters. Older accounts keep their names and passwords.

## New games and more 🎲

- 🔴🟡 **Connect 4** (`/challenge name connect4`): type a column 1-7, four in a row wins.
- 🚢 **Battleship** (`/challenge name battleship`): your ships are placed for you; fire like `c3`. Nobody, not even spectators, sees your ships.
- 📈 **ELO**: everyone starts at 1000; beating a stronger player gains more. `/leaderboard` shows the best.
- 👀 **Spectating**: `/watch name` follows their game; `/watch` alone stops.
- 📬 **Offline messages**: `/send` to someone offline waits for them (up to 20) and arrives when they log in.
- ✏️ **Edit/delete** (website): ✏️ or 🗑️ under your own message, for 10 minutes.
- 💰 **Jackpot**: 10% of every casino loss goes into a pot; three 💎 on `/slots` wins it. `/jackpot` shows it.
- 🧠 **Trivia**: `/trivia` (costs like `/ask`): Hashbrown asks the room a question; the first right answer in 60 seconds wins 40 🪙.
- ⚔️ **Group wars**: for 30 minutes, every game a member wins against the other group is a point; the winner takes 300 🪙 from the loser's bank.
- 📦 **Big files** (website): up to 15 MB, sent in 1 MB pieces with a progress bar. Each piece waits for the server's "got it" before the next one goes (flow control). The terminal client still sends up to 2 MB.
- 📎 **Files are offered first**: the receiver sees "📎 Dana wants to send you photo.jpg (2.3 MB)" with Accept and Decline (or types `/accept file` / `/decline file`); nothing arrives before Accept, and an offer expires after 2 minutes. An old `client.py` that doesn't know about offers still gets files straight away.
- ✓✓ **Read receipts** (website): your private message shows ✓ when it reached them and ✓✓ when it was on their screen.
- ⏰ **Reminders**: `/remind 10m take the fries out` (or `2h`, `1h30m`; up to 24 hours, 5 at a time). They survive a server restart; if you're away when one is due, you get it when you log in.
- 📌 **Topics**: `/pin Movie night at 8` puts a topic at the top of the room (group admins in a group, a server admin in the lobby); people see it when they come in.
- 🔎 **Search**: `/search pizza` finds it in the chat of the rooms you're in, newest first (20 at most).
- 🎯 **Daily quests**: `/quests` shows today's three tasks (the same for everyone), each pays once.

## Hashbrown extras 🥔

- 🎙️ **Commentator:** after every match, Hashbrown sends both players one funny line about it.
- ❓ **Question of the day:** once a day (after 10:00 Israel time, when at least two people are online) Hashbrown asks the lobby a fun question. `/qotd` shows it again. Answer with `/answer ...` (or the 💡 Answer button): one answer each, people vote with reactions, and when the next question comes the answer with the most reactions wins 50 🪙.
- 💸 **Tips:** `/give hashbrown 10` and Hashbrown says thanks. 📊 `/hbstats` (server admins) shows today's questions, tokens and an estimated cost (set your prices in `HASHBROWN_PRICE_IN` / `HASHBROWN_PRICE_OUT` in `config.py`).
- 🎭 **Group personality:** buy the 🎭 upgrade for your group (`/upgrade personality`), then a group admin types `/personality a pirate who loves potatoes`. Hashbrown plays that role in your group (all its rules still apply). `/personality` with nothing turns it off.
- These cost the server, not you, and count toward the server's daily Hashbrown limit.

## On the website: reactions and typing 😂

Hover (or tab to) a message and press **☺︎+** to react with 👍 ❤️ 😂 😮 😢 or 🥔. Click a reaction under a message to add or take back yours. While someone in your room types, you see *Noa is typing…* above the message box (right away, and it goes when they send or clear the box). Type `@` for a list of the people in this chat and @hashbrown. A poll shows a button for each option.

## Profiles 👤

Click anyone's name (in the online list or in the chat) for their card, or **👤 My profile** for yours, then **✏️ Edit profile**: an emoji avatar, your display name (same as `/nick`), a bio, a status (🟢 online, 🌙 away, ⛔ busy, plus your own line), a name colour, your favourite game, the theme (it follows you to every device), privacy (show "last seen" or not; who can send you private messages and files: everyone, people in your groups, or nobody) and a new password (the old one first). In the terminal: `/profile name`, `/setprofile bio I love fries`, `/password old new`. Your username never changes.

## Drawing game 🎨

Type `/draw` (at least 2 people in the room). You get a secret word and a canvas above the chat; draw it with the mouse or a finger. Everyone else guesses in the chat. The server checks the guesses, so nobody's app ever sees the word before the end. The first right guess wins 30 🪙 and the drawer 15 🪙 (not for a guess in the first 8 seconds). A round lasts 90 seconds; `/draw stop` gives up, and you can start one every 2 minutes. Each brush stroke is one small `stroke` packet: open Packet X-ray while someone draws.

## If the connection drops 🔁

The website and `client.py` reconnect by themselves (they try for about two minutes) and you get exactly what you missed while you were gone. Not after `/quit`, after being kicked, or after changing your password: then you log in again.

## Groups screen 👥 (website)

Press **👥 Groups** in the sidebar. You see your groups first, then every other group (🔒 = private: you ask to join and an admin approves). Search at the top, **+ Create group** to make one.

- **A group's card:** its emoji, name, pinned topic, members (and how many are online), bank, upgrades and Hashbrown's persona there. **Open chat**, **Join** / **Request to join**, or **Leave**.
- **Click a group's name** for the details: members with their role (👑 owner, 🛡️ admin) and a green dot when online, and the group's war.
- **🏦 Bank** (members): the balance, what it earns right now and why (10 🪙 a minute while a member is online), a chart of the last days, **Donate**, the top donors and the history: who donated, what admins bought, war prizes and Hashbrown questions the bank paid.
- **⬆️ Upgrades:** every upgrade with its price and state: ✅ owned, 🟢 the bank can buy it, or 🔒 how much is missing. Admins get a **Buy** button with a confirm step that shows the bank after buying; everyone else sees who the admins are.
- **🛡️ Admin tools** (only that group's admins see them): join requests with **Approve** / **Reject**, and for each member **Kick**, **Mute** (5, 15 or 60 min), **Ban**, **Promote** / **Demote** (owner). Set the topic, emoji and persona. **Disband** asks you to type the group's name first.

Every button sends the same command you'd type (like `/approve Ben Secret` or `/kick Ben`), so the server's rules decide. Most group commands work in the group's room, so a button for another group opens that group first. The server's answer shows at the bottom of the screen.

## Chat switcher 💬 (website)

The **💬 Chats** list in the sidebar shows 🌍 the Lobby and every group you're in. Messages from a room you're not looking at don't fill your screen: that room gets an unread count and a preview of its last message. Click a room to open it (the same as `/join name` or `/lobby`): you see only that room's messages, and its topic at the top. The terminal client keeps working the old way (you only get the room you're in).

## For the networking class 🔬

- **Packet X-ray** (website, bottom of the sidebar): the **Packets** tab shows every JSON packet your tab sends ⬆ and gets ⬇. The **TCP** tab shows the raw bytes of each `recv()` the website's bridge did: newlines are shown as ⏎, and a chunk that ends in the middle of a packet says so. Login packets (your password) are never recorded.
- **`python client.py --packets`**: the terminal client prints every packet (password hidden), every `recv()` chunk and the UDP discovery packets.
- **UDP auto-discovery**: `python client.py` with no IP broadcasts `{"type": "discover"}` to UDP port 8821. Every server on the Wi-Fi answers; you confirm the one you want (anyone can answer a broadcast).
- **`/ping`**: a `ping` packet goes to the server and comes straight back as `pong`: the time it took is the round trip.
- **`/netstats`**: how many packets and bytes the server got from you and sent you.
- **🗺️ Network map** (website, bottom of the sidebar): the server in the middle and every connected player around it. Dots fly toward the server for packets a player sent and away for packets they got, coloured by kind, once a second. Each player's ping is measured with a tiny `probe` packet the server sends and the app answers. Only the kinds of packets are shown, never what's in them; private groups' names are hidden from outsiders.
- **Network lab** (type these in the server window): `lag 300` delays every packet the server sends by 300 ms; `loss 10` makes 10% of them "get lost". TCP never really loses data: it sends a lost packet again, so it arrives late and everything after it waits too (head-of-line blocking). `lab` shows the settings, `lab off` turns it off. While it's on, everyone on the website sees a 🧪 banner saying what it does.

## Server console

Type these in the server window:

- `say hello everyone`: broadcast a message
- `give Yaniv 500`: give someone tokens
- `kick Yaniv`: disconnect someone
- `list`: who's online
- `save`: save data now

## How it works (short version)

- **TCP sockets**: the server gives every client its own thread. The main thread only calls `accept()`.
- **Messages**: every message is one line of JSON ending with `\n`. TCP is a stream, so the newline is how each side knows where a message ends.
- **Shared state**: `online`, `accounts`, `groups` and the rest are protected by a single `threading.RLock`.
- **Sending**: each client has an outbox queue and a writer thread, so one slow connection can't freeze everyone.
- **Hashbrown**: the AI call runs in its own thread, outside the lock, so the chat keeps working while the AI thinks.
- **Game logic**: lives in `games.py` with no networking.
- **Code layout**: `server.py` only starts the server. The code is in `chatserver/`, one topic per file:
  - `config.py`: every setting (ports, prices, limits, `ADMIN_PASSWORD`). Edit it, then restart.
  - `state.py`: what the server keeps in memory (accounts, groups, who's online).
  - `connections.py`: accepting connections and talking to each client.
  - `cmd_*.py`: the /commands, one file per section of /help (`cmd_chat.py`, `cmd_games.py`...).
  - `chat.py`: what happens with each line someone types (a chat message, a /command or a game move).
  - `registry.py` + `commands.py`: how a /command registers itself, and the order of the /help sections.
  - The rest: `storage.py` (saving), `auth.py` (logins), `rooms.py` (sending to people), `matches.py` (two-player matches and bets), `hashbrown_ai.py`, `background.py` (income, quiz, console).
- **Adding things**:
  - a /command: a function with `@registry.command(...)` in the right `cmd_*.py` (example in `registry.py`).
  - a setting: a line in `config.py`, read it as `config.NAME`.
  - a game: its class in `games.py`, then one line in the `GAMES` table in `cmd_games.py`.

## Known limits

- Messages are **not encrypted** on the network. Anyone on the same Wi-Fi with Wireshark can read them, passwords included. Don't reuse a real password.
- In PyCharm's Run window, the password is visible while you type it. A real terminal hides it.
- No "typing..." indicator. `input()` only gives the program your text after you press Enter.
- In a real terminal (Mac Terminal, Windows Terminal or CMD), incoming messages appear above the line you're typing, and your text stays put. PyCharm's Run window can't do that unless you turn on **Run > Edit Configurations > Modify options > Emulate terminal in output console**. That setting also hides the password while you type it.
- Emojis look best in PyCharm, Windows Terminal or the Mac Terminal.
