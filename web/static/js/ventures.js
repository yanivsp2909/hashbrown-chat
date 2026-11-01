// 🏢 The Ventures screen: the startup game by clicking. It takes the chat column's place (like the Groups screen):
// the home (my company or "Start a company", the Unicorn Board, the graveyard, my investments), the "Start a
// company" wizard, and a company's HQ (ventureshq.js). What it shows comes from the server's "ventures" and
// "company" packets; every button sends the same /command a player could type, so the server's rules decide.

import { $, clear, el, str } from "./dom.js";
import { send } from "./api.js";
import { getState } from "./store.js";
import * as groups from "./groups.js";
import * as V from "./ventureslogic.js";
import { renderHq } from "./ventureshq.js";

const REPLY_MS = 7000;
const REPLY_WINDOW = 4000;   // only replies this soon after a button here (not the quiet refreshes)
let view = null;             // null = closed, "" = home, "new" = the wizard, a company id = its HQ
let home = null;             // the last "ventures" packet (read with readHome)
let company = null;          // the open HQ's company
let wizard = { step: 1, name: "", sector: "", error: "" };
let lastAct = 0;
let replyTimer = null;
const inFlight = new Set();
const drafts = {};           // typed text that must survive a redraw (data-focus key -> value)
let hooks = { onError: () => {}, closeDrawer: () => {} };

export const isOpen = () => view !== null;

// ---------------------------------------------------------------- sending

/** Send one command for a button (a second click while it's on its way does nothing). */
export async function act(key, line) {
  if (inFlight.has(key)) return false;
  inFlight.add(key);
  lastAct = Date.now();
  hideReply();
  render();
  try {
    const error = await send({ type: "line", text: line });
    if (error) {
      noteServerText("error", `⚠️ ${error}`, true);
      hooks.onError(error);
      return false;
    }
    return true;
  } finally {
    inFlight.delete(key);
    render();
  }
}

export const busy = (key) => inFlight.has(key);
export const draft = (key) => drafts[key] ?? "";
export function setDraft(key, value) { drafts[key] = value; }
export const confirmStep = groups.confirmStep;   // (the same small dialog the Groups screen uses)

/** The latest server reply, in the line at the bottom (the chat behind the screen is hidden). */
export function noteServerText(kind, text, force = false) {
  if (!isOpen() || (!force && Date.now() - lastAct > REPLY_WINDOW)) return;
  const line = $("ventures-reply");
  const isError = kind === "error";
  line.textContent = "";
  line.setAttribute("role", isError ? "alert" : "status");
  line.className = `gs-reply gs-reply-${["error", "money", "event"].includes(kind) ? kind : "system"}`;
  clearTimeout(replyTimer);
  setTimeout(() => { line.textContent = str(text).split("\n")[0]; }, 50);
  if (!isError) replyTimer = setTimeout(hideReply, REPLY_MS);
}

function hideReply() {
  const line = $("ventures-reply");
  line.textContent = "";
  line.className = "gs-reply visually-hidden";
}

// ---------------------------------------------------------------- drawing

/** Draw the screen again, keeping the keyboard focus (and the caret) where it was. */
export function render() {
  if (view === null) return;
  const body = $("ventures-body");
  const active = document.activeElement;
  const focusKey = active && body.contains(active) ? active.dataset.focus : "";
  const caret = focusKey && "selectionStart" in active ? [active.selectionStart, active.selectionEnd] : null;
  clear(body);
  const parts = view === "" ? homeView() : view === "new" ? wizardView()
    : company && company.id === view ? renderHq(company, home)
      : [el("p", { class: "gs-muted", role: "status", text: "Loading the company…" })];
  body.append(...parts.filter(Boolean));   // (a part that has nothing to show is null)
  if (focusKey) {
    const again = body.querySelector(`[data-focus="${CSS.escape(focusKey)}"]`);
    if (again) {
      again.focus({ preventScroll: true });
      if (caret && "setSelectionRange" in again) try { again.setSelectionRange(...caret); } catch { /* (not a text box) */ }
    }
  }
}

