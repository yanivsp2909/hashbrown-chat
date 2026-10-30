// Small banners at the top of the chat.
//   📌 the room's pinned topic: {"type": "topic", "room", "text"} (the server sends one on every room switch,
//      an empty text means no topic)
//   🧪 the network lab: the host made the network worse on purpose (lag / loss in the server window), so
//      everyone sees why messages are slow. {"type": "lab", lag_ms, loss_percent}

import { $ } from "./dom.js";

const whole = (n) => (Number.isInteger(n) && n > 0 ? n : 0);

/** "🧪 Network lab: 300 ms lag, 20% loss", or "" when the lab is off. */
export function labText(msg) {
  const parts = [whole(msg.lag_ms) && `${whole(msg.lag_ms)} ms lag`, whole(msg.loss_percent) && `${whole(msg.loss_percent)}% loss`];
  const on = parts.filter(Boolean);
  return on.length ? `🧪 Network lab: ${on.join(", ")}` : "";
}

/** 📌 Show (or hide) this room's topic. (Other rooms' topics never get here: rooms.js filters them.) */
export function showTopic(msg) {
  const banner = $("topic-banner");
  const text = typeof msg.text === "string" ? msg.text.trim() : "";
  banner.textContent = text ? `📌 ${text}` : "";
  banner.hidden = !text;
}

/** Show (or hide) the lab banner. After a reload the replay runs through every change: the last one wins. */
export function showLab(msg) {
  const banner = $("lab-banner");
  banner.textContent = labText(msg);
  banner.hidden = !banner.textContent;
}
