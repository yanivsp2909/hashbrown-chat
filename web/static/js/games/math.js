// ➗ Math Duel: one big question, an answer box and the live score.

import { el, str } from "../dom.js";

const num = (value) => (Number.isFinite(value) ? value : 0);

export function renderMath(s, send) {
  const question = str(s.question);
  const locked = Boolean(s.locked_out);
  const open = Boolean(question) && !s.finished && !locked;
  const input = el("input", {
    type: "text", name: "answer", inputmode: "numeric", maxlength: "8", autocomplete: "off", "aria-label": "Your answer",
    placeholder: open ? "?" : "", disabled: !open, "data-autofocus": open ? "true" : undefined,
  });
  const form = el("form", {
    class: "math-form",
    onsubmit: (event) => {
      event.preventDefault();
      const answer = input.value.trim();
      if (/^-?\d{1,7}$/.test(answer)) send(answer);
      input.value = "";
    },
  }, input, el("button", { class: "btn btn-primary", type: "submit", disabled: !open, text: "Answer" }));

  const last = s.last && typeof s.last === "object" ? s.last : null;
  const scored = { you: "you got it ✅", them: "they got it", nobody: "nobody got it" }[str(last?.scored)] || "";
  return el("div", { class: "math" },
    el("div", { class: "scoreboard", "aria-label": `Score: you ${num(s.you)}, them ${num(s.them)}` },
      el("div", {}, el("p", { class: "score", text: String(num(s.you)) }), el("p", { class: "score-label", text: "You" })),
      el("span", { class: "score-vs", text: "vs" }),
      el("div", {}, el("p", { class: "score", text: String(num(s.them)) }), el("p", { class: "score-label", text: "Them" }))),
    el("p", { class: "question", text: question ? `${question} = ?` : s.finished ? "🏁 Done!" : "…" }),
    form,
    locked ? el("p", { class: "math-locked", text: "❌ Wrong answer. Wait for the next question." }) : null,
    el("p", { class: "math-meta", text: `Question ${num(s.round)} of ${num(s.max_rounds)} · first to ${num(s.target)}` }),
    last ? el("p", { class: "math-meta", text: `Last one: ${str(last.question)} = ${str(last.answer)} · ${scored}` }) : null);
}