function header(title, back) {
  return el("div", { class: "gs-head" },
    el("button", { class: "icon-btn", type: "button", "aria-label": back.label, "data-focus": "back", onclick: back.go,
      text: "←" }),
    el("h2", { id: "ventures-title", class: "gs-title", tabindex: "-1", text: title }));
}

function seasonLine() {
  const s = home ? home.season : null;
  if (!s) return null;
  return el("p", { class: "vs-season" },
    el("span", { class: "vs-pill", text: `Season ${str(s.number)}` }),
    ` Day ${str(s.day)} of ${str(s.days)} · the next game day starts ${V.countdown(s.next_tick)}`);
}

function homeView() {
  const parts = [header("🏢 Ventures", { label: "Back to the chat", go: close }), seasonLine()];
  if (!home) return [...parts, el("p", { class: "gs-muted", role: "status", text: "Loading Ventures…" })];
  parts.push(...home.invites.map(inviteTicket));
  parts.push(home.mine ? myCompanyCard(home.mine) : startCard());
  parts.push(el("div", { class: "vs-columns" },
    el("div", { class: "vs-col" }, boardPanel(), newsPanel()),
    el("div", { class: "vs-col" }, investmentsPanel(), graveyardPanel())));
  return parts;
}

function inviteTicket(invite) {
  const key = `join:${str(invite.company)}`;
  const role = (home.roles.find((r) => r.key === invite.role) || {});
  const equity = Number(invite.bp) ? ` with ${V.percent(invite.bp)} of the company` : "";
  return el("article", { class: "ticket vs-ticket", "aria-label": `Invite to ${str(invite.name)}` },
    el("h3", { class: "ticket-title", text: `📨 ${str(invite.from)} invites you to ${str(invite.name)}` }),
    el("p", { class: "ticket-text", text: `As ${str(role.icon)} ${str(role.name || invite.role)}${equity}.` }),
    el("div", { class: "row" },
      button("Accept", () => act(key, `/join ${str(invite.group)}`), { primary: true, key }),
      button("Decline", () => act(`${key}:no`, `/invites decline ${str(invite.group)}`), { key: `${key}:no` })));
}

function myCompanyCard(mine) {
  return el("section", { class: "vs-plate vs-mine", "aria-labelledby": "vs-mine-title" },
    el("div", { class: "vs-mine-head" },
      el("span", { class: "vs-icon", "aria-hidden": "true", text: str(mine.icon) }),
      el("div", {},
        el("h3", { id: "vs-mine-title", class: "vs-mine-name", text: str(mine.name) }),
        el("p", { class: "gs-muted", text: `${str(mine.stage_name)} · day ${str(mine.age)} · ${mine.team.map(str).join(", ")}` })),
      mine.fumes ? el("span", { class: "vs-chip vs-chip-danger", text: "🚨 On fumes" }) : null),
    el("p", { class: "vs-big" }, el("span", { class: "vs-big-label", text: "Valuation " }), V.money(mine.valuation)),
    button("Open the HQ", () => openCompany(mine.id), { primary: true, key: "open-mine" }));
}

function startCard() {
  const me = home.me;
  const short = Number(me.tokens) < Number(me.found_cost);
  return el("section", { class: "vs-plate vs-start", "aria-labelledby": "vs-start-title" },
    el("h3", { id: "vs-start-title", class: "vs-start-title", text: "You don't have a company yet" }),
    el("p", { class: "gs-muted", text: `Pick an idea, invite friends, raise money from investors and take it all the way to an IPO. ` +
      `Founding costs ${str(me.found_cost)} 🪙 (you have ${str(me.tokens)}).` }),
    button("🚀 Start a company", startWizard, { primary: true, key: "start", disabled: !me.can_found,
      why: me.can_found ? "" : str(me.why) || (short ? `You need ${me.found_cost} 🪙.` : "") }));
}

