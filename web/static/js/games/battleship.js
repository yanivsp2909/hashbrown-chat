// 🚢 Battleship: two 6x6 seas. "Their sea" is buttons: click a square to fire at it (sends like "c3").
// "Your sea" just shows your ships and where they fired. Their ships are never sent to us.

import { el } from "../dom.js";

const LETTERS = "ABCDEF";
const ICON = { hit: "💥", miss: "⚪", ship: "🚢" };
const WORD = { hit: "hit", miss: "miss", ship: "your ship" };

function sea(title, cells, size, fire) {
  const squares = cells.map((mark, i) => {
    const name = `${LETTERS[Math.floor(i / size)]}${(i % size) + 1}`;
    const label = `${name}, ${WORD[mark] || (fire ? "not fired yet" : "water")}`;
    return fire
      ? el("button", { type: "button", class: `bs-cell ${mark || ""}`, disabled: Boolean(mark) || !fire.open,
        "aria-label": label, "data-key": `bs-${i}`, onclick: () => fire.send(name.toLowerCase()) }, ICON[mark] || "")
      : el("span", { class: `bs-cell ${mark || ""}`, role: "img", "aria-label": label }, ICON[mark] || "");
  });
  return el("section", { class: "bs-sea", "aria-label": title },
    el("h3", { class: "bs-title", text: title }),
    el("div", { class: "bs-grid" }, squares));   // 6 columns, set in games.css (the page allows no inline styles)
}

export function renderBattleship(s, send) {
  const size = Number(s.size) || 6;
  const theirs = Array.isArray(s.theirs) ? s.theirs : [];
  const mine = Array.isArray(s.mine) ? s.mine : [];
  return el("div", { class: "bs" },
    sea("Their sea: fire here", theirs, size, { send, open: Boolean(s.your_turn) && !s.finished }),
    sea("Your sea", mine, size, null));
}
