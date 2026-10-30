// 📨 What to do with each message from the chat server.

import { el, str } from "./dom.js";
import { sendLine } from "./api.js";
import { getState, setState } from "./store.js";
import * as chat from "./chat.js";
import { receive } from "./files.js";
import { addInvite } from "./rail.js";
import { inviteFrom, isPresence, isWordleOver, matchResult, myBalance, parseHelp, parseOnline, renamed, welcomeNick } from "./patterns.js";
import { clearPasswords, showLoginError } from "./login.js";
import { noteTarget } from "./games/panel.js";
import * as online from "./online.js";

const MAX_NAMES = 60;
const NICK_KEY = "hashbrown.nick";
const QUIET_HELP_FOR = 5000;  // ms: a quiet /help that got no answer by then (say, "Slow down!") is forgotten
let quietHelp = 0;        // live /help replies to swallow: the ones we asked for to fill autocomplete
let quietHelpUntil = 0;
let replayHelpHidden = true;  // during a replay, the first /help after a login was our quiet one
let gameCount = 0;
let pendingUsername = "";

export const setPendingUsername = (name) => { pendingUsername = name; };

// What the rest of the app does when something here happens (set by app.js)
let hooks = { onNewGame: () => {}, showOnline: () => {}, showGame: () => {} };
export const setHooks = (more) => { hooks = { ...hooks, ...more }; };

/** The nick survives a reload even when the replay no longer reaches back to the login. */
function setNick(nick) {
  setState({ nick });
  try {
    sessionStorage.setItem(NICK_KEY, nick);
  } catch {
    // storage blocked: the nick just won't survive a reload
  }
}

export function savedNick() {
  try {
    return sessionStorage.getItem(NICK_KEY) || "";
  } catch {
    return "";
  }
}

/** Ask the server for /help without showing the reply: it becomes the autocomplete list. */
export function requestCommands(sendLine) {
  quietHelp += 1;
  quietHelpUntil = Date.now() + QUIET_HELP_FOR;
  sendLine("/help").then((error) => { if (error) quietHelp = Math.max(0, quietHelp - 1); });
}

/** Logged out: forget the quiet /help we were waiting for, so the next login asks again. */
export function resetCommands() {
  quietHelp = 0;
  replayHelpHidden = true;
}

export function needsCommands() {
  return getState().screen === "chat" && !getState().commands.length && quietHelp === 0;
}

function remember(name) {
  const names = getState().knownNames;
  if (!name || names.includes(name) || name === "Hashbrown") return;
  setState({ knownNames: [...names, name].slice(-MAX_NAMES) });
}

function onAuthResult(msg, live, sendLine) {
  const text = str(msg.text);
  if (!msg.ok) {
    if (!live) return;
    showLoginError(text);
    return;
  }
  clearPasswords();
  setState({ screen: "chat" });
  setNick(welcomeNick(text) || pendingUsername);
  if (live) {
    requestCommands(sendLine);
    online.refreshAll();
  } else replayHelpHidden = false;
}

function onBoard(msg, text, live) {
  const s = msg.state && typeof msg.state === "object" ? msg.state : null;
  const slot = s?.game === "wordle" ? "wordle" : "match";
  const old = getState()[slot];
  const sameGame = slot === "wordle" ? old && !old.state?.finished : old && !old.result && !old.state?.finished;
  const id = sameGame ? old.id : ++gameCount;
  setState({ [slot]: { id, state: s, text, result: null } });
  if (!sameGame && live) {
    hooks.onNewGame(slot);
    if (slot === "match") online.refreshAll();   // you're "playing" now, and a bet left your balance
  }
}