function companyRow(co, extra = "") {
  return el("li", {},
    el("button", { class: "vs-row", type: "button", "data-focus": `co:${str(co.id)}`, onclick: () => openCompany(co.id) },
      el("span", { class: "vs-row-icon", "aria-hidden": "true", text: str(co.icon) }),
      el("span", { class: "vs-row-main" },
        el("span", { class: "vs-row-name", text: str(co.name) }),
        el("span", { class: "vs-row-sub", text: `${str(co.stage_name)} · ${co.team.map(str).join(", ")}${extra}` })),
      el("span", { class: "vs-row-value", text: `${V.money(co.valuation)}${Number(co.valuation) >= 1e9 ? " 🦄" : ""}` })));
}

function panel(id, title, ...children) {
  return el("section", { class: "vs-panel", "aria-labelledby": id }, el("h3", { id, class: "gs-h3", text: title }), ...children);
}

function boardPanel() {
  return panel("vs-board", "🦄 Unicorn Board", home.board.length
    ? el("ol", { class: "vs-list vs-ranked" }, ...home.board.map((co) => companyRow(co)))
    : el("p", { class: "gs-empty", text: "No companies yet. Be the first!" }));
}

function newsPanel() {
  return panel("vs-news", "📰 Ventures News", home.news.length
    ? el("ul", { class: "vs-list vs-news" }, ...home.news.map((n) => el("li", {},
      el("strong", { text: str(n.headline) }), n.text ? el("span", { class: "vs-row-sub", text: ` ${str(n.text)}` }) : null)))
    : el("p", { class: "gs-empty", text: "A quiet day on the market." }));
}

function investmentsPanel() {
  const { held, waiting } = home.investments;
  const rows = [...held.map((co) => companyRow(co, ` · you own ${V.percent(co.bp)}`)),
    ...waiting.map((w) => el("li", { class: "vs-row vs-row-static" },
      el("span", { class: "vs-row-main" }, el("span", { class: "vs-row-name", text: str(w.name) }),
        el("span", { class: "vs-row-sub", text: `⏳ ${str(w.tokens)} 🪙 offered for ${V.percent(w.bp)}, waiting for the CEO` }))))];
  return panel("vs-invest", "😇 My investments", rows.length ? el("ul", { class: "vs-list" }, ...rows)
    : el("p", { class: "gs-empty", text: "Open a young company on the board to invest your tokens in it." }));
}

function graveyardPanel() {
  return panel("vs-grave", "⚰️ Graveyard", home.graveyard.length
    ? el("ul", { class: "vs-list vs-grave" }, ...home.graveyard.slice(0, 8).map((g) => el("li", { class: "vs-grave-row" },
      el("span", { class: "vs-row-name", text: `🪦 ${str(g.name)}` }),
      el("span", { class: "vs-row-sub", text: `${str(g.how)} after ${str(g.lived)} days, peak ${V.money(g.peak)}: ${str(g.cause)}` }),
      el("em", { class: "vs-epitaph", text: `“${str(g.epitaph)}”` }))))
    : el("p", { class: "gs-empty", text: "Empty. For now." }));
}

/** A button (gold when primary); a disabled one still explains why, in its description. */
export function button(text, onclick, { primary = false, key = "", disabled = false, why = "", danger = false, small = false } = {}) {
  const id = why ? `why-${key.replace(/[^\w-]/g, "_")}` : undefined;
  const node = el("button", { class: `btn ${danger ? "btn-danger" : primary ? "btn-primary" : "btn-ghost"}${small ? " btn-small" : ""}`,
    type: "button", "data-focus": key || undefined, "aria-describedby": id, "aria-busy": busy(key) ? "true" : undefined,
    "aria-disabled": disabled || busy(key) ? "true" : undefined,
    onclick: () => { if (!disabled && !busy(key)) onclick(); } }, text);
  return why ? el("span", { class: "vs-btn-wrap" }, node, el("span", { id, class: "vs-why", text: why })) : node;
}

