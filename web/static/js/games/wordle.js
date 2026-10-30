// 🟩 Wordle: a 6x5 grid, the letters you've learned about, and a box that sends "/g word".

import { el, str } from "../dom.js";

const COLORS = new Set(["green", "yellow", "gray"]);
const RANK = { gray: 1, yellow: 2, green: 3 };
const ALPHABET = "abcdefghijklmnopqrstuvwxyz";

function readGuesses(raw) {
  return (Array.isArray(raw) ? raw : []).slice(0, 6).map((g) => ({
    word: str(g?.word).toLowerCase().slice(0, 5).padEnd(5, " "),
    colors: Array.from({ length: 5 }, (_, i) => (COLORS.has(g?.colors?.[i]) ? g.colors[i] : "gray")),
  }));
}

function letterStatus(guesses) {
  const best = {};
  for (const { word, colors } of guesses) {
    [...word].forEach((ch, i) => {
      if (RANK[colors[i]] > (RANK[best[ch]] || 0)) best[ch] = colors[i];
    });
  }
  return best;
}

export function renderWordle(s, send, prev, { onNewGame, result }) {
  const guesses = readGuesses(s.guesses);
  const hadBefore = Array.isArray(prev?.guesses) ? prev.guesses.length : guesses.length;
  const rows = 6;   // the server's Wordle always allows 6 tries
  const typingRow = s.finished ? -1 : guesses.length;

  const grid = el("div", { class: "wordle-grid", role: "group", "aria-label": `Wordle, ${guesses.length} of ${rows} tries used` });
  const typedTiles = [];
  for (let r = 0; r < rows; r += 1) {
    const guess = guesses[r];
    const row = el("div", { class: `wordle-row${guess && r >= hadBefore ? " fresh" : ""}` });
    for (let i = 0; i < 5; i += 1) {
      const tile = el("span", { class: `tile${guess ? ` ${guess.colors[i]}` : ""}`, text: guess ? guess.word[i] : "" });
      if (r === typingRow) typedTiles.push(tile);
      row.append(tile);
    }
    if (guess) row.setAttribute("aria-label", `${guess.word.toUpperCase()}: ${guess.colors.join(", ")}`);
    grid.append(row);
  }

  const status = letterStatus(guesses);
  const letters = el("div", { class: "letters", "aria-hidden": "true" },
    [...ALPHABET].map((ch) => el("span", { class: status[ch] || "", text: ch.toUpperCase() })));

  if (s.finished) {
    return el("div", { class: "wordle" }, grid, letters,
      el("p", { class: "wordle-result", text: s.won ? `🎉 Solved in ${guesses.length}/6!` : result || "💀 Out of tries." }),
      el("button", { class: "btn btn-primary", type: "button", onclick: onNewGame, text: "🟩 Play again" }));
  }

  const input = el("input", {
    name: "guess", maxlength: "5", autocomplete: "off", spellcheck: "false", autocapitalize: "off", "aria-label": "Your 5-letter guess",
    placeholder: "crane", "data-autofocus": "true",
    oninput: () => {
      input.value = input.value.replace(/[^a-z]/gi, "").slice(0, 5);
      typedTiles.forEach((tile, i) => {
        tile.textContent = input.value[i] || "";
        tile.classList.toggle("typed", Boolean(input.value[i]));
      });
    },
  });
  const form = el("form", {
    class: "wordle-form",
    onsubmit: (event) => {
      event.preventDefault();
      if (input.value.length === 5) send(`/g ${input.value.toLowerCase()}`);
    },
  }, input, el("button", { class: "btn btn-primary", type: "submit", text: "Guess" }));
  return el("div", { class: "wordle" }, grid, letters, form);
}
