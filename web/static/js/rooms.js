// 💬 The chat switcher: 🌍 the Lobby and every group you're in, like the chat list in a messaging app.
//
// At login we tell the server we understand "rooms". Then it sends the list of our rooms
// ({"type": "rooms"}) and the chat of ALL of them, each message tagged with its room. Messages from
// the room you're looking at are shown as usual; the others only count as unread (and give a preview).
// Clicking a room sends /join (or /lobby): the server moves you and sends that room's history.

import { $, clear, el, str } from "./dom.js";
import { removeStream, removeTemp } from "./chat.js";
import { sendLine } from "./api.js";
import { getState, setState, subscribe } from "./store.js";
import { refresh } from "./online.js";

const PREVIEW = 60;   // characters of the last message shown under a room's name
const ANNOUNCE_AFTER = 2000;   // ms: new messages in other rooms are announced together, not one by one
let waiting = {};               // room title -> new messages not announced yet
let announceTimer = null;

/** One short sentence for screen readers, like "2 new messages in #Potatoes" (never the message text). */
function announce(text) {
  $("chat-live").textContent = text;
}

function announceLater(roomKey) {
  const room = getState().rooms.find((r) => r.key === roomKey);
  const title = room ? (room.key === "lobby" ? "the Lobby" : String(room.title || room.name)) : roomKey;
  waiting = { ...waiting, [title]: (waiting[title] || 0) + 1 };
  clearTimeout(announceTimer);
  announceTimer = setTimeout(() => {
    announce(Object.entries(waiting).map(([t, n]) => `${n} new message${n === 1 ? "" : "s"} in ${t}`).join(", "));
    waiting = {};
  }, ANNOUNCE_AFTER);
}

const previewOf = (msg) => `${String(msg.name ?? "")}: ${String(msg.text ?? "")}`.slice(0, PREVIEW);

/** A packet from the server. Returns true if it belongs to another room: then it's only counted as unread
 *  (and it still clears that room's "thinking..." card or live answer if you were there when it started). */
export function fromOtherRoom(msg, live) {
  const { currentRoom } = getState();
  // (a "history" packet's "room" is the room's title, not its key: it's always for the room you're in)
  if (msg.type === "history" || typeof msg.room !== "string" || !currentRoom || msg.room === currentRoom) return false;
  if (msg.replaces) removeTemp(str(msg.replaces));
  if (msg.stream_id) removeStream(str(msg.stream_id));
  if (msg.type === "chat" && live) {   // a replay after a reload doesn't count twice
    const { unread, previews } = getState();
    setState({
      unread: { ...unread, [msg.room]: (unread[msg.room] || 0) + 1 },
      previews: { ...previews, [msg.room]: previewOf(msg) },
    });
    announceLater(msg.room);
  }
  return true;
}

/** The server's {"type": "rooms"} list. The room you're in has nothing unread. */
export function setRooms(msg) {
  const rooms = Array.isArray(msg.rooms) ? msg.rooms.filter((r) => r && typeof r.key === "string") : [];
  const current = typeof msg.current === "string" ? msg.current : "lobby";
  if (current !== getState().currentRoom) {
    refresh("users");   // the Online list shows where people are
    const room = rooms.find((r) => r.key === current);
    if (getState().currentRoom && room) announce(`Now in ${current === "lobby" ? "the Lobby" : String(room.title || room.name)}`);
  }
  // Only keep counts for rooms still in the list (a new group with an old name starts fresh)
  const keep = (table) => Object.fromEntries(rooms.filter((r) => r.key in table).map((r) => [r.key, table[r.key]]));
  const { unread, previews } = getState();
  setState({ rooms, currentRoom: current, unread: { ...keep(unread), [current]: 0 }, previews: keep(previews) });
}

/** A message from the room you're in: remember it as that room's preview. */
export function notePreview(msg) {
  const { currentRoom, previews } = getState();
  if (msg.type === "chat" && currentRoom) {
    setState({ previews: { ...previews, [currentRoom]: previewOf(msg) } });
  }
}

function roomRow(room, state, onPick) {
  const isHere = room.key === state.currentRoom;
  const unread = state.unread[room.key] || 0;
  const title = room.key === "lobby" ? "Lobby" : String(room.title || room.name);
  return el("li", {},
    el("button", {
      class: `room-btn${isHere ? " here" : ""}${unread ? " has-unread" : ""}`, type: "button",
      "aria-current": isHere ? "true" : null, "data-key": room.key,
      onclick: () => onPick(room),
    },
    el("span", { class: "room-main" },
      el("span", { class: "room-name", dir: "auto" },
        room.key === "lobby" ? el("span", { "aria-hidden": "true", text: "🌍 " }) : null, title),
      el("span", { class: "room-preview", dir: "auto", text: state.previews[room.key] || (room.key === "lobby" ? "everyone" : "") })),
    unread ? el("span", { class: "room-unread", "aria-hidden": "true", text: unread > 99 ? "99+" : String(unread) }) : null,
    unread ? el("span", { class: "visually-hidden", text: `, ${unread} unread message${unread === 1 ? "" : "s"}` }) : null));
}

export function initRooms({ onError, closeDrawer }) {
  const section = $("chats");
  const list = $("chat-list");
  const pick = async (room) => {
    closeDrawer();
    if (room.key === getState().currentRoom) return;
    const error = await sendLine(room.key === "lobby" ? "/lobby" : `/join ${room.name}`);
    if (error) onError(error);
  };
  let drawn = "";
  subscribe((state) => {
    const fingerprint = JSON.stringify([state.rooms, state.currentRoom, state.unread, state.previews]);
    if (fingerprint === drawn) return;
    drawn = fingerprint;
    section.hidden = !state.rooms.length;   // an older server never sends the list: no switcher then
    const focusedKey = list.contains(document.activeElement) ? document.activeElement.dataset.key : null;
    clear(list).append(...state.rooms.map((room) => roomRow(room, state, pick)));
    const again = focusedKey && list.querySelector(`[data-key="${CSS.escape(focusedKey)}"]`);
    if (again) again.focus({ preventScroll: true });
  });
}
