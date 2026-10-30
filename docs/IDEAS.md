# 💡 Ideas for later

Not built yet. Each one keeps the protocol compatible (new optional fields or packet types only).

| Idea | What it is | Server changes it would need |
|---|---|---|
| ✔️ Read receipts | Private messages show ✓ delivered and ✓✓ seen | A message id on private messages and a new `seen` packet from the reader |
| ⏰ `/remind 10m text` | The server reminds you later | A small timer list in `state.py`, checked by a background job |
| 📌 `/pin` | A room topic shown to everyone who joins | A `pinned` field per room, saved, sent with the room history |
| 🔎 `/search word` | Search the room's history | A query on the SQLite history (`LIKE`), results as a list card |
| 🎯 Daily quests | Three small tasks a day (win a game, send 20 messages...) for tokens | Quest progress per account, hooks in the chat and match code |
