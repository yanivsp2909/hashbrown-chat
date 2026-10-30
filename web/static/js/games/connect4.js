// 🔴🟡 Connect 4: each column is one button; click it to drop your piece there (sends 1-7).

import { el, str } from "../dom.js";

const ROWS = 6;
const COLS = 7;

export function renderConnect4(s, send) {
  const cells = Array.isArray(s.cells) ? s.cells : [];
  const columns = Array.from({ length: COLS }, (_, col) => {
    const pieces = Array.from({ length: ROWS }, (_, row) => str(cells[row * COLS + col]));
    const used = pieces.filter(Boolean).length;
    const open = Boolean(s.your_turn) && !s.finished && used < ROWS;
    return el("button", {
      type: "button", class: "c4-col", disabled: !open, onclick: () => send(String(col + 1)), "data-key": `c4-${col}`,
      "aria-label": `Column ${col + 1}, ${used} piece${used === 1 ? "" : "s"}${used === ROWS ? ", full" : ""}`,
    }, ...pieces.map((piece) => el("span", { class: "c4-cell", "aria-hidden": "true", text: piece || "" })));
  });
  return el("div", { class: "c4", role: "group", "aria-label": "Connect 4 board" }, columns);
}
