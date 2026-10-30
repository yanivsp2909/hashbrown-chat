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
| Casino and `/rob` | risky 😈 |

**Group bank:** every group earns 10 🪙 per minute while at least one member is online. Anyone can `/donate`, and admins spend the bank with `/upgrade`:

| Upgrade | Price | Effect |
|---|---|---|
| 💰 income | 300 | members earn +2 🪙/min while inside the group |
| 📜 history | 200 | chat history goes from 15 to 50 messages |
| 🎨 emoji | 150 | a custom emoji next to the group name (`/groupemoji 🍟`) |
| 🥔 hashbrown | 250 | Hashbrown questions asked in the group are paid by the bank |

If an owner disbands a group, whatever is left in the bank goes to them.

## Commands

| | |
|---|---|
| 💬 Chat | `/help` `/users` `/send name msg` `/me action` `/nick name` `/whois name` `/quit` |
| 🥔 Hashbrown | `@hashbrown question` (everyone sees the answer) or `/ask question` (only you see it, you pay) |
| 👥 Groups | `/groups` `/create name [private]` `/join name` `/lobby` `/leave` `/members` `/requests` `/approve name` `/reject name` |
| 🛡️ Admin | `/kick` `/ban` `/unban` `/mute name [min]` `/unmute` `/promote` `/demote` `/disband` |
| 🏦 Group bank | `/bank` `/donate amount` `/upgrade name` `/groupemoji 🍟` `/topgroups` |
| 🪙 Tokens | `/balance` `/top` `/give name amount` `/daily` `/rob name` `/shop` `/buy 🔥` `/badge 🔥` `/achievements` |
| 🎰 Casino | `/coinflip amount heads` `/dice amount` `/slots amount` |
| 🎮 Games | `/games` `/challenge name ttt\|damka\|math [bet]` `/accept` `/decline` `/board` `/resign` `/wordle` `/g word` `/giveup` |
| 🛠️ Admin | `/admin password` `/admintokens [name]` |
| 📁 Files | `/sendfile name path/to/file` |

**During a game**, just type your move:
- Tic-Tac-Toe: `5`
- Damka: `c3 d4`
- Math Duel: the number, like `42`

The admin password is `ADMIN_PASSWORD` in `chatserver/config.py`. **Change it from 123**, or your friends will guess it.

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
