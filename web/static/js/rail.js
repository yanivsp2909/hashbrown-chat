// 🎟️ The ticket rail: challenges waiting for you, your game and your Wordle hang here as order tickets.

import { $, clear, el, str } from "./dom.js";
import { sendLine } from "./api.js";
import { getState, setState, subscribe } from "./store.js";
import * as GI from "./groupinvites.js";
import { answerRequest } from "./friends.js";

export const INVITE_LIFETIME = 180_000;  // the server forgets a challenge after 3 minutes
const LOW_TIME = 30_000;
const RESULT_TEXT = { won: "won", lost: "lost", draw: "draw" };

const rail = $("rail");
const numbers = new Map();   // ticket key -> order number, so a ticket keeps its number
let nextNumber = 1;
const seen = new Set();      // tickets already on screen: only new ones animate in
const stamped = new Set();

function orderNumber(key) {
  if (!numbers.has(key)) numbers.set(key, nextNumber++);
  return `#${String(numbers.get(key)).padStart(3, "0")}`;
}

export function addInvite(from, text) {
  const at = Date.now();
  const invites = getState().invites.filter((i) => i.from !== from);
  setState({ invites: [...invites, { from, text, at }] });
  setTimeout(() => removeInvite(from, at), INVITE_LIFETIME);
}

function removeInvite(from, at) {
  setState({ invites: getState().invites.filter((i) => i.from !== from || (at && i.at !== at)) });
}

/** The server's {"type": "invite_closed"}: that challenge was answered (maybe by typing /accept), or its sender left. */
export function closeInvite(from) {
  removeInvite(from);
}

// ----- 📨 group invites: they last a day, so they stay on the rail (after a reload too) until answered or over

const nowSeconds = () => Date.now() / 1000;
const MAX_TIMER_MS = 2 ** 31 - 1;   // setTimeout can't wait longer (about 24.8 days)

const inviteTimers = new Map();   // group key -> the timer that takes its ticket down (one per group)

export function addGroupInvite(invite) {
  if (invite.expires <= nowSeconds()) return;
  setState({ groupInvites: GI.withInvite(getState().groupInvites, invite) });
  clearTimeout(inviteTimers.get(invite.group));   // a new invite to the same group: its old timer goes
  const wait = Math.min(MAX_TIMER_MS, (invite.expires - nowSeconds()) * 1000 + 500);
  inviteTimers.set(invite.group, setTimeout(() => {
    inviteTimers.delete(invite.group);
    setState({ groupInvites: GI.stillOpen(getState().groupInvites, nowSeconds()) });
  }, wait));
}

/** {"type": "invite_closed", "group": key}: answered (here, by typing, or on another device), or over. */
export function closeGroupInvite(group) {
  clearTimeout(inviteTimers.get(group));
  inviteTimers.delete(group);
  setState({ groupInvites: GI.withoutInvite(getState().groupInvites, group) });
}

function groupInviteTicket(invite) {
  const answer = (word) => async () => {
    closeGroupInvite(invite.group);
    const error = await sendLine(GI.answerLine(invite, word));
    if (error) addGroupInvite(invite);   // didn't get through: the ticket comes back
  };
  return ticket(`group-invite:${invite.group}`, {
    title: `📨 ${invite.from} invites you`,
    lines: [el("strong", { dir: "auto", text: invite.name }), GI.timeLeft(invite.expires, nowSeconds())],
    actions: [
      el("button", { class: "btn btn-primary", type: "button", onclick: answer("accept"), text: "Accept",
        "aria-label": `Accept the invite to ${invite.name}` }),
      el("button", { class: "btn btn-ghost", type: "button", onclick: answer("decline"), text: "Decline",
        "aria-label": `Decline the invite to ${invite.name}` }),
    ],
  });
}

/** 🤝 Someone asked to be your friend (from the friends packet, so it's there after a reload too). */
function friendTicket(name) {
  return ticket(`friend:${name}`, {
    title: `🤝 ${name} wants to be friends`,
    actions: [
      el("button", { class: "btn btn-primary", type: "button", text: "Accept", "aria-label": `Accept ${name}'s friend request`,
        onclick: () => answerRequest(name, "accept") }),
      el("button", { class: "btn btn-ghost", type: "button", text: "Decline", "aria-label": `Decline ${name}'s friend request`,
        onclick: () => answerRequest(name, "decline") }),
    ],
  });
}

