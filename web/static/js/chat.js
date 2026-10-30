// 💬 The message list. Everything is built with el(), so server text is always plain text.
//
// Every message has one of four shapes:
//   chat  a bubble with a header (name, badge, time). Lines from the same person close together
//         share one header; your own bubbles sit on the right.
//   card  a server notice (tokens, errors, private messages...) with a small header and its colour.
//   list  a card whose rows came in as indented lines (/groups, /top, /help...).
//   meta  a short grey line in the middle ("👋 Noa joined the chat").

import { $, clear, el, initial, nameClass, str } from "./dom.js";
import { hashbrownPrivate, isHashbrown, parsePrivate } from "./patterns.js";
import { reactionRow } from "./reactions.js";

const MAX_MESSAGES = 500;
const NEAR_BOTTOM = 80;     // px: closer than this to the bottom counts as "reading the latest"
const GROUP_MINUTES = 5;    // lines from one person this close together share a header
const ROW = /^ {2,}\S/u;     // in a server list, rows start with two (or more) spaces
const HEBREW = /[\u0590-\u05ff]/u;
const THINKING_MS = 2 * 60 * 1000;   // a "thinking" notice nobody replaced is removed after this long
const LABELS = {            // the header of each kind of server notice
  system: "Info", error: "Oops", private: "Private", money: "Tokens",
  event: "Heads up", game: "Game", help: "Commands", board: "Board",
};

const list = $("messages");
const jumpDown = $("jump-down");
const jumpLabel = $("jump-label");
let pinned = true;      // following the newest message?
let unseen = 0;         // new messages while you were scrolled up
let unread = 0;         // new messages while the tab was hidden (shown in the tab title)
let lastChat = null;    // {name, minutes} of the bubble right above, for grouping
let lastTop = 0;        // scroll position at the last scroll event
let liveTimer = null;

jumpDown.addEventListener("click", () => {
  followLatest();
  $("input").focus({ preventScroll: true });   // the button disappears: don't leave focus nowhere
});
list.addEventListener("scroll", () => {
  const top = list.scrollTop;
  if (isNearBottom()) pinned = true;
  // Only you scrolling UP stops the following. Text re-wrapping when the game column or a
  // ticket appears also moves the bottom away, but that must not count as "reading older stuff".
  else if (top < lastTop - 1) pinned = false;
  lastTop = top;
  if (pinned) hideJump();
});
// The list changes height when tickets, the game column or a phone keyboard come and go.
// If you were reading the newest message, keep it in view.
new ResizeObserver(() => {
  if (pinned) scrollToBottom();
}).observe(list);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) setUnread(0);
});

function isNearBottom() {
  return list.scrollHeight - list.scrollTop - list.clientHeight < NEAR_BOTTOM;
}

function scrollToBottom() {
  list.scrollTop = list.scrollHeight;
  lastTop = list.scrollTop;
}

function hideJump() {
  unseen = 0;
  jumpDown.hidden = true;
}

/** Jump to the newest message and keep following (after you send something, for example). */
export function followLatest() {
  pinned = true;
  scrollToBottom();
  hideJump();
}

function setUnread(count) {
  unread = count;
  document.title = count ? `(${count}) Hashbrown Chat 🥔` : "Hashbrown Chat 🥔";
}

/** A paragraph of server text: its own direction, and Hebrew is marked so screen readers switch voice. */
function textPara(cls, text) {
  return el("p", { class: cls, dir: "auto", lang: HEBREW.test(text) ? "he" : null, text });
}

/** Old messages (a reload's replay, a room's history) arrive in a burst: don't read them all out. */
function quietly() {
  list.setAttribute("aria-live", "off");
  clearTimeout(liveTimer);
  liveTimer = setTimeout(() => list.setAttribute("aria-live", "polite"), 600);
}

