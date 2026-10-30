// 🔴🔵 Damka: click one of your pieces, then a dark square, to send a move like "c3 d4".
// board[0] is row 8 (the top). Blue moves down, so for blue the board is turned around
// and your pieces are always at the bottom.

import { el, str } from "../dom.js";

const FILES = "abcdefgh";
const COLOR_NAMES = { r: "red", b: "blue" };

function readBoard(raw) {
  const rows = Array.isArray(raw) ? raw : [];
  return Array.from({ length: 8 }, (_, r) => Array.from({ length: 8 }, (_, c) => {
    const piece = Array.isArray(rows[r]) ? rows[r][c] : null;
    return ["r", "R", "b", "B"].includes(piece) ? piece : null;
  }));
}

const squareName = (r, c) => `${FILES[c]}${8 - r}`;

export function renderDamka(s, send) {
  const board = readBoard(s.board);
  const you = s.you === "b" ? "b" : "r";
  const flip = you === "b";
  const mustJump = str(s.must_jump_from) || null;
  const myTurn = Boolean(s.your_turn) && !s.finished;
  let selected = myTurn ? mustJump : null;
  const wrap = el("div", { class: "damka-wrap" });

  function square(r, c) {
    const piece = board[r][c];
    const name = squareName(r, c);
    const dark = (r + c) % 2 === 1;
    const mine = Boolean(piece) && piece.toLowerCase() === you;
    const canPick = myTurn && mine && (!mustJump || name === mustJump);
    const isTarget = Boolean(selected) && dark && !piece;
    const owner = piece ? `${mine ? "your" : "their"} ${COLOR_NAMES[piece.toLowerCase()]}${piece === piece.toUpperCase() ? " king" : " piece"}` : "empty";
    const classes = ["sq", dark && "dark", mine && "mine", name === selected && "selected",
      isTarget && "target", myTurn && name === mustJump && "must"].filter(Boolean).join(" ");
    return el("button", {
      class: classes, type: "button", disabled: !(canPick || isTarget), "aria-label": `${name}, ${owner}`, "data-key": `sq-${name}`,
      "aria-pressed": canPick ? String(name === selected) : undefined,
      onclick: () => {
        if (canPick) {
          selected = name === selected && !mustJump ? null : name;
          draw();
        } else if (isTarget) {
          send(`${selected} ${name}`);
          selected = null;
          draw();
        }
      },
    }, piece ? el("span", { class: `piece ${piece.toLowerCase()}`, "aria-hidden": "true", text: piece === piece.toUpperCase() ? "👑" : "" }) : null);
  }

  function draw() {
    const focused = wrap.contains(document.activeElement) ? document.activeElement.dataset.key : null;
    const order = [...Array(8).keys()].map((i) => (flip ? 7 - i : i));
    const grid = el("div", { class: "damka", role: "group", "aria-label": `Damka board, you are ${COLOR_NAMES[you]}` });
    for (const r of order) for (const c of order) grid.append(square(r, c));
    wrap.replaceChildren(
      el("div", { class: "ranks", "aria-hidden": "true" }, order.map((r) => el("span", { text: String(8 - r) }))),
      grid,
      el("div", { class: "files", "aria-hidden": "true" }, order.map((c) => el("span", { text: FILES[c] }))));
    // Keep keyboard focus on the square you just used (or the piece you picked)
    const again = focused && wrap.querySelector(`[data-key="${focused}"]`);
    const fallback = selected && wrap.querySelector(`[data-key="sq-${selected}"]`);
    if (focused) (again && !again.disabled ? again : fallback)?.focus();
  }

  draw();
  return wrap;
}
