# 🥔 Hashbrown Chat: the user guide

> 📘 This is the full user guide. For the project overview, see the [README](../README.md).
>
> IP addresses in this guide, such as `192.168.1.20`, are examples. Use your host's IP.

A chat for friends on the same Wi-Fi, with groups, games, a token economy and an AI member called Hashbrown. One person runs the server; everyone else joins from a browser (the website) or a terminal (`client.py`).

Pure Python 3.8 or newer. Nothing to install for the chat itself; only Hashbrown, the AI, needs the `openai` package (see [Waking up Hashbrown](#waking-up-hashbrown-)).

**Contents:** [How to run](#how-to-run) · [Website](#website-) · [Waking up Hashbrown](#waking-up-hashbrown-) · [Earning tokens](#earning-tokens-) · [Market, fund, savings and loans](#market-fund-savings-and-loans-) · [Every command](#every-command) · [Games and more](#games-and-more-) · [Hashbrown extras](#hashbrown-extras-) · [Website screens](#website-screens) · [For the networking class](#for-the-networking-class-) · [Server console](#server-console) · [How it works](#how-it-works-short-version) · [The protocol](#-the-protocol) · [Known limits](#known-limits)

## Files

| File | Who needs it |
|---|---|
| `server.py` + `games.py` + `chatserver/` | the person hosting (same folder) |
| `web/` | the host: the website, which `server.py` starts by itself |
| `client.py` | everyone who joins from a terminal (one file, nothing to install) |
| `start.sh` | the host on a Mac: starts the server with the AI key and admin password from the Keychain |
| `test_hashbrown.py` | the host, to check the AI key works |
| `chat_data.json` | created by the server: accounts, tokens, groups, the economy |
| `history.db` | created by the server: the chat history (SQLite) and the group banks' history |
| `hashbrown_config.json` | created by the server: **your API key. Never send this to anyone.** |

## How to run

**Host:**
```
python3 server.py
```
(or `./start.sh` on a Mac, see [Waking up Hashbrown](#waking-up-hashbrown-)). Allow incoming connections if your computer asks. The server also starts the website and prints the link to share.

**Everyone else**, from a terminal:
```
python3 client.py
```
It looks for the server on the Wi-Fi by itself (a UDP broadcast, see [For the networking class](#for-the-networking-class-)) and asks you to confirm it. If it finds nothing, it asks for the IP; `python3 client.py 192.168.1.20` skips the search. Then it asks **1) terminal 2) website**: Enter plays in the terminal, **2** opens the host's website in your browser (`--web` skips the question). Pick **2** to create an account or **1** to log in, and type `/help`.

## Website 🌐

Friends can use the chat from a browser instead of `client.py`, on a phone or a laptop. Nothing to install.

**Host:** `python3 server.py` starts the website too (on port 8080). If you turned that off (`START_WEBSITE = False` in `chatserver/config.py`), keep `server.py` running and in a second window run:
```
python3 web/web_server.py
```
It prints the link to share, for example:
```
[WEB] 🔗 Share this link: http://192.168.1.20:8080
```
Friends must be on the **same Wi-Fi**. The address is your computer's current Wi-Fi address, so it changes when you switch networks: restart and it prints the new one.

In the browser, friends create an account or log in (the same accounts as `client.py`), then:
- 🎟️ Challenges, your game and your Wordle hang as "order tickets" at the top of the chat. Press **Accept** to play.
- 🎮 Boards are clickable: tap a square in Tic-Tac-Toe, a piece and then a square in Damka, a column in Connect 4, a square in Battleship; type the answer in Math Duel and guess in Wordle.
- ⌨️ Type `/` to see every command and `@` to mention someone. **Up** brings back what you sent before.
- 📎 The paperclip, or dragging a file onto the chat, sends a file (up to 15 MB). The other side is asked first; files you get show up as **Download** buttons.
- 🌙 Dark and light mode (it follows you to every device), and it works on phones.

Options: `--port 8080` (website port), `--chat-port 8820` (where `server.py` listens), `--max-sessions 50`. Each browser tab is one login. A reloaded tab stays logged in. A closed tab logs out after 90 seconds (or right away with **Log out**).

**Tests:** `python3 -m unittest discover -s web/tests -v` runs a copy of the server in a temporary folder, so your real `chat_data.json` is never touched. A test also fails with a clear message if you reword a server message the website relies on; those messages are listed at the top of `web/static/js/patterns.js`.

Same warning as the terminal client: the website is plain HTTP, so anyone on the Wi-Fi could read messages and passwords.

## Waking up Hashbrown 🥔

Hashbrown runs on an Azure OpenAI deployment on Microsoft Foundry. Without a key everything else still works; Hashbrown is just off.

0. Install the one package Hashbrown needs: `pip install -r requirements.txt`. (It's pinned below version 2 because newer `openai` versions need a newer Python than 3.8.) Without it the server still starts and says `Hashbrown needs the openai package`.
1. Give it the key, one of these ways:
   - **Environment variable** (wins over the file): `export HASHBROWN_API_KEY="your-key"` (Windows PowerShell: `$env:HASHBROWN_API_KEY="your-key"`).
   - **Mac Keychain:** save it once with `security add-generic-password -a "$USER" -s hashbrown-foundry -w` (it asks for the key), then start with `./start.sh`.
   - **The config file:** the server creates `hashbrown_config.json` next to `server.py` on its first run. Fill it in:
     ```json
     {
       "endpoint": "https://YOUR-RESOURCE.services.ai.azure.com/openai/v1",
       "deployment": "YOUR-DEPLOYMENT-NAME",
       "api_key": "PASTE-YOUR-KEY-HERE"
     }
     ```
2. Run `python3 test_hashbrown.py`. It asks Hashbrown one question and tells you if the key works.
3. Start the server. It should print `🥔 Awake!`.

**Streaming:** the server asks for the answer in pieces. The website shows it appearing live, then the final cleaned text replaces it; `client.py` gets one full message at the end. If the AI breaks halfway, the live text disappears and the tokens are refunded.

**Costs and limits:** each question costs 20 🪙. There's a 15 second cooldown per person, a limit of 30 questions per person per day and 100 for the whole server. If the AI call fails, the tokens are refunded. Every question also costs **real money** on your Azure account (`/hbstats` shows today's estimate).

## Earning tokens 🪙

| Way to earn | Amount |
|---|---|
| Being online | 5 🪙 per minute |
| Being inside a group with the 💰 income upgrade | +2 🪙 per minute |
| `/daily` | 150 🪙, +50 for each day in a row, up to 500. Claim again within 20-48 hours or the streak resets. |
| Winning a game | +25 🪙 for each of your first 10 wins per day, plus the pot if there was a bet |
| Wordle (`/wordle`) | 60 🪙 for 1 try down to 10 🪙 for 6 tries, 5 rewarded games a day |
| Drawing game (`/draw`) | 30 🪙 for the right guess, 15 🪙 for the drawer |
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
| 🎭 personality | 200 | Hashbrown plays a role you choose in the group (`/personality`) |

If an owner disbands a group, whatever is left in the bank goes to them.

**`/give` limits** (against making extra accounts to farm tokens): an account can't give in its first 24 hours, and nobody gives more than 500 🪙 a day in total. Tipping Hashbrown (`/give hashbrown 10`) counts too; Hashbrown keeps its tips and shows up in `/top`.

## Market, fund, savings and loans 📈

All the numbers are in the economy part of `chatserver/config.py` (search for "the economy").

- **📈 Stocks:** `/stocks`, `/buy FRY 5`, `/sell FRY 5`, `/portfolio`. Four companies: 🍟 FRY (starts at 100), 🥔 SPUD (50), 🧂 SALT (20), 🥫 KTCH (75). Every minute each price takes a small random step (about 2%), with a gentle pull back toward where it started, at most 6% a minute and never below 1. Every buy and sell costs a 1% fee (at least 1 🪙). The website's **📈 Market** shows a live chart of each one.
- **👥 Group stocks:** every group is a stock too: `/buy #Potatoes 3`. Its price follows the group's bank, members and how busy its chat was in the last hour (each person's lines count at most 10 an hour). A group that grew since yesterday pays its shareholders 2% of the price per share a day, out of its own bank. If a group is disbanded, its shareholders are paid the last price.
- **🧾 The public fund:** the trading fees, 5% of marketplace sales, a 10% tax on casino wins of 200 🪙 or more, loan repayments and auction money go into it. The quest, question-of-the-day and drawing prizes come out of it first, and savings interest and loans only come from it, so tokens go round instead of being printed.
- **🏦 Savings:** `/save 100`, `/withdraw 100`, `/savings`. Up to 5000 🪙; +1% a day (at most 50 🪙), while the fund has it.
- **💳 Loans:** `/loan 200` (up to 500, one at a time; your account must be older than a day and have sent 20 messages; the fund must have it). You owe 10% more, within 3 days; `/repay all`. If you're late, your per-minute income pays it back first, and at login your tokens and savings do.
- **🛒 Marketplace:** `/sell badge 🔥 300` puts a badge you own up for sale, `/market` shows what's for sale, `/market buy 2` buys number 2, `/market cancel 2` takes yours back. 5% of the price goes to the fund. Buying follows the `/give` limits.
- **🔨 Auctions:** every 6 hours (with 2+ people online) a rare badge (🦄 🌈 🪐 🐉 🏆, not in the shop) is auctioned in the lobby for 2 minutes. `/bid 150`: your tokens are held, and given back if someone bids more. The money goes to the fund. Admins can start one with `/auction`.
- **📰 Market news:** when a stock is 15% up or down for the day, Hashbrown posts a funny headline in the lobby (at most 3 a day).
- **📊 Economy dashboard** (website): every token in the game, the fund, the hottest stock, the week's inflation and the richest players.

## Every command

These are all 96 commands, in the same groups as `/help`. `[ ]` means optional. 👥 The group commands (`/leave`, `/members`, `/requests`, `/approve`, `/reject`, the 🛡️ Group admin and 🏦 Group bank commands except `/topgroups`, and `/war`) work only in a group's chat and act on that group; anywhere else they answer "👥 Open the group's chat to use /kick". In the lobby `/help` leaves them out. `/create` and `/join` work from anywhere. Anything that isn't a command is a chat message to the room you're in; start a message with `@hashbrown` to ask the AI (20 🪙).

### 💬 Chat

| Command | What it does |
|---|---|
| `/help` | Show the list of commands |
| `/users` | Who's online and in which room |
| `/send name message` | A private message 💌. If they're offline it waits for them (up to 20). On the website you see ✓ delivered and ✓✓ seen |
| `/remind 10m text` | A private reminder later ⏰ (`2h`, `1h30m`, `90s`; up to 24 hours, 5 at a time). `/remind` alone lists yours |
| `/pin text` | Pin this room's topic 📌 (group admins in a group, a server admin in the lobby). `/pin` alone shows it, `/pin clear` removes it |
| `/search word` | Find it in the chat of your rooms 🔎 (newest first, 20 at most) |
| `/me action` | Act it out: `* Yaniv dances` |
| `/nick newname` | Change your display name |
| `/whois name` | Someone's profile |
| `/quit` | Leave the chat |
| `/poll question \| a \| b` | Ask the room to vote 📊 (2-6 options). `/poll` alone shows the votes |
| `/vote number` | Vote in the room's poll |
| `/endpoll` | Close your poll and show who won |

### 👤 Profile

| Command | What it does |
|---|---|
| `/profile [name]` | Someone's profile card 👤 (yours without a name) |
| `/setprofile field value` | Change your profile. Fields: `avatar` (one emoji), `bio`, `status` (online / away / busy), `statustext`, `color` (0-7 or auto), `game`, `theme` (light / dark), `lastseen` (show / hide), `dms` (everyone / groups / nobody). Example: `/setprofile bio I love fries` |
| `/password old new` | Change your password (the old one first) 🔑 |

### 👥 Groups

| Command | What it does |
|---|---|
| `/groups` | List all groups |
| `/create name [private]` | A new group (50 🪙). Private groups need an admin to let you in |
| `/join name` | Enter a group (or ask to, if it's private) |
| `/lobby` | Go back to the lobby |
| `/leave` | Quit the group you're in |
| `/members` | Who's in this group |
| `/requests` | Join requests (admins) |
| `/invite name` | Invite someone 📨 (admins, in the group's chat). Works for private groups too: no join request. The invite lasts 24 hours, only while you're still an admin; at most 20 waiting per group and 10 per person, and the same person again after a minute. It follows their "who can message me" setting |
| `/invites [decline group]` | Your group invites (from anywhere). `/join group` accepts one, `/invites decline group` says no |
| `/approve name` | Let someone in (admins, in the group's chat) |
| `/reject name` | Turn down a request (admins, in the group's chat) |

### 🛡️ Group admin

| Command | What it does |
|---|---|
| `/kick name` | Remove from the group |
| `/ban name` | Kick, and they can't come back |
| `/unban name` | Allow them back in |
| `/mute name [minutes]` | Silence someone (5 minutes by default) |
| `/unmute name` | Let them talk again |
| `/promote name` | Make them an admin (owner only) |
| `/demote name` | Remove an admin (owner only) |
| `/disband` | Delete your group (owner only); the bank goes to you |

### 🏦 Group bank

| Command | What it does |
|---|---|
| `/bank` | The group's bank and upgrades |
| `/donate amount` | Put your tokens in the group bank |
| `/upgrade name` | Buy an upgrade with the bank (admins). See [the upgrades](#earning-tokens-) |
| `/groupemoji emoji` | Set the group's emoji (needs the 🎨 upgrade) |
| `/personality text` | How Hashbrown acts in this group (needs the 🎭 upgrade). Empty turns it off |
| `/topgroups` | The richest groups |

### 🪙 Tokens

| Command | What it does |
|---|---|
| `/balance [name]` | How many tokens 🪙 |
| `/top` | The richest players 🏆 |
| `/give name amount` | Send tokens to someone (not in your account's first 24 hours, at most 500 a day) |
| `/daily` | Free tokens every day, more for a streak 🔥 |
| `/rob name` | 40% chance to steal, or pay a fine 🦹 |
| `/shop` | Badges for your name |
| `/buy badge` | Buy a badge from `/shop`, like `/buy 🔥` (also buys shares: `/buy FRY 5`) |
| `/badge emoji\|off` | Wear a badge you own, or none |
| `/achievements` | Your trophies and how to get the rest |

### 🎰 Casino

Fake tokens only. 10% of every loss goes into the jackpot, and wins of 200 🪙 or more pay a 10% tax to the public fund.

| Command | What it does |
|---|---|
| `/coinflip amount heads\|tails` | Double or nothing |
| `/dice amount` | Two dice against the house 🎲 |
| `/slots amount` | Three of the same = x10, 💎💎💎 = x25 and the jackpot |
| `/jackpot` | The pot that three 💎 on `/slots` wins 💰 |

### 📈 Market

| Command | What it does |
|---|---|
| `/stocks` | Stock prices and today's change 📈 (buy with `/buy FRY 5`) |
| `/sell FRY 5` | Sell shares, or put a badge up for sale: `/sell badge 🔥 300` |
| `/portfolio` | Your shares and what they're worth |
| `/market [buy N \| cancel N]` | Players' badges for sale 🛒; buy number N, or take your listing back |
| `/bid amount` | Bid in the lobby's auction 🔨 |

### 🛠️ Admin

Server admins only (the password comes from the Keychain item `hashbrown-admin` or the `HASHBROWN_ADMIN_PASSWORD` environment variable; it's never in the code).

| Command | What it does |
|---|---|
| `/auction` | Start an auction of a rare badge now |
| `/admin password` | Become a server admin |
| `/admintokens [name]` | +1000 🪙 (for you, or for someone) |
| `/hbstats` | Hashbrown's questions, tokens and estimated cost today 📊 |

### 🏦 Savings & loans

| Command | What it does |
|---|---|
| `/save amount` | Put tokens in savings (interest every day) 🏦 |
| `/withdraw amount` | Take tokens out of savings |
| `/savings` | Your savings and your loan |
| `/loan amount` | Borrow tokens (you pay back 10% more) 💳 |
| `/repay [amount\|all]` | Pay your loan back |

### 🎮 Games

| Command | What it does |
|---|---|
| `/games` | What you can play |
| `/challenge name game [bet]` | Invite someone to a 1v1 (if their "who can message me" setting lets you): `ttt`, `damka`, `math`, `connect4` (or `c4`), `battleship` (or `ships`), with an optional token bet |
| `/accept [name]` | Accept a challenge, or a file 📎 (`/accept file`) |
| `/decline [name]` | Say no to a challenge or a file |
| `/draw` | Start a drawing round: draw your word, the others guess 🎨 (`/draw stop` gives up) |
| `/quests` | Today's three small tasks, each pays 🪙 🎯 |
| `/move ...` | Make a move (or just type it, see below) |
| `/watch [name]` | Watch someone's game 👀 (`/watch` alone stops) |
| `/leaderboard [elo\|wins\|tokens]` | The best players (ELO by default) 📈 |
| `/hint` | A Wordle hint from Hashbrown, one per game (20 🪙) |
| `/rematch` | Challenge your last opponent again, same game and bet 🔁 |
| `/claim` | Win if the other player hasn't moved for 2 minutes ⏰ |
| `/board` | Show the board again |
| `/resign` | Give up the game 🏳️ |
| `/wordle` | A solo word game that wins tokens 🟩 |
| `/g word` | Guess in your Wordle |
| `/giveup` | Quit your Wordle |

**During a game**, just type your move: Tic-Tac-Toe `5`, Damka `c3 d4`, Math Duel the number (`42`), Connect 4 a column `1`-`7`, Battleship a square `c3`.

### 📁 Files

| Command | What it does |
|---|---|
| `/sendfile name path` | Send a file from the terminal (up to 2 MB) 📁. On the website, use the 📎 paperclip (up to 15 MB) |

### 🥔 Hashbrown

| Command | What it does |
|---|---|
| `/ask question` | Ask Hashbrown privately; only you see the answer (20 🪙). `@hashbrown question` asks in the room |
| `/tldr` | Hashbrown sums up the chat, only for you (20 🪙) |
| `/judge` | Hashbrown judges the argument, everyone sees it (20 🪙) |
| `/tr text` | Translate Hebrew ↔ English, only for you (20 🪙) |
| `/qotd` | Today's question of the day ❓ |
| `/answer text` | Answer the question of the day; the answer with the most reactions wins 50 🪙 |
| `/trivia` | Hashbrown asks the room a trivia question; the first right answer in 60 seconds wins 40 🪙 (20 🪙 to start) |

### 🌐 Network

| Command | What it does |
|---|---|
| `/ping` | How long a packet takes to the server and back 🏓 |
| `/netstats` | Packets and bytes on your connection 📊 |

### ⚔️ Group wars

| Command | What it does |
|---|---|
| `/war [group \| accept group]` | Your group against another ⚔️: an admin declares `/war group`, their admin answers `/war accept group` within 10 minutes, `/war` alone shows the score |

**New accounts** need a username of 3-16 English *or* Hebrew letters, digits or `_` (not both alphabets, so nobody can hide a look-alike letter in a name) and a password of 6 to 64 characters. Older accounts keep their names and passwords.

## Games and more 🎲

- 🔴🟡 **Connect 4** (`/challenge name connect4`): type a column 1-7, four in a row wins.
- 🚢 **Battleship** (`/challenge name battleship`): your ships are placed for you; fire like `c3`. Nobody, not even spectators, sees your ships.
- 📈 **ELO**: everyone starts at 1000; beating a stronger player gains more. `/leaderboard` shows the best.
- 👀 **Spectating**: `/watch name` follows their game; `/watch` alone stops.
- 📬 **Offline messages**: `/send` to someone offline waits for them (up to 20) and arrives when they log in.
- ✏️ **Edit/delete** (website): ✏️ or 🗑️ under your own message, for 10 minutes.
- 💰 **Jackpot**: 10% of every casino loss goes into a pot; three 💎 on `/slots` wins it. `/jackpot` shows it.
- 🧠 **Trivia**: `/trivia` (costs like `/ask`): Hashbrown asks the room a question; the first right answer in 60 seconds wins 40 🪙.
- ⚔️ **Group wars**: for 30 minutes, every game a member wins against the other group is a point; the winner takes 300 🪙 from the loser's bank.
- 📦 **Big files** (website): up to 15 MB, sent in 1 MB pieces with a progress bar. Each piece waits for the server's "got it" before the next one goes (flow control). The terminal client sends up to 2 MB.
- 📎 **Files are offered first**: the receiver sees "📎 Dana wants to send you photo.jpg (2.3 MB)" with Accept and Decline (or types `/accept file` / `/decline file`); nothing arrives before Accept, and an offer expires after 2 minutes. An old `client.py` that doesn't know about offers still gets files straight away.
- ⏰ **Reminders**: `/remind 10m take the fries out`. They survive a server restart; if you're away when one is due, you get it when you log in.
- 🎯 **Daily quests**: `/quests` shows today's three tasks (the same for everyone), each pays once.

### Drawing game 🎨

Type `/draw` (at least 2 people in the room). You get a secret word and a canvas above the chat; draw it with the mouse or a finger. Everyone else guesses in the chat. The server checks the guesses, so nobody's app ever sees the word before the end. The first right guess wins 30 🪙 and the drawer 15 🪙 (not for a guess in the first 8 seconds). A round lasts 90 seconds; `/draw stop` gives up, and you can start one every 2 minutes. Each brush stroke is one small `stroke` packet: open Packet X-ray while someone draws.

## Hashbrown extras 🥔

- 🎙️ **Commentator:** after every match, Hashbrown sends both players one funny line about it.
- ❓ **Question of the day:** once a day (after 10:00 Israel time, when at least two people are online) Hashbrown asks the lobby a fun question. `/qotd` shows it again. Answer with `/answer ...` (or the 💡 Answer button): one answer each, people vote with reactions, and when the next question comes the answer with the most reactions wins 50 🪙.
- 💸 **Tips:** `/give hashbrown 10` and Hashbrown says thanks. 📊 `/hbstats` (server admins) shows today's questions, tokens and an estimated cost (set your prices in `HASHBROWN_PRICE_IN` / `HASHBROWN_PRICE_OUT` in `config.py`).
- 🎭 **Group personality:** buy the 🎭 upgrade for your group (`/upgrade personality`), then a group admin types `/personality a pirate who loves potatoes`. Hashbrown plays that role in your group (all its rules still apply). `/personality` with nothing turns it off.
- 📰 **Market news:** a funny headline when a stock moves 15% in a day.
- These cost the server, not you, and count toward the server's daily Hashbrown limit.

## Website screens

### Reactions, typing and mentions 😂

Hover (or tab to) a message and press **☺︎+** to react with 👍 ❤️ 😂 😮 😢 or 🥔. Click a reaction under a message to add or take back yours. While someone in your room types, you see *Noa is typing…* above the message box. Type `@` for a list of the people in this chat and @hashbrown. A poll shows a button for each option.

### Group invites 📨

An admin invites you with `/invite name` or the Groups screen's **Invite** button. You get a ticket at the top of the chat, "📨 Alice invites you", with the group, the time left and **Accept** / **Decline** (in the terminal: `/join name` or `/invites decline name`). It works for private groups without a join request, and lasts 24 hours. Missed it while offline? It's waiting when you log in, and `/invites` lists them.

### Chat switcher 💬

The **💬 Chats** list in the sidebar shows 🌍 the Lobby and every group you're in. Messages from a room you're not looking at don't fill your screen: that room gets an unread count and a preview of its last message. Click a room to open it (the same as `/join name` or `/lobby`): you see only that room's messages, and its topic at the top. The terminal client keeps working the old way (you only get the room you're in).

### Groups screen 👥

Press **👥 Groups** in the sidebar. You see your groups first, then every other group (🔒 = private: you ask to join and an admin approves). Search at the top, **+ Create group** to make one.

- **A group's card:** its emoji, name, pinned topic, members (and how many are online), bank, upgrades and Hashbrown's persona there. **Open chat**, **Join** / **Request to join**, or **Leave**.
- **Click a group's name** for the details: members with their role (👑 owner, 🛡️ admin) and a green dot when online, and the group's war.
- **🏦 Bank** (members): the balance, what it earns right now and why, a chart of the last days, **Donate**, the top donors and the history: who donated, what admins bought, war prizes and Hashbrown questions the bank paid.
- **⬆️ Upgrades:** every upgrade with its price and state: ✅ owned, 🟢 the bank can buy it, or 🔒 how much is missing. Admins get a **Buy** button with a confirm step; everyone else sees who the admins are.
- **🛡️ Admin tools** (only that group's admins see them): **📨 Invite someone** (type a name or pick one: who's online first) and the invites still waiting, join requests with **Approve** / **Reject**, and for each member **Kick**, **Mute** (5, 15 or 60 min), **Ban**, **Promote** / **Demote** (owner). Set the topic, emoji and persona. **Disband** asks you to type the group's name first.

Every button sends the same command you'd type (like `/approve Ben` or `/kick Ben`), so the server's rules decide. A button also says which group it's for (the `group` field of the `line` packet), so it acts on that group and you stay in the chat you're in.

### Profiles 👤

Your avatar and name colour also show on your chat bubbles. Click anyone's name (in the online list or in the chat) for their card, or **👤 My profile** for yours, then **✏️ Edit profile**: an emoji avatar, your display name (same as `/nick`), a bio, a status (🟢 online, 🌙 away, ⛔ busy, plus your own line), a name colour, your favourite game, the theme (it follows you to every device), privacy (show "last seen" or not; who can send you private messages and files: everyone, people in your groups, or nobody) and a new password (the old one first). Your username never changes.

### Market and economy 📈

**📈 Market** shows every stock (the four companies and every group) with a live chart, today's change, your shares and Buy / Sell. **📊 Economy** shows every token in the game, the public fund, the hottest stock, the week's inflation and the richest players.

### If the connection drops 🔁

The website and `client.py` reconnect by themselves (they try for about two minutes) and you get exactly what you missed while you were gone. Not after `/quit`, after being kicked, or after changing your password: then you log in again.

## For the networking class 🔬

- **Packet X-ray** (website, bottom of the sidebar): a side panel next to the chat (on smaller screens it docks under the chat, on a phone like a drawer from the bottom). It doesn't block anything: keep chatting and playing while it runs. The **Packets** tab shows every JSON packet your tab sends ⬆ and gets ⬇. The **TCP** tab shows the raw bytes of each `recv()` the website's bridge did: newlines are shown as ⏎, and a chunk that ends in the middle of a packet says so. Both record from the moment the page loads, open or not (the newest 500 of each), so opening it shows what already happened; after a reload, packets the bridge sends again are marked "↺ replayed". **Pause** stops recording, **Clear** empties both tabs, and **Type** shows only one kind of packet (in the TCP tab: the chunks that hold one). Passwords and reconnect tokens show as •••. Escape or ✕ closes it.
- **`python3 client.py --packets`**: the terminal client prints every packet (password hidden), every `recv()` chunk and the UDP discovery packets.
- **UDP auto-discovery**: `python3 client.py` with no IP broadcasts `{"type": "discover"}` to UDP port 8821. Every server on the Wi-Fi answers; you confirm the one you want (anyone can answer a broadcast).
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
- `lag 300`, `loss 10`, `lab`, `lab off`: the network lab

## How it works (short version)

- **TCP sockets**: the server gives every client its own thread. The main thread only calls `accept()`.
- **Messages**: every message is one line of JSON ending with `\n`. TCP is a stream, so the newline is how each side knows where a message ends.
- **Shared state**: `online`, `accounts`, `groups` and the rest are protected by a single `threading.RLock`.
- **Sending**: each client has an outbox queue and a writer thread, so one slow connection can't freeze everyone.
- **Reconnect**: kept packets get a `seq` number; after a drop the app sends the last one it saw and gets exactly the rest (the last 500, up to 10 minutes).
- **Hashbrown**: the AI call runs in its own thread, outside the lock, so the chat keeps working while the AI thinks.
- **Game logic**: lives in `games.py` with no networking.
- **Code layout**: `server.py` only starts the server. The code is in `chatserver/`, one topic per file:
  - `config.py`: every setting (ports, prices, limits). Edit it, then restart.
  - `state.py`: what the server keeps in memory (accounts, groups, who's online).
  - `connections.py` + `session.py`: accepting connections and talking to each client.
  - `cmd_*.py`: the /commands, one file per section of /help (`cmd_chat.py`, `cmd_games.py`...).
  - `chat.py`: what happens with each line someone types (a chat message, a /command or a game move).
  - `registry.py` + `commands.py`: how a /command registers itself, and the order of the /help sections.
  - The rest: `storage.py` (saving), `history.py` (SQLite), `auth.py` and `resume.py` (logins and reconnects), `rooms.py` (sending to people), `matches.py` (two-player matches and bets), `market.py`, `fund.py`, `savings.py`, `auctions.py` (the economy), `hashbrown_ai.py`, `background.py` (income, quiz, console).
- **Adding things**:
  - a /command: a function with `@registry.command(...)` in the right `cmd_*.py` (example in `registry.py`).
  - a setting: a line in `config.py`, read it as `config.NAME`.
  - a game: its class in `games.py`, then one line in the `GAMES` table in `cmd_games.py`.

## 📡 The protocol

Every packet is **one JSON object on one line**, ending with `\n` (newline-delimited JSON). New things are only ever *added* (new optional fields or packet types), so an old `client.py` keeps working: it ignores what it doesn't know. Some packets only go to apps that asked for them with the optional `features` list in the login packet (like `"stream"`, `"rooms"`, `"probe"`).

| Direction | Type | Fields |
|---|---|---|
| client → server | `auth` | `action` (`login`, `register` or `resume`), `username`, `password` (or `token` and `seq` for `resume`), optional `features` (e.g. `["stream", "rooms"]`) |
| server → client | `auth_result` | `ok`, `text`, and `resume_token` (and `resumed`) for reconnecting |
| client → server | `line` | `text` (a chat message or a `/command`); optional `group`: the group key a group command is for (the Groups screen's buttons; you must be a member, other lines ignore it) |
| server → client | `msg` | `kind`, `text`. `kind` is one of `system`, `error`, `event`, `money`, `game`, `private`, `help` or `board`; board messages also have a `state` object; a file offer has `offer` (`id`, `from`, `filename`, `size`); kick notices have `kicked` |
| server → client | `chat` | `time`, `name`, `badge`, `text`, `action`, `id`, the sender's `avatar` and `color` if they set them, and `room` (its key) for clients with the `rooms` feature |
| server → client | `history` | `room` (its title), `key` (which room), `messages` |
| server → client | `rooms` | `current`, `rooms` (`key`, `name`, `title`): only for clients with the `rooms` feature |
| server → client | `stream` | `stream_id`, `append` (a piece of Hashbrown's answer, only for clients with the `stream` feature) |
| server → client | `topic` | `room`, `text` (the pinned topic; empty = none), on every room switch and when it changes |
| server → client | `lab` | `lag_ms`, `loss_percent` (the network lab changed; 0 and 0 = off) |
| both ways | `ping` / `pong` | `t` (any number; it comes straight back: now minus `t` is the round trip) |
| both ways | `probe` / `probe_back` | `id`: the server's ping probe for the network map, only to clients with the `probe` feature |
| client → server | `typing` / `typing_stop` | (none): passed on with `name` to clients with the `typing` feature |
| server → client | `invite_closed` | `from`, `why` (`accepted`, `declined` or `gone`): a challenge to you is over, so its ticket goes |
| server → client | `invite_closed` (📨 group) | `group` (a group key), `why` (`accepted`, `declined`, `expired` or `gone`): a group invite to you is over |
| server → client | `msg` + `group_invite` | optional on an invite notice: `group`, `name`, `from`, `expires` (seconds): the website shows a ticket with Accept / Decline |
| client → server | `react` | `id` (a chat message), `emoji`: the room gets `reactions` with `id` and `counts` |
| client → server | `edit` / `delete` | `id` (your own message, for 10 min), `text`: the room gets `edited` / `deleted` |
| client → server | `seen` | `id` (a private message's `pm_id`): its sender gets `receipt` |
| server → client | `receipt` | `id`, `status` (`delivered` or `seen`); the sender's copy of a `/send` has `pm` (`id`, `status`), the receiver's has `pm_id` |
| client → server | `file` | `to`, `filename`, `data` (base64): a small file |
| server → client | `file` | `from`, `filename`, `data` |
| both ways | `file_start`, `file_chunk`, `file_ack`, `file_end`, `file_cancel` | big files in 1 MB chunks; the next chunk only after its `file_ack` (flow control) |
| client → server | `get_groups` / `get_group` / `groups_closed` | (none) / `group` (its key) / (none): the website's Groups screen opens, looks at one group, closes |
| server → client | `groups` / `group_info` | one card per group / one group's details, sent when asked and once a second while the screen is open and something changed. A private group you're not in shows only its name, emoji and size; `bank_details` only goes to members, `admin` only to that group's admins |
| client → server | `get_profile` / `change_password` | `name` / `old`, `new`: the server answers `profile` (`profile`, `mine`) |
| both ways | `stroke` | `points` (0-1000), `color`, `size`, or `clear`: the drawer's brush, passed to the room's `draw` clients; `draw_round` says when a round starts and ends |
| client → server | `get_netmap` / `netmap_closed` | the network map opens/closes: the server sends `netmap` (`players`: room, ping, packets per type) once a second |
| server → everyone | `market` | `prices`, `changes`, `time`: once a minute, one packet for all |
| client → server | `get_market` / `get_economy` | the market screen (`market_info`: stocks with recent prices, your shares) and the economy dashboard (`economy`) |
| UDP, client → everyone | `discover` | (none): broadcast to port 8821 |
| UDP, server → client | `server` | `name`, `port`, `web_port`: the client uses the IP the answer came from |

Packets the server keeps for a reconnect also carry an optional `seq` number.

## Known limits

- Messages are **not encrypted** on the network (on purpose: it's a networking project). Anyone on the same Wi-Fi with Wireshark can read them, passwords included. Don't reuse a real password.
- In PyCharm's Run window, the password is visible while you type it. A real terminal hides it.
- The terminal client can't show "is typing…": `input()` only gives the program your text after you press Enter.
- In a real terminal (Mac Terminal, Windows Terminal or CMD), incoming messages appear above the line you're typing, and your text stays put. PyCharm's Run window can't do that unless you turn on **Run > Edit Configurations > Modify options > Emulate terminal in output console**. That setting also hides the password while you type it.
- Emojis look best in PyCharm, Windows Terminal or the Mac Terminal.
