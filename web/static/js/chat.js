// 💬 The message list. Everything is built with el(), so server text is always plain text.

import { $, clear, el, str } from "./dom.js";
import { isHashbrown } from "./patterns.js";

const MAX_MESSAGES = 500;
const NEAR_BOTTOM = 120;   // px: closer than this to the bottom counts as "reading the latest"
const KIND_CLASSES = new Set(["system", "error", "private", "money", "event", "game", "help", "board"]);

const list = $("messages");
const jumpDown = $("jump-down");
let unseen = 0;

jumpDown.addEventListener("click", () => scrollToBottom());
list.addEventListener("scroll", () => {
  if (isNearBottom()) jumpDown.hidden = true;
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) setUnseen(0);
});

function isNearBottom() {
  return list.scrollHeight - list.scrollTop - list.clientHeight < NEAR_BOTTOM;
}

function scrollToBottom() {
  list.scrollTop = list.scrollHeight;
  jumpDown.hidden = true;
}

function setUnseen(count) {
  unseen = count;
  document.title = count ? `(${count}) Hashbrown Chat 🥔` : "Hashbrown Chat 🥔";
}

/** Same name, same color, on every screen: a tiny string hash picks one of 8 name colors. */
export function nameClass(name) {
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.codePointAt(0)) >>> 0;
  return `name-${hash % 8}`;
}

function add(node, { live = true } = {}) {
  const follow = isNearBottom();
  if (live) node.classList.add("enter");
  list.append(node);
  while (list.childElementCount > MAX_MESSAGES) {
    const oldest = list.firstElementChild;
    const blob = oldest.querySelector('a[href^="blob:"]');
    if (blob) URL.revokeObjectURL(blob.href);  // free the file's memory along with its message
    oldest.remove();
  }
  if (follow) scrollToBottom();
  else if (live) jumpDown.hidden = false;
  if (live && document.hidden) setUnseen(unseen + 1);
  return node;
}

function chatNode(msg, { mine = false, old = false } = {}) {
  const name = str(msg.name, "?");
  const badge = str(msg.badge);
  const time = el("span", { class: "time", text: str(msg.time) });
  if (isHashbrown(msg)) {
    return el("li", { class: "msg hashbrown" },
      el("span", { class: "avatar", "aria-hidden": "true", text: "🥔" }),
      el("div", { class: "chat-body" },
        el("p", {}, el("span", { class: "who", text: "Hashbrown" }), time),
        el("p", { class: "chat-text", dir: "auto", text: str(msg.text) })));
  }
  const who = el("span", { class: `who ${nameClass(name)}` }, badge ? el("span", { class: "badge", text: badge }) : null, name);
  const classes = ["msg", "chat-line", mine && "mine", old && "old", msg.action && "action"].filter(Boolean).join(" ");
  const body = msg.action
    ? el("p", { class: "chat-text", dir: "auto" }, "* ", who, str(msg.text))
    : el("p", { class: "chat-text", dir: "auto" }, who, str(msg.text));
  return el("li", { class: classes }, time, el("div", { class: "chat-body" }, body));
}

export function addChat(msg, { live, mine }) {
  add(chatNode(msg, { mine }), { live });
}

/** A server notice. `actions` are extra buttons, like Accept / Decline on a challenge. */
export function addNotice(kind, text, { live = true, lit = false, actions = [] } = {}) {
  const safeKind = KIND_CLASSES.has(kind) ? kind : "system";
  const node = el("li", { class: `msg notice ${safeKind}${lit ? " lit" : ""}`, dir: "auto" }, str(text));
  if (actions.length) node.append(el("div", { class: "actions" }, actions));
  return add(node, { live });
}

export function addHistory(room, messages, { live, isMine }) {
  add(el("li", { class: "msg room-divider", text: `📍 You're in ${room}` }), { live });
  if (!Array.isArray(messages) || !messages.length) return;
  for (const msg of messages) {
    if (msg && typeof msg === "object") add(chatNode(msg, { old: true, mine: isMine(str(msg.name)) }), { live: false });
  }
  add(el("li", { class: "msg room-divider", text: "now" }), { live: false });
}

export function addFile({ from, filename, size, url }, { live }) {
  const kb = `${Math.max(1, Math.round(size / 1024))} KB`;
  add(el("li", { class: "msg file-msg" },
    el("span", { "aria-hidden": "true", text: "📥" }),
    el("div", { class: "file-meta" },
      el("p", {}, el("strong", { text: from }), " sent you a file"),
      el("p", { class: "file-size" }, filename, " · ", kb)),
    el("a", { class: "btn btn-primary", href: url, download: filename, text: "Download" })), { live });
}

/** Lit private messages stay highlighted until you send something. */
export function clearLit() {
  for (const node of list.querySelectorAll(".notice.lit")) node.classList.remove("lit");
}

export function clearMessages() {
  clear(list);
  jumpDown.hidden = true;
  setUnseen(0);
}