function nowTime() {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

function minutesOf(time) {
  const match = /^(\d{1,2}):(\d{2})$/u.exec(time);
  return match ? Number(match[1]) * 60 + Number(match[2]) : null;
}

function add(node, { live = true } = {}) {
  if (live) node.classList.add("enter");
  else quietly();
  list.append(node);
  while (list.childElementCount > MAX_MESSAGES) {
    const oldest = list.firstElementChild;
    const blob = oldest.querySelector('a[href^="blob:"]');
    if (blob) URL.revokeObjectURL(blob.href);  // free the file's memory along with its message
    oldest.remove();
    if (!pinned) lastTop = list.scrollTop;   // the browser kept your place; remember the new position
  }
  if (pinned) scrollToBottom();
  else if (live) {
    unseen += 1;
    jumpLabel.textContent = unseen === 1 ? "1 new message" : `${unseen} new messages`;
    jumpDown.hidden = false;
  }
  if (live && document.hidden) setUnread(unread + 1);
  return node;
}

/** Anything that isn't a chat bubble starts a new group. */
function addOther(node, options) {
  lastChat = null;
  return add(node, options);
}

// ---------------------------------------------------------------- chat bubbles

function avatar(name, bot) {
  if (bot) return el("img", { class: "avatar avatar-bot", src: "/logo.svg", alt: "", width: "32", height: "32" });
  return el("span", { class: `avatar ${nameClass(name)}`, "aria-hidden": "true", text: initial(name) });
}

function chatNode(msg, { mine = false, old = false } = {}) {
  const name = str(msg.name, "?");
  const badge = str(msg.badge);
  const time = str(msg.time);
  const bot = isHashbrown(msg);
  const minutes = minutesOf(time);
  const grouped = Boolean(lastChat && lastChat.name === name && minutes !== null && lastChat.minutes !== null
    && (minutes - lastChat.minutes + 1440) % 1440 <= GROUP_MINUTES);
  lastChat = { name, minutes };

  // In a group only the first bubble shows the header; the others keep just the name, for screen readers
  const head = grouped
    ? el("p", { class: "msg-head visually-hidden", text: mine ? "You" : name })
    : el("p", { class: "msg-head" },
      el("span", { class: `who${bot || mine ? "" : ` ${nameClass(name)}`}`, text: mine ? "You" : name }),
      badge && !bot ? el("span", { class: "badge", text: badge }) : null,
      bot ? el("span", { class: "tag", text: "AI" }) : null,
      el("span", { class: "time", text: time }));
  const text = textPara("msg-text", str(msg.text));
  const classes = ["msg", "chat", mine && "mine", bot && "bot", old && "old", msg.action && "action", grouped && "cont"];
  return el("li", { class: classes.filter(Boolean).join(" ") },
    mine ? null : grouped ? el("span", { class: "avatar-gap" }) : avatar(name, bot),
    el("div", { class: "bubble" }, head, text,
      Number.isInteger(msg.id) ? reactionRow(msg.id, msg.reactions) : null));   // 😂 only stored messages have an id
}

export function addChat(msg, { live, mine }) {
  const bubble = msg.stream_id ? findStream(str(msg.stream_id)) : null;
  if (bubble) {   // the final text of an answer that was streaming: it takes the place of the live bubble
    bubble.querySelector(".msg-text").textContent = str(msg.text);
    delete bubble.dataset.streamId;
    return;
  }
  add(chatNode(msg, { mine }), { live });
}

// ---------------------------------------------------------------- Hashbrown typing live

function findStream(streamId) {
  return [...list.querySelectorAll("[data-stream-id]")].find((node) => node.dataset.streamId === streamId) || null;
}

/** A piece of Hashbrown's answer: the first one makes the live bubble, the next ones add to it. */
export function addStreamPiece(msg, { live }) {
  const streamId = str(msg.stream_id);
  let bubble = findStream(streamId);
  if (!bubble) {
    bubble = add(chatNode({ name: "Hashbrown", badge: str(msg.badge), time: str(msg.time), text: "" }), { live });
    bubble.dataset.streamId = streamId;
    // If the final message never comes (the server died), don't leave a half answer forever
    setTimeout(() => { if (bubble.dataset.streamId) bubble.remove(); }, THINKING_MS);
  }
  bubble.querySelector(".msg-text").textContent += str(msg.append);
  if (pinned) scrollToBottom();
}

/** Remove the live bubble of an answer that failed (or that arrives as a private card instead). */
export function removeStream(streamId) {
  findStream(streamId)?.remove();
}

/** You changed rooms: half-written answers from the old room won't get their ending here, so drop them. */
export function removeAllStreams() {
  for (const node of list.querySelectorAll("[data-stream-id]")) node.remove();
}

// ---------------------------------------------------------------- server notices

function cardHead(label, time) {
  return el("p", { class: "card-head" }, el("span", { class: "card-label", text: label }),
    time ? el("span", { class: "time", text: time }) : null);
}

/** Lines that start with two spaces are rows: "  🥇 Noa  250 🪙" -> ["🥇 Noa", "250 🪙"]. */
function isList(text) {
  return text.split("\n").filter((line) => ROW.test(line)).length >= 2;
}

function listBody(text) {
  const [first, ...rest] = text.split("\n");
  const parts = [textPara("list-title", first)];
  let rows = null;
  for (const line of rest) {
    if (!line.trim()) continue;
    if (ROW.test(line)) {
      if (!rows) parts.push(rows = el("ul", { class: "list-rows" }));
      rows.append(el("li", { class: "list-row" },
        line.trim().split(/\s{2,}/u).map((cell) => el("span", { class: "cell", dir: "auto", text: cell }))));
    } else {
      rows = null;
      parts.push(textPara("list-sub", line.trim()));
    }
  }
  return parts;
}

function privateNode(pm, live) {
  const who = pm.from === "you" ? `You → ${pm.to}` : `${pm.from} → you`;
  return el("li", { class: "msg card kind-private" },
    cardHead(`💌 ${who}`, pm.time),
    textPara("card-text private-text", pm.text));
}

/** A server notice. `actions` are extra buttons, like Accept / Decline on a challenge;
 *  `label` replaces the kind's usual header word (like "Game over" for a loss). */
export function addNotice(kind, text, { live = true, lit = false, actions = [], label = "", tempId = "" } = {}) {
  const safeKind = Object.hasOwn(LABELS, kind) ? kind : "system";
  let body = str(text);
  const time = live ? nowTime() : "";
  const pm = safeKind === "private" ? parsePrivate(body) : null;
  const answer = safeKind === "private" && !pm ? hashbrownPrivate(body) : null;
  if (answer !== null) {   // Hashbrown's private /ask answer: a card that reads as Hashbrown
    body = answer;
    label = "🥔 Only you";
  }
  let node;
  if (pm) {
    node = privateNode(pm, live);
  } else if (isList(body)) {
    node = el("li", { class: `msg card list kind-${safeKind}` }, cardHead(label || LABELS[safeKind], time), listBody(body));
  } else if (safeKind === "system" && !body.includes("\n") && !actions.length) {
    node = el("li", { class: "msg meta", dir: "auto", lang: HEBREW.test(body) ? "he" : null, text: body });
  } else {
    node = el("li", { class: `msg card kind-${safeKind}` },
      cardHead(label || LABELS[safeKind], time), textPara("card-text", body));
  }
  if (lit) node.classList.add("lit");
  if (actions.length) node.append(el("div", { class: "actions" }, actions));
  if (tempId) {   // a temporary notice ("Hashbrown is thinking..."): the answer removes it, or the timer does
    node.dataset.tempId = tempId;
    setTimeout(() => node.remove(), THINKING_MS);
  }
  return addOther(node, { live });
}

/** Remove the temporary notice that a new message replaces (its data-temp-id matches). */
export function removeTemp(tempId) {
  for (const node of list.querySelectorAll("[data-temp-id]")) {
    if (node.dataset.tempId === tempId) node.remove();
  }
}

export function addHistory(room, messages, { live, isMine }) {
  addOther(el("li", { class: "msg room-divider", text: `📍 You're in ${room}` }), { live });
  if (!Array.isArray(messages) || !messages.length) return;
  for (const msg of messages) {
    if (msg && typeof msg === "object") add(chatNode(msg, { old: true, mine: isMine(str(msg.name)) }), { live: false });
  }
  addOther(el("li", { class: "msg room-divider", text: "now" }), { live: false });
}

function fileCard({ from, filename, size, url }, live) {
  const kb = `${Math.max(1, Math.round(size / 1024))} KB`;
  return el("li", { class: "msg card kind-file" },
    cardHead("📥 File", live ? nowTime() : ""),
    el("div", { class: "file-row-msg" },
      el("div", { class: "file-meta" },
        el("p", {}, el("strong", { text: from }), " sent you a file"),
        el("p", { class: "file-size" }, el("span", { dir: "auto", text: filename }), " · ", kb)),
      el("a", { class: "btn btn-primary", href: url, download: filename, text: "Download" })));
}

export function addFile(file, { live }) {
  addOther(fileCard(file, live), { live });
}

// ----- 📦 big files: a card with a progress bar while the pieces come and go

const transferCard = (id) => list.querySelector(`[data-transfer="${CSS.escape(id)}"]`);

export function addTransferCard(id, label, total) {
  addOther(el("li", { class: "msg card kind-file", "data-transfer": id },
    cardHead("📦 File", nowTime()),
    el("p", { class: "transfer-label", dir: "auto", text: label }),
    el("progress", { class: "transfer-bar", max: String(total), value: "0", "aria-label": label })));
}

export function setTransferProgress(id, done, total) {
  const bar = transferCard(id)?.querySelector("progress");
  if (bar) {
    bar.value = done;
    bar.setAttribute("aria-valuetext", `${Math.round((done / total) * 100)}%`);
  }
}

/** Finished: the card becomes a normal file card (file) or says what happened (text). */
export function endTransferCard(id, { file = null, text = "" } = {}) {
  const card = transferCard(id);
  if (!card) return;
  if (file) card.replaceWith(fileCard(file, true));
  else clear(card).append(cardHead("📦 File", nowTime()), textPara("card-text", text));
}

/** Lit private messages stay highlighted until you send something. */
export function clearLit() {
  for (const node of list.querySelectorAll(".msg.lit")) node.classList.remove("lit");
}

export function clearMessages() {
  clear(list);
  lastChat = null;
  pinned = true;
  hideJump();
  setUnread(0);
}
