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
  knownNames: [],
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