// ---------------------------------------------------------------- the wizard

function startWizard() {
  wizard = { step: 1, name: "", sector: "", error: "" };
  view = "new";
  render();
  $("ventures-title")?.focus();
}

function wizardView() {
  const back = wizard.step === 1 ? () => showHome() : () => { wizard = { ...wizard, step: wizard.step - 1, error: "" }; render(); };
  const steps = ["Name", "Sector", "Found it"];
  return [header("🚀 Start a company", { label: wizard.step === 1 ? "Back to Ventures" : "Back one step", go: back }),
    el("ol", { class: "vs-steps", "aria-label": "Steps" }, ...steps.map((s, i) => el("li", {
      class: i + 1 === wizard.step ? "now" : i + 1 < wizard.step ? "done" : "", "aria-current": i + 1 === wizard.step ? "step" : undefined,
      text: `${i + 1}. ${s}` }))),
    wizard.step === 1 ? nameStep() : wizard.step === 2 ? sectorStep() : confirmStepView(),
    wizard.error ? el("p", { class: "vs-error", role: "alert", text: wizard.error }) : null];
}

function nameStep() {
  const input = el("input", { id: "vs-name", class: "input", "data-focus": "wiz-name", value: wizard.name, maxlength: "16",
    autocomplete: "off", "aria-describedby": "vs-name-hint", oninput: (e) => { wizard = { ...wizard, name: e.target.value }; } });
  const next = () => {
    const problem = V.nameProblem(wizard.name);
    wizard = { ...wizard, error: problem, step: problem ? 1 : 2 };
    render();
    if (!problem) $("ventures-title")?.focus();
  };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); next(); } });
  return el("div", { class: "vs-plate vs-wizard" },
    el("label", { for: "vs-name", class: "gs-h4", text: "What's your company called?" }), input,
    el("p", { id: "vs-name-hint", class: "gs-muted", text: `${V.NAME_RULE}. It's also the name of your company's private chat.` }),
    button("Next: pick a sector →", next, { primary: true, key: "wiz-next" }));
}

function sectorStep() {
  return el("fieldset", { class: "vs-sectors" },
    el("legend", { class: "gs-h4", text: `What does ${wizard.name} do?` }),
    ...home.sectors.map((s) => el("label", { class: `vs-sector${wizard.sector === s.key ? " picked" : ""}` },
      el("input", { type: "radio", name: "vs-sector", value: str(s.key), class: "visually-hidden", "data-focus": `sector:${str(s.key)}`,
        checked: wizard.sector === s.key, onchange: () => { wizard = { ...wizard, sector: s.key, step: 3, error: "" }; render(); $("ventures-title")?.focus(); } }),
      el("span", { class: "vs-sector-icon", "aria-hidden": "true", text: str(s.icon) }),
      el("span", { class: "vs-sector-name", text: str(s.name) }),
      el("span", { class: "vs-sector-pitch", text: str(s.pitch) }),
      el("span", { class: "vs-sector-twist", text: `Twist: ${str(s.twist)}` }),
      el("span", { class: `vs-chip vs-diff-${Number(s.difficulty) || 2}`, text: V.difficulty(s.difficulty) }))));
}

function confirmStepView() {
  const sector = home.sectors.find((s) => s.key === wizard.sector) || {};
  const me = home.me;
  return el("div", { class: "vs-plate vs-wizard" },
    el("p", { class: "vs-confirm-name" }, el("span", { "aria-hidden": "true", text: `${str(sector.icon)} ` }), wizard.name),
    el("p", { class: "gs-muted", text: `${str(sector.name)} · ${str(sector.pitch)}` }),
    el("ul", { class: "vs-next" },
      el("li", { text: `Costs ${str(me.found_cost)} 🪙 (you have ${str(me.tokens)}); it goes to the public fund.` }),
      el("li", { text: "You get $50K of founders' savings and a private company chat. You're the 👑 CEO." }),
      el("li", { text: "Every day you have a few action points: build, hire, market, sell. At 21:00 a new game day starts." }),
      el("li", { text: "Run out of cash and the company dies. Raise money by pitching investors." })),
    button(`🏢 Found ${wizard.name}`, found, { primary: true, key: "wiz-found" }));
}