function ticket(key, { title, lines = [], actions = [], lit = false, stamp = null, drain = null, onclick = null }) {
  const fresh = !seen.has(key);
  seen.add(key);
  const node = el("article", { class: `ticket${lit ? " lit" : ""}${fresh ? " fresh" : ""}`, "aria-label": title },
    el("div", { class: "ticket-top" },
      onclick
        ? el("button", { class: "ticket-title ticket-open", type: "button", text: title, "aria-label": `${title}: open the game`, onclick })
        : el("p", { class: "ticket-title", text: title }),
      el("span", { class: "ticket-no", text: orderNumber(key) })),
    lines.map((line) => el("p", { class: "ticket-line" }, line)),
    actions.length ? el("div", { class: "ticket-actions" }, actions) : null);
  if (drain) node.append(drain);
  if (stamp) {
    node.append(el("span", { class: `stamp ${stamp}${stamped.has(key) ? "" : " fresh"}`, text: RESULT_TEXT[stamp] }));
    stamped.add(key);
  }
  return node;
}

function drainBar(at) {
  const left = Math.max(0, at + INVITE_LIFETIME - Date.now());
  const bar = el("span");
  bar.style.setProperty("--drain-ms", `${left}ms`);
  bar.style.setProperty("--from", String(left / INVITE_LIFETIME));
  const wrap = el("div", { class: `drain${left < LOW_TIME ? " low" : ""}`, role: "timer", "aria-label": "Time left to accept" }, bar);
  if (left > LOW_TIME) setTimeout(() => wrap.classList.add("low"), left - LOW_TIME);
  return wrap;
}

function inviteTicket(invite) {
  const respond = (verb) => async () => {
    removeInvite(invite.from, invite.at);
    await sendLine(`/${verb} ${invite.from}`);
  };
  const game = /challenges you to (.+?)!/u.exec(invite.text)?.[1] ?? "a game";
  return ticket(`invite:${invite.from}:${invite.at}`, {
    title: `⚔️ ${invite.from} challenges you`,
    lines: [game],
    actions: [
      el("button", { class: "btn btn-primary", type: "button", onclick: respond("accept"), text: "Accept" }),
      el("button", { class: "btn btn-ghost", type: "button", onclick: respond("decline"), text: "Decline" }),
    ],
    drain: drainBar(invite.at),
  });
}

/** The first line of the server's board text, like "❌⭕ Tic-Tac-Toe   Adi vs Noa". */
export function boardHeader(text) {
  return str(text).trim().split("\n")[0].trim();
}

function matchTicket(match, openGame) {
  const s = match.state || {};
  const header = boardHeader(match.text);
  const [title, players = ""] = header.split(/\s{3,}/u);
  const myTurn = Boolean(s.your_turn) && !match.result;
  const waiting = s.game === "math" ? (s.locked_out ? "⏳ Locked out" : "⚡ Answer fast!") : "⏳ Their turn";
  const status = match.result ? "Game over" : s.finished ? "Finishing…" : myTurn ? "👉 Your turn" : waiting;
  return ticket(`match:${match.id}`, {
    title: title || "🎮 Game", lines: [players, el("strong", { text: status })],
    lit: myTurn, stamp: match.result, onclick: openGame,
  });
}

function wordleTicket(wordle, openGame) {
  const s = wordle.state || {};
  const tries = Array.isArray(s.guesses) ? s.guesses.length : 0;
  const done = s.finished || wordle.result;
  return ticket(`wordle:${wordle.id}`, {
    title: "🟩 Wordle",
    lines: [done ? (s.won ? `Solved in ${tries}/6` : "Out of tries") : `Try ${tries + 1} of ${s.max_tries || 6}`],
    stamp: done ? (s.won ? "won" : "lost") : null, onclick: openGame,
  });
}

export function initRail({ openGame }) {
  let shown = null;
  subscribe((state) => {
    const key = [state.invites, state.groupInvites, state.friends?.requests, state.match, state.wordle];
    if (shown && key.every((part, i) => part === shown[i])) return;
    shown = key;
    clear(rail).append(
      ...state.invites.map(inviteTicket),
      ...GI.stillOpen(state.groupInvites, nowSeconds()).map(groupInviteTicket),
      ...(state.friends ? state.friends.requests.map(friendTicket) : []),
      ...(state.match ? [matchTicket(state.match, openGame)] : []),
      ...(state.wordle ? [wordleTicket(state.wordle, openGame)] : []));
  });
}
