// 🗃️ App state. Never mutated: every change makes a new frozen object and tells the listeners.

const listeners = new Set();
let state = Object.freeze({
  screen: "loading",     // loading | login | chat | closed
  nick: "",
  room: "🏠 Lobby",
  commands: [],          // [{name, usage, description}] from the quiet /help
  match: null,           // {state, text, result} for ttt / damka / math
  wordle: null,          // {state, text, result}
  invites: [],           // [{from, text, at}] challenges waiting for you
  groupInvites: [],      // 📨 [{group, name, from, expires}] group invites waiting for you (groupinvites.js)
  knownNames: [],
  online: null,          // [{name, shown, room, playing}] from a quiet /users, null = not known yet
  balance: null,         // your tokens from a quiet /balance, null = not known yet
  rooms: [],             // 💬 [{key, name, title}] the chat switcher's list (from the server's "rooms" packet)
  currentRoom: "",       // the key of the room you're in
  unread: {},            // room key -> messages you haven't seen there
  previews: {},          // room key -> "Name: last message"
});

export const getState = () => state;

export function setState(patch) {
  state = Object.freeze({ ...state, ...patch });
  for (const listener of listeners) listener(state);
}

export function subscribe(listener) {
  listeners.add(listener);
  listener(state);
}