async function found() {
  if (await act("wiz-found", V.foundLine(wizard.name, wizard.sector))) wizard = { ...wizard, error: "" };
}

/** A server answer to the wizard: success opens the HQ (from the next "ventures" packet), an error shows here. */
function wizardReply(kind, text) {
  if (view !== "new" || Date.now() - lastAct > REPLY_WINDOW) return;
  if (kind === "error") {
    wizard = { ...wizard, error: str(text) };
    render();
  }
}

// ---------------------------------------------------------------- open, close, packets

function setOpen(open) {
  $("ventures-screen").hidden = !open;
  $("screen-chat").classList.toggle("ventures-open", open);
  $("ventures-open").setAttribute("aria-expanded", String(open));
}

export function open() {
  if (groups.isOpen()) groups.close();
  hooks.closeDrawer();
  view = "";
  setOpen(true);
  render();
  send({ type: "get_ventures" });
  $("ventures-title")?.focus();
}

export function close(refocus = true) {
  if (view === null) return;
  view = null;
  company = null;
  setOpen(false);
  send({ type: "ventures_closed" });
  hideReply();
  if (!refocus) return;   // (another screen is opening and takes the focus)
  const opener = $("ventures-open");
  (opener.offsetParent && getComputedStyle(opener).visibility !== "hidden" ? opener : $("open-sidebar")).focus();
}

function showHome() {
  view = "";
  company = null;
  send({ type: "get_ventures" });
  render();
  $("ventures-title")?.focus();
}

export function openCompany(id) {
  view = str(id);
  company = null;
  render();
  send({ type: "get_company", company: view });
  $("ventures-title")?.focus();
}

export const backHome = showHome;

/** {"type": "ventures"} from the server. */
export function onVentures(msg) {
  const before = home;
  home = V.readHome(msg);
  if (view === "new" && home.mine && (!before || !before.mine)) {   // just founded: straight into the HQ
    openCompany(home.mine.id);
    return;
  }
  if (view === "" || view === "new" || (view && company)) render();
}

/** {"type": "company"} from the server (only the open one is drawn). */
export function onCompany(msg) {
  const next = V.readCompany(msg);
  if (!next || next.id !== view) return;
  const first = company === null;
  company = next;
  render();
  if (first) $("ventures-title")?.focus();
}

/** Server text while the screen is open: in the reply line (and the wizard's error). */
export function onServerText(kind, text) {
  wizardReply(kind, text);
  noteServerText(kind, text);
}

/** 🔁 After a (re)login the server doesn't know the screen is open. */
export function resync() {
  if (view === null) return;
  send({ type: "get_ventures" });
  if (view && view !== "new") send({ type: "get_company", company: view });
}

export function resetVentures() {
  view = null;
  home = null;
  company = null;
  setOpen(false);
}

export const myName = () => getState().nick;

export function initVentures(nextHooks) {
  hooks = { ...hooks, ...nextHooks };
  $("ventures-open").addEventListener("click", () => (isOpen() ? close() : open()));
  $("groups-open").addEventListener("click", () => { if (isOpen()) close(false); });
  $("ventures-screen").addEventListener("keydown", (event) => {
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName) && event.target.type !== "radio";
    if (event.key === "Escape" && !$("groups-confirm").open && !typing && !event.defaultPrevented && !event.isComposing) {
      event.preventDefault();
      if (view) showHome(); else close();
    }
  });
}
