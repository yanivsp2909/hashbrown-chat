# Hashbrown Chat

A school networking project: a TCP chat server (`server.py` launches `chatserver/`), a terminal client (`client.py`),
a website (`web/`: `web_server.py` + `bridge.py` + `static/`) and an AI member, Hashbrown.

**The build plan and status live in `docs/PROGRESS.md`.** Continue from the first item that isn't done or skipped.

## Rules
- **The protocol only grows:** new optional fields or new packet types, never renamed or removed ones.
  Old `client.py` copies must keep working (they ignore unknown types and fields: keep it that way).
- **Keep the wording** that `web/static/js/patterns.js` matches. If server text changes, `web/tests/test_bridge.py` says which pattern breaks.
- **No encryption** anywhere (teacher's rule): no TLS, packets stay readable.
- **Networking stays on Python's built-in `socket` module**, as learned in school: TCP for the chat, UDP for discovery.
  Never replace it with websockets, asyncio frameworks or a web framework. A new feature adds new packet types on
  the same TCP connection. (The website's `web_server.py` uses the standard library's `http.server` only because a
  browser can't open a raw TCP socket; its bridge talks to the chat server over that same TCP connection.)
- `client.py` is one file, standard library only. The server's only library is `openai` (`requirements.txt`), and it must start without it.
- **Tests never call the real AI** (fake server in `tests/helpers.py`). Never print or log the API key, never open
  `hashbrown_config.json` by hand, never run `test_hashbrown.py` or `start.sh`.
- Python 3.8+ syntax. Readable for a student: small functions, plain names, comments for the *why*.
- Settings in `chatserver/config.py`, read as `config.NAME`; shared data in `chatserver/state.py` as `state.x`.
- A new `/command`: a function with `@registry.command(...)` in the right `cmd_*.py`. A new `cmd_*.py` must be listed in `commands.py`.
- Never delete the owner's data (`chat_data.json`, `history.db`, `received_files/`).

## Commands
```bash
python3 -m pytest -q --tb=short -p no:cacheprovider        # server tests (~1 min)
python3 -m unittest discover -s web/tests                  # website tests (when web/ or server text changes)
node --check web/static/js/<file>.js                       # JS syntax
python3 -m pyflakes chatserver/ tests/                     # unused/undefined names
```

## How to work
- Failing test first, then the code. After each feature: tests, commit (Conventional Commits), one line in PROGRESS.md.
- After each group: full suite + web tests, one code review, update README.md and docs/GUIDE.md, `git push`.
  Then write "GROUP DONE" and a 3-line summary.
- Stop and ask only if: a secret turns up, something can't stay compatible with old clients, the real AI key
  would be needed, or data would be deleted. Otherwise decide, note it in PROGRESS.md, keep going.
- Agents only when they add something: one code-reviewer per group; security-reviewer for UDP discovery,
  file transfer and login. Give them exact files. Never two agents on the same code at once.
- Read only the lines you need (grep first). Screenshots only at the end of a group that changed the website.
