// ⌨️ "Noa is typing…": the moment you start typing a message (not a /command) we tell the server, then
// refresh it at most every 2 seconds while you keep typing, and say "stopped" when you send or empty the box.
// We show who else in this room is typing until their message or "stopped" arrives, or nothing came for
// SHOW_FOR. The line is not read out to screen readers (it would interrupt them all the time).

import { $ } from "./dom.js";
import { send } from "./api.js";

const REFRESH_EVERY = 2000;   // ms between two "still typing" packets
const SHOW_FOR = 4000;        // ms someone stays "typing" after their last packet
let typingNow = false;        // did we tell the server we're typing (and not "stopped" since)?
let lastSent = 0;
let typers = {};              // name -> until when (ms)
let hideTimer = null;

function draw() {
  const now = Date.now();
  typers = Object.fromEntries(Object.entries(typers).filter(([, until]) => until > now));
  const names = Object.keys(typers);
  const line = $("typing-line");
  line.textContent = names.length === 1 ? `${names[0]} is typing…`
    : names.length === 2 ? `${names[0]} and ${names[1]} are typing…`
      : names.length ? "Several people are typing…" : "";
  line.hidden = !names.length;
  clearTimeout(hideTimer);   // redraw exactly when the next person runs out of time
  if (names.length) hideTimer = setTimeout(draw, Math.min(...Object.values(typers)) - now + 10);
}

function someoneTyping(name) {
  if (!name) return;
  typers = { ...typers, [name]: Date.now() + SHOW_FOR };
  draw();
}

/** A {"type": "typing"} packet. It carries the typer's room (for apps with the "rooms" feature): only people
 * in the room you're looking at count. (No room field: it can only be about this room.) */
export function onTyping(msg, currentRoom) {
  if (typeof msg.room === "string" && currentRoom && msg.room !== currentRoom) return;
  someoneTyping(String(msg.name || ""));
}

/** You switched rooms: the old room's typers aren't typing here. */
export function forgetTypers() {
  typers = {};
  draw();
}

export function stoppedTyping(name) {
  if (!(name in typers)) return;
  const { [name]: _gone, ...rest } = typers;
  typers = rest;
  draw();
}

/** You sent the message (or emptied the box): the others stop seeing you typing right away. */
export function stopMyTyping() {
  if (!typingNow) return;
  typingNow = false;
  send({ type: "typing_stop" });
}

function onInput(text) {
  if (!text.trim() || text.startsWith("/")) return stopMyTyping();
  if (typingNow && Date.now() - lastSent < REFRESH_EVERY) return undefined;
  typingNow = true;   // the first key goes out at once; after that, a refresh every REFRESH_EVERY
  lastSent = Date.now();
  return send({ type: "typing" });
}

export function initTyping() {
  $("input").addEventListener("input", (event) => onInput(event.target.value));
}
