// 🎤 The pitch room and the term sheet on a company's HQ. The conversation is the server's "pitch_log" (the investor's
// lines and what the founders sent); the answer box sends "/pitch your words". The term sheet is a paper ticket:
// the CEO answers it with /offer accept|decline <id> or /offer counter 15M. The server decides every number.
// (New investor lines are announced once by ventures.js; this list is redrawn, so it isn't a live region itself.)

import { el, str } from "./dom.js";
import * as V from "./ventureslogic.js";
import { act, button, confirmStep, draft, render, setDraft } from "./ventures.js";
import { detailsKeep, formError } from "./ventureshq.js";

export function pitchRoom(co) {
  const p = co.pitch || {};
  const parts = [el("h3", { id: "vs-pitch", class: "gs-h3", text: "🎤 Pitch room" })];
  if (co.sheet) parts.push(termSheet(co));
  else if (p.active) parts.push(investorCard(p), conversation(p), answerBox(co, p));
  else parts.push(...idle(co, p));
  return el("section", { class: "vs-panel vs-pitch", "aria-labelledby": "vs-pitch" }, ...parts);
}

function investorCard(p) {
  const who = p.investor || {};
  return el("div", { class: "vs-investor" },
    el("span", { class: "vs-investor-face", "aria-hidden": "true", text: str(who.emoji) }),
    el("span", {}, el("strong", { text: str(who.name) }), el("span", { class: "vs-row-sub", text: ` · ${str(who.firm)}` })),
    el("span", { class: "vs-chip", text: p.turn < p.questions ? `Question ${Math.min(p.turn + 1, p.questions)} of ${p.questions}` : "Deciding" }));
}

function conversation(p) {
  const lines = (Array.isArray(p.log) ? p.log : []).filter((l) => l && typeof l.text === "string");
  return el("ol", { class: "vs-convo", "aria-label": "The conversation", tabindex: "0" },
    ...lines.map((l) => el("li", { class: `vs-say vs-say-${l.who === "investor" ? "them" : "us"}` },
      el("span", { class: "vs-say-who", text: l.who === "investor" ? str(l.name) : "You" }),
      el("span", { class: "vs-say-text", dir: "auto", text: str(l.text) }))),
    p.busy ? el("li", { class: "vs-say vs-say-them vs-thinking", text: "🥔 Thinking about it…" }) : null);
}

function answerBox(co, p) {
  const canSend = co.you && co.you.c_level;
  const locked = p.busy || !canSend;
  const send = async () => {
    const text = draft("pitch-answer").trim();
    if (!text || locked) return;
    if (await act("pitch-send", V.pitchLine(text))) setDraft("pitch-answer", "");
  };
  const box = el("textarea", { id: "vs-pitch-answer", class: "input vs-answer", rows: "3", maxlength: "480", dir: "auto",
    "data-focus": "pitch-answer", placeholder: p.turn === 0 ? "What do you build, for whom, and why will you win?" : "Your answer…",
    readonly: locked, "aria-disabled": locked ? "true" : undefined, "aria-keyshortcuts": "Control+Enter Meta+Enter",
    "aria-describedby": "vs-answer-hint", oninput: (e) => setDraft("pitch-answer", e.target.value),
    onkeydown: (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send(); } } });
  box.value = draft("pitch-answer");
  return el("div", { class: "vs-answer-wrap" },
    el("label", { for: "vs-pitch-answer", class: "gs-h4", text: p.turn === 0 ? "Your pitch" : "Your answer" }), box,
    el("div", { class: "row" },
      button("Send to the investor", send, { key: "pitch-send", primary: true, disabled: locked,
        why: canSend ? (p.busy ? "" : "") : "Only the CEO and the C-level team talk to investors." }),
      button("Walk out", () => act("pitch-stop", "/pitch stop"), { key: "pitch-stop", small: true, disabled: !canSend,
        label: "Walk out of the pitch" })),
    el("p", { id: "vs-answer-hint", class: "gs-muted", text: "Ctrl+Enter sends. Teammates can also talk in the company chat: " +
      "their lines go to the investor with the next answer." }));
}

function idle(co, p) {
  const parts = [];
  const lines = Array.isArray(p.log) ? p.log : [];
  if (lines.length) parts.push(detailsKeep("last-pitch", "The last pitch", conversation({ ...p, busy: false })));
  parts.push(el("p", { class: "gs-muted", text: `${V.plural(p.pitches_left, "pitch", "pitches")} left in this stage.` }));
  parts.push(button(`🎤 Pitch investors (${p.ap_cost} ⚡)`, () => act("pitch", "/pitch"), { key: "pitch", primary: p.can_pitch,
    disabled: !p.can_pitch, why: p.can_pitch ? "" : str(p.why) }));
  return parts;
}

function termSheet(co) {
  const s = co.sheet;
  const ceo = co.you && co.you.ceo;
  const counter = async () => {
    const line = V.counterLine(draft("counter"));
    if (!line) {
      setDraft("counter-error", "Type a valuation like 15M, 2.5B or 900K.");
      render();
      document.getElementById("vs-counter")?.focus();
      return;
    }
    setDraft("counter-error", "");
    if (await act("counter", line)) setDraft("counter", "");
  };
  const accept = async () => {
    if (await confirmStep({ title: "✅ Accept the term sheet?", text: `${str(s.investor)} puts in ${V.money(s.amount)} and owns ` +
      `${V.percent(s.equity_bp)} of the company. Everyone's shares shrink a little. This can't be undone.`, yes: "Accept" })) {
      act("sheet-yes", V.offerLine("accept", str(s.id)));
    }
  };
  const facts = [["Money", V.money(s.amount)], ["For", V.percent(s.equity_bp)], ["Pre-money", V.money(s.pre)],
    ["Post-money", V.money(s.post)]];
  const error = draft("counter-error");
  return el("article", { class: "vs-sheet", "aria-labelledby": "vs-sheet-title" },
    el("h4", { id: "vs-sheet-title", class: "ticket-title", tabindex: "-1", text: `📄 Term sheet · ${str(s.investor)}` }),
    s.message ? el("p", { class: "ticket-text", dir: "auto", text: `“${str(s.message)}”` }) : null,
    el("dl", { class: "vs-sheet-facts" }, ...facts.flatMap(([k, v]) => [el("dt", { text: k }), el("dd", { text: v })])),
    el("p", { class: "ticket-muted", text: `1× liquidation preference · expires ${V.countdown(s.expires)}` }),
    ceo ? el("div", { class: "vs-sheet-actions" },
      el("div", { class: "row" },
        button("✅ Accept", accept, { key: "sheet-yes", primary: true, label: "Accept the term sheet" }),
        button("Decline", () => act("sheet-no", V.offerLine("decline", str(s.id))), { key: "sheet-no", label: "Decline the term sheet" })),
      s.can_counter ? el("form", { class: "row vs-counter", onsubmit: (e) => { e.preventDefault(); counter(); } },
        el("label", { for: "vs-counter", class: "visually-hidden", text: "Your valuation (post-money)" }),
        el("input", { id: "vs-counter", class: "input", "data-focus": "counter", placeholder: `More than ${V.money(s.post)}, like 15M`,
          value: draft("counter"), "aria-invalid": error ? "true" : undefined, "aria-describedby": error ? "counter-error" : undefined,
          oninput: (e) => setDraft("counter", e.target.value) }),
        el("button", { class: "btn btn-ghost btn-small", type: "submit", "data-focus": "counter-go", text: "Counter once" })) : null,
      formError("counter"))
      : el("p", { class: "ticket-muted", text: "⏳ Waiting for the CEO to answer." }));
}
