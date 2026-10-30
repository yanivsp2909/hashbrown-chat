// ⌨️ "Noa is typing…": while you type a message (not a /command) we tell the server at most every few
// seconds, and we show who else in this room is typing. The line is not read out to screen readers
// (it would interrupt them all the time); it disappears when their message arrives.

import { $ } from "./dom.js";
import { send } from "./api.js";

const SEND_EVERY = 3000;   // ms between two "I'm typing" packets
const SHOW_FOR = 4000;     // ms someone stays "typing" after their last packet
let lastSent = 0;
let typers = {};           // name -> until when (ms)

function draw() {
  const now = Date.now();
  typers = Object.fromEntries(Object.entries(typers).filter(([, until]) => until > now));
  const names = Object.keys(typers);
  const line = $("typing-line");
  line.textContent = names.length === 1 ? `${names[0]} is typing…`
    : names.length === 2 ? `${names[0]} and ${names[1]} are typing…`
      : names.length ? "Several people are typing…" : "";
  line.hidden = !names.length;
}

export function someoneTyping(name) {
  if (!name) return;
  typers = { ...typers, [name]: Date.now() + SHOW_FOR };
  draw();
}

export function stoppedTyping(name) {
  if (!(name in typers)) return;
  const { [name]: _gone, ...rest } = typers;
  typers = rest;
  draw();
}

export function initTyping() {
  $("input").addEventListener("input", (event) => {
    const text = event.target.value;
    if (!text.trim() || text.startsWith("/") || Date.now() - lastSent < SEND_EVERY) return;
    lastSent = Date.now();
    send({ type: "typing" });
  });
  setInterval(draw, 1000);
}
