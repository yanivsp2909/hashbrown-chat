// 😂 Reactions under a chat message: chips like "👍 2" (click one to add or take back yours), and a small
// "add a reaction" button that opens the six emojis. The server keeps the counts (in history.db) and
// sends {"type": "reactions", "id", "counts"} to the room whenever they change.

import { clear, el } from "./dom.js";
import { send } from "./api.js";

export const EMOJIS = ["👍", "❤️", "😂", "😮", "😢", "🥔"];   // the same list as REACTIONS in chatserver/config.py

const react = (id, emoji) => send({ type: "react", id, emoji });

function chips(id, counts) {
  return Object.entries(counts || {}).filter(([, n]) => n > 0).map(([emoji, n]) =>
    el("button", { class: "reaction", type: "button", "data-emoji": emoji, "aria-label": `${emoji} ${n}, add or take back yours`,
      onclick: () => react(id, emoji) }, `${emoji} ${n}`));
}

function picker(id, toggle) {
  return el("span", { class: "reaction-picker", id: `react-pick-${id}`, hidden: true },
    ...EMOJIS.map((emoji) => el("button", { class: "reaction-pick", type: "button", "aria-label": `React with ${emoji}`,
      onclick: () => { react(id, emoji); toggle.click(); toggle.focus(); } }, emoji)));
}

/** The row under a bubble: the counts, then the add button and its (hidden) emoji picker. */
export function reactionRow(id, counts) {
  const row = el("div", { class: "reactions", "data-reactions-for": String(id) });
  const toggle = el("button", { class: "reaction-add", type: "button", "aria-label": "Add a reaction", "aria-expanded": "false",
    "aria-controls": `react-pick-${id}` });
  toggle.append(el("span", { "aria-hidden": "true", text: "☺︎+" }));
  const choices = picker(id, toggle);
  toggle.addEventListener("click", () => {
    choices.hidden = !choices.hidden;
    toggle.setAttribute("aria-expanded", String(!choices.hidden));
  });
  row.addEventListener("keydown", (event) => {   // Escape closes the emoji choices
    if (event.key === "Escape" && !choices.hidden) {
      toggle.click();
      toggle.focus();
    }
  });
  row.append(el("span", { class: "reaction-chips" }, ...chips(id, counts)), toggle, choices);
  return row;
}

/** {"type": "reactions"} from the server: redraw that message's chips (if it's on screen). */
export function updateReactions(msg) {
  const row = document.querySelector(`[data-reactions-for="${CSS.escape(String(msg.id))}"] .reaction-chips`);
  if (!row) return;
  const focused = row.contains(document.activeElement) ? document.activeElement.dataset.emoji : null;
  clear(row).append(...chips(msg.id, msg.counts));
  const again = focused && row.querySelector(`[data-emoji="${CSS.escape(focused)}"]`);
  if (again) again.focus();   // a keyboard user who toggled a chip stays on it
}
