// 🟢 Who's online and how many tokens you have, kept fresh in the sidebar.
//
// The server only answers "/users" and "/balance" as text, so we ask quietly in the background
// (when you log in, when someone comes or goes, after money changes, and once a minute) and draw
// the answers as panels instead of filling the chat. Quiet questions are spaced out, because the
// server allows only 8 messages per 5 seconds for everything you send.

import { $, clear, el, initial, nameClass } from "./dom.js";
import { getState, subscribe } from "./store.js";

const COMMANDS = { users: "/users", balance: "/balance" };
const SETTLE = 400;          // ms: wait for a burst of events to finish before asking
const MIN_GAP = 4000;        // ms: never ask the same question more often than this
const SPACING = 1000;        // ms: at least this long between any two background questions
const YOURS_FOR = 10_000;    // ms: an answer this soon after YOU typed the command is shown to you
const REFRESH_EVERY = 60_000;

let sendLine = async () => null;
let youAskedAt = { users: 0, balance: 0 };   // when you typed /users or /balance yourself
let last = { users: 0, balance: 0 };         // when we last asked in the background
let nextFree = 0;   // the earliest time the next background question may go
let hooks = { onProfile: () => {} };   // 👤 clicking a name opens their profile
const timers = {};

async function ask(kind) {
  if (getState().screen !== "chat") return;
  last = { ...last, [kind]: Date.now() };
  await sendLine(COMMANDS[kind]);   // an error just means no fresh answer this time
}

/** Ask the server again soon ("users" or "balance"), without showing anything in the chat. */
export function refresh(kind) {
  if (getState().screen !== "chat") return;
  clearTimeout(timers[kind]);
  const now = Date.now();
  const wait = Math.max(SETTLE, last[kind] + MIN_GAP - now, nextFree - now);
  nextFree = now + wait + SPACING;
  timers[kind] = setTimeout(() => ask(kind), wait);
}

export function refreshAll() {
  refresh("users");
  refresh("balance");
}

/** You typed /users or /balance yourself: show you the next answer. */
export function youAsked(kind) {
  youAskedAt = { ...youAskedAt, [kind]: Date.now() };
}

/** True (once) if you asked for this answer in the last few seconds; otherwise it was ours. */
export function answerIsYours(kind) {
  if (Date.now() - youAskedAt[kind] > YOURS_FOR) return false;
  youAskedAt = { ...youAskedAt, [kind]: 0 };
  return true;
}

export function resetOnline() {
  for (const kind of Object.keys(COMMANDS)) clearTimeout(timers[kind]);
  youAskedAt = { users: 0, balance: 0 };
  last = { users: 0, balance: 0 };
  nextFree = 0;
}

function personRow(person, me, { onChallenge, onMessage }) {
  const isMe = person.name === me;
  const where = [person.room, person.playing ? "🎮 playing" : ""].filter(Boolean).join(" · ");
  return el("li", { class: "person" },
    el("span", { class: `avatar ${nameClass(person.name)}`, "aria-hidden": "true", text: initial(person.name) }),
    el("span", { class: "person-main" },
      el("button", { class: "person-name person-name-btn", type: "button", title: person.shown, "data-key": `profile:${person.name}`,
        "aria-label": `${person.shown}${isMe ? " (you)" : ""}: profile`, onclick: () => hooks.onProfile(person.name) },
      person.shown, isMe ? el("span", { class: "you", text: " (you)" }) : null),
      el("span", { class: "person-room", text: where })),
    isMe ? null : el("span", { class: "person-actions" },
      el("button", { class: "mini-btn", type: "button", "aria-label": `Challenge ${person.name}`, title: "Challenge",
        "data-key": `challenge:${person.name}`, onclick: () => onChallenge(person.name) },
      el("span", { "aria-hidden": "true", text: "⚔️" })),
      el("button", { class: "mini-btn", type: "button", "aria-label": `Private message to ${person.name}`, title: "Private message",
        "data-key": `message:${person.name}`, onclick: () => onMessage(person.name) },
      el("span", { "aria-hidden": "true", text: "💌" }))));
}

export function initOnline(options) {
  sendLine = options.sendLine;
  hooks = options;
  $("online-refresh").addEventListener("click", () => {
    last = { ...last, users: 0 };   // you asked: don't wait for the usual gap
    refresh("users");
  });
  setInterval(() => {
    if (!document.hidden) refreshAll();
  }, REFRESH_EVERY);

  let shown = {};
  let drawn = "";
  subscribe((state) => {   // state is frozen and replaced on every change, so !== means "changed"
    const people = state.online || [];
    const fingerprint = JSON.stringify([state.online, state.nick]);
    if (fingerprint !== drawn) {   // only redraw when something really changed: keeps keyboard focus
      drawn = fingerprint;
      const list = $("people");
      const focusedKey = list.contains(document.activeElement) ? document.activeElement.dataset.key : null;
      $("online-count").textContent = state.online ? `· ${people.length}` : "";
      $("online-sr").textContent = state.online ? `${people.length} ${people.length === 1 ? "person" : "people"}` : "";
      clear(list).append(...(state.online
        ? people.map((person) => personRow(person, state.nick, options))
        : [el("li", { class: "people-empty", text: "Checking who's here…" })]));
      const again = focusedKey && list.querySelector(`[data-key="${CSS.escape(focusedKey)}"]`);
      if (again) again.focus();
    }
    if (state.balance !== shown.balance) {
      $("me-balance").textContent = state.balance === null ? "…" : `${state.balance.toLocaleString("en-US")} tokens`;
    }
    shown = state;
  });
}
