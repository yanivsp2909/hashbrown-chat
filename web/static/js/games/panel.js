// 🎮 The game panel: draws the board from the server's "state", or its plain text when there's none.

import { $, clear, el, str } from "../dom.js";
import { sendLine } from "../api.js";
import { setState, subscribe } from "../store.js";
import { boardHeader } from "../rail.js";
import { renderTtt } from "./ttt.js";
import { renderDamka } from "./damka.js";
import { renderMath } from "./math.js";
import { renderConnect4 } from "./connect4.js";
import { renderBattleship } from "./battleship.js";
import { renderWordle } from "./wordle.js";

const BOARDS = { ttt: renderTtt, damka: renderDamka, math: renderMath, connect4: renderConnect4, battleship: renderBattleship };
const RESULTS = { won: "🏆 You won!", lost: "💀 You lost", draw: "🤝 Draw" };
const YOU = { ttt: (s) => `You are ${str(s.you)}`, connect4: (s) => `You are ${str(s.you)}`, battleship: () => "Sink all their ships first", damka: (s) => `You are ${s.you === "b" ? "🔵" : "🔴"}, your pieces move up the board` };

const NOTE_WINDOW = 3000;   // ms: a server error this soon after a game action belongs to that game
const body = $("game-body");
let onError = () => {};
let lastAction = { slot: null, at: 0 };

function sender(slot) {
  return async (text) => {
    lastAction = { slot, at: Date.now() };
    const error = await sendLine(text);
    if (error) onError(error);
  };
}
const send = sender("match");
const sendWordle = sender("wordle");

/** Which game ("match" / "wordle") a server error right now is answering, if any. */
export function noteTarget() {
  return Date.now() - lastAction.at < NOTE_WINDOW ? lastAction.slot : null;
}

function turnPill(game, s, result) {
  if (result) return el("p", { class: "turn-pill over", text: RESULTS[result] });
  if (s.finished) return el("p", { class: "turn-pill over", text: "🏁 Game over" });
  if (game === "math") return el("p", { class: `turn-pill${s.locked_out ? "" : " lit"}`, text: s.locked_out ? "⏳ Locked out" : "⚡ Answer fast!" });
  return el("p", { class: `turn-pill${s.your_turn ? " lit" : ""}`, text: s.your_turn ? "👉 Your turn" : "⏳ Their turn" });
}

/** A two-step button: the first click asks "Sure?", the second does it. No pop-up dialogs. */
function confirmButton(label, action) {
  let armed = false;
  const button = el("button", { class: "btn btn-ghost", type: "button", text: label });
  button.addEventListener("click", () => {
    if (armed) return action();
    armed = true;
    button.textContent = "Sure? Click again";
    setTimeout(() => { armed = false; button.textContent = label; }, 3000);
  });
  return button;
}

function textToggle(text) {
  const pre = el("pre", { class: "game-text", hidden: true, text: str(text).trim() });
  const button = el("button", {
    class: "btn btn-ghost", type: "button", "aria-expanded": "false", text: "Show as text",
    onclick: () => {
      pre.hidden = !pre.hidden;
      button.setAttribute("aria-expanded", String(!pre.hidden));
      button.textContent = pre.hidden ? "Show as text" : "Hide text";
    },
  });
  return [button, pre];
}

function matchCard(match, prev) {
  const s = match.state;
  const game = s && BOARDS[s.game] ? s.game : null;
  const [title, players = ""] = boardHeader(match.text).split(/\s{3,}/u);
  const over = Boolean(match.result || s?.finished);
  const [toggle, pre] = textToggle(match.text);
  if (!game) pre.hidden = false;  // no structured state: the server's text is the board
  const foot = el("div", { class: "game-foot" },
    over ? el("button", { class: "btn btn-primary", type: "button", text: "Close", onclick: () => setState({ match: null }) })
      : confirmButton("🏳️ Resign", () => send("/resign")),
    game ? toggle : null);
  return el("section", { class: "game-card", "aria-label": title || "Game" },
    el("header", { class: "game-head" },
      el("h2", { text: title || "🎮 Game" }),
      players ? el("p", { class: "players", text: players }) : null,
      s.spectating ? el("p", { class: "players", text: "👀 Watching (you can't move)" })
        : game && YOU[game] ? el("p", { class: "players", text: YOU[game](s) }) : null,
      game ? turnPill(game, s, match.result) : null),
    game ? el("div", { class: "plate" }, BOARDS[game](s, send, prev?.state)) : null,
    match.note ? el("p", { class: "game-error", text: match.note }) : null,
    pre, foot);
}

