// 📨 What to do with each message from the chat server.

import { el, str } from "./dom.js";
import { sendLine } from "./api.js";
import { getState, setState } from "./store.js";
import * as chat from "./chat.js";
import { receive } from "./files.js";
import { addInvite } from "./rail.js";
import { inviteFrom, isAlreadyOnline, isWordleOver, matchResult, parseHelp, renamed, welcomeNick } from "./patterns.js";
import { clearPasswords, showLoginError } from "./login.js";
import { noteTarget } from "./games/panel.js";

const MAX_NAMES = 60;
const NICK_KEY = "hashbrown.nick";
let quietHelp = 0;        // live /help replies to swallow: the ones we asked for to fill autocomplete
let replayHelpHidden = true;  // during a replay, the first /help after a login was our quiet one
let gameCount = 0;
let pendingUsername = "";

export const setPendingUsername = (name) => { pendingUsername = name; };

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
  sendLine("/help").then((error) => { if (error) quietHelp = Math.max(0, quietHelp - 1); });
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
    const hint = isAlreadyOnline(text) ? " If you just closed a tab, log out there or wait about 90 seconds." : "";
    showLoginError(text + hint);
    return;
  }
  clearPasswords();
  setState({ screen: "chat" });
  setNick(welcomeNick(text) || pendingUsername);
  if (live) requestCommands(sendLine);
  else replayHelpHidden = false;
}

function onBoard(msg, text) {
  const s = msg.state && typeof msg.state === "object" ? msg.state : null;
  if (s?.game === "wordle") {
    const old = getState().wordle;
    const id = old && !old.state?.finished ? old.id : ++gameCount;
    return setState({ wordle: { id, state: s, text, result: null } });
  }
  const old = getState().match;
  const id = old && !old.result && !old.state?.finished ? old.id : ++gameCount;
  setState({ match: { id, state: s, text, result: null } });
}

function onServerText(msg, live) {
  const kind = str(msg.kind, "system");
  const text = str(msg.text);
  if (kind === "help") {
    setState({ commands: parseHelp(text) });
    if (live && quietHelp > 0) {
      quietHelp -= 1;
      return;
    }
    if (!live && !replayHelpHidden) {
      replayHelpHidden = true;
      return;
    }
  }
  if (kind === "board") return onBoard(msg, text);

  const slot = kind === "error" && live ? noteTarget() : null;
  if (slot && getState()[slot]) setState({ [slot]: { ...getState()[slot], note: text } });
  const result = matchResult(kind, text);
  const { match } = getState();
  if (result && match && !match.result) setState({ match: { ...match, result } });
  const { wordle } = getState();
  if (isWordleOver(text) && wordle) setState({ wordle: { ...wordle, result: text, state: wordle.state && { ...wordle.state, finished: true } } });
  const rename = renamed(text);
  if (rename && rename[0] === getState().nick) setNick(rename[1]);
  const challenger = kind === "event" ? inviteFrom(text) : null;
  if (challenger && live) addInvite(challenger, text);
  const actions = challenger ? [  // also here, so a reloaded tab can still answer
    el("button", { class: "btn btn-primary", type: "button", text: "Accept", onclick: () => sendLine(`/accept ${challenger}`) }),
    el("button", { class: "btn btn-ghost", type: "button", text: "Decline", onclick: () => sendLine(`/decline ${challenger}`) }),
  ] : [];
  chat.addNotice(kind, text, { live, lit: kind === "private" && live, actions });
}

export function handleMessage(msg, live, sendLine) {
  switch (msg.type) {
    case "auth_result":
      return onAuthResult(msg, live, sendLine);
    case "msg":
      return onServerText(msg, live);
    case "chat": {
      const name = str(msg.name);
      remember(name);
      return chat.addChat(msg, { live, mine: name === getState().nick });
    }
    case "history":
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