function onServerText(msg, live) {
  const kind = str(msg.kind, "system");
  const text = str(msg.text);
  if (kind === "help") {
    setState({ commands: parseHelp(text) });
    if (live && quietHelp > 0) {
      quietHelp -= 1;
      if (Date.now() < quietHelpUntil) return;   // too late means it's the /help you typed: show it
    }
    if (!live && !replayHelpHidden) {
      replayHelpHidden = true;
      return;
    }
  }
  if (kind === "board") return onBoard(msg, text, live);

  // Lists that live in the sidebar instead of the chat
  const people = parseOnline(text);
  if (people) {
    setState({ online: people });
    if (live && online.answerIsYours("users")) hooks.showOnline();  // you asked: show you where it is
    return;
  }
  const balance = kind === "money" ? myBalance(text, getState().nick) : null;
  if (balance !== null) {
    setState({ balance });
    // "🪙 Yaniv has 250 tokens." is shown only if you just typed /balance; the background ones
    // (and every old one in a replay) stay in the sidebar. The welcome "You have..." line always shows.
    const answer = / has \d+ tokens/u.test(text);
    if (answer && !(live && online.answerIsYours("balance"))) return;
  } else if (live && (kind === "money" || kind === "game")) {
    online.refresh("balance");
  }
  if (live && isPresence(text)) online.refresh("users");

  const slot = kind === "error" && live ? noteTarget() : null;
  if (slot && getState()[slot]) setState({ [slot]: { ...getState()[slot], note: text } });
  const result = matchResult(kind, text);
  const { match } = getState();
  if (result && match && !match.result) {
    setState({ match: { ...match, result } });
    if (live) online.refreshAll();
  }
  const { wordle } = getState();
  const wordleOver = isWordleOver(text) && wordle;
  if (wordleOver) setState({ wordle: { ...wordle, result: text, state: wordle.state && { ...wordle.state, finished: true } } });
  const rename = renamed(text);
  if (rename && rename[0] === getState().nick) setNick(rename[1]);
  const challenger = kind === "event" ? inviteFrom(text) : null;
  if (challenger && live) addInvite(challenger, text);
  const actions = challenger && !live ? [  // live, the ticket has the buttons; after a reload there's no ticket
    el("button", { class: "btn btn-primary", type: "button", text: "Accept", onclick: () => sendLine(`/accept ${challenger}`) }),
    el("button", { class: "btn btn-ghost", type: "button", text: "Decline", onclick: () => sendLine(`/decline ${challenger}`) }),
  ] : wordleOver && wordle.state ? [  // the grid lives in the game panel: one click away
    el("button", { class: "btn btn-ghost", type: "button", text: "🟩 Show grid", onclick: () => hooks.showGame() }),
  ] : [];
  chat.addNotice(kind, text, { live, lit: kind === "private" && live, actions, label: result ? "Game over" : "",
    tempId: str(msg.temp_id) });
}

export function handleMessage(msg, live, sendLine) {
  if (msg.replaces) chat.removeTemp(str(msg.replaces));   // the answer takes the place of "thinking..."
  if (msg.stream_id && (msg.failed || (msg.done && msg.type !== "chat"))) chat.removeStream(str(msg.stream_id));
  switch (msg.type) {
    case "stream":
      return msg.done ? undefined : chat.addStreamPiece(msg, { live });
    case "auth_result":
      return onAuthResult(msg, live, sendLine);
    case "msg":
      return onServerText(msg, live);
    case "chat": {
      const name = str(msg.name);
      remember(name);
      return chat.addChat(msg, { live, mine: name === getState().nick });
    }
    case "pong":
      if (typeof msg.t === "number" && live) chat.addNotice("system", `🏓 Pong: ${Math.max(0, Date.now() - msg.t)} ms there and back`);
      return undefined;
    case "history":
      chat.removeAllStreams();
      setState({ room: str(msg.room, "🏠 Lobby") });
      for (const old of Array.isArray(msg.messages) ? msg.messages : []) remember(str(old?.name));
      return chat.addHistory(str(msg.room), msg.messages, { live, isMine: (n) => n === getState().nick });
    case "file": {
      const file = receive(msg);
      if (file.error) return chat.addNotice("error", `📁 ${str(msg.from, "Someone")} ${file.error}`, { live });
      return chat.addFile(file, { live });
    }
    default:
      return undefined;
  }
}