function wordleCard(wordle, prev) {
  const s = wordle.state;
  const [toggle, pre] = textToggle(wordle.text);
  const finished = Boolean(s?.finished || wordle.result);
  const foot = el("div", { class: "game-foot" },
    finished ? el("button", { class: "btn btn-ghost", type: "button", text: "Close", onclick: () => setState({ wordle: null }) })
      : confirmButton("🏳️ Give up", () => sendWordle("/giveup")),
    s ? toggle : null);
  if (!s) pre.hidden = false;
  return el("section", { class: "game-card", "aria-label": "Wordle" },
    el("header", { class: "game-head" }, el("h2", { text: "🟩 Wordle" }),
      wordle.result ? el("p", { class: "game-note", text: wordle.result }) : null),
    s ? el("div", { class: "plate auto" }, renderWordle(s, sendWordle, prev?.state, { onNewGame: () => sendWordle("/wordle"), result: wordle.result })) : null,
    wordle.note ? el("p", { class: "game-error", text: wordle.note }) : null,
    pre, foot);
}

function emptyGrill({ focusChallenge }) {
  return el("div", { class: "empty-grill plate" },
    el("span", { class: "big", "aria-hidden": "true", text: "🍳" }),
    el("h2", { text: "Nothing on the grill" }),
    el("p", { text: "Challenge a friend to a 1v1, or play a solo Wordle for tokens." }),
    el("div", { class: "row" },
      el("button", { class: "btn btn-primary", type: "button", text: "⚔️ Challenge", onclick: focusChallenge }),
      el("button", { class: "btn btn-ghost", type: "button", text: "🟩 Wordle", onclick: () => sendWordle("/wordle") })));
}

const finePointer = matchMedia("(pointer: fine)");   // on phones, focusing an input pops the keyboard
const status = $("game-status");

/** Re-draws one slot only when its own game changed, so typing in one game survives moves in the other. */
function renderSlot(slot, game, prev, card) {
  const active = document.activeElement;
  const focusWasHere = slot.contains(active) || active === document.body;
  const key = slot.contains(active) ? active.dataset.key : null;   // e.g. the square you were on
  clear(slot);
  if (game) slot.append(card(game, prev));
  const same = key && slot.querySelector(`[data-key="${CSS.escape(key)}"]`);
  const target = same || (finePointer.matches && slot.querySelector("[data-autofocus]"));
  if (target && focusWasHere) target.focus({ preventScroll: true });
}

/** One live region that always exists: screen readers hear what changed, once. */
function announce(match, wordle) {
  const text = match?.note || (match?.result ? RESULTS[match.result] : match?.state?.your_turn ? "Your turn" : "")
    || wordle?.note || wordle?.result || "";
  if (status.textContent !== text) status.textContent = text;
}

export function initPanel({ focusChallenge, showError }) {
  onError = showError;
  const matchSlot = el("div", { class: "game-slot" });
  const wordleSlot = el("div", { class: "game-slot" });
  const empty = emptyGrill({ focusChallenge });
  body.append(matchSlot, wordleSlot, empty);
  let shown = { match: undefined, wordle: undefined };
  subscribe((state) => {
    if (state.match !== shown.match) renderSlot(matchSlot, state.match, shown.match, matchCard);
    if (state.wordle !== shown.wordle) renderSlot(wordleSlot, state.wordle, shown.wordle, wordleCard);
    shown = { match: state.match, wordle: state.wordle };
    empty.hidden = Boolean(state.match || state.wordle);
    announce(state.match, state.wordle);
    $("open-game").classList.toggle("has-game", Boolean(state.match || state.wordle));
  });
}
