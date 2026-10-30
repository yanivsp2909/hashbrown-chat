// ❌⭕ Tic-Tac-Toe: click a square to send its number (1-9).

import { el, str } from "../dom.js";

export function renderTtt(s, send, prev) {
  const cells = Array.isArray(s.cells) ? s.cells : [];
  const before = Array.isArray(prev?.cells) ? prev.cells : [];
  const squares = Array.from({ length: 9 }, (_, i) => {
    const mark = str(cells[i]);
    const open = Boolean(s.your_turn) && !s.finished && !mark;
    return el("button", {
      type: "button", disabled: !open, onclick: () => send(String(i + 1)), "data-key": `ttt-${i}`,
      "aria-label": `Square ${i + 1}, ${mark || "empty"}`,
    }, mark
      ? el("span", { class: before[i] ? "" : "mark", text: mark })
      : el("span", { class: "hint", "aria-hidden": "true", text: open ? String(i + 1) : "" }));
  });
  return el("div", { class: "ttt", role: "group", "aria-label": "Tic-Tac-Toe board" }, squares);
}
