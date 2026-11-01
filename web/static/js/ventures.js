// 🏢 The Ventures screen: the startup game by clicking. It takes the chat column's place (like the Groups screen):
// the home (my company or "Start a company", the Unicorn Board, news, my investments, the graveyard), the "Start a
// company" wizard, and a company's HQ (ventureshq.js). What it shows comes from the server's "ventures" and
// "company" packets; every button sends the same /command a player could type, so the server's rules decide.
// Screen readers: the body is redrawn when something changes, so news is announced once through one steady live
// region (#ventures-live), never by the redrawn parts themselves.

import { $, clear, el, str } from "./dom.js";
import { send } from "./api.js";
import * as groups from "./groups.js";
import * as V from "./ventureslogic.js";
import { renderHq } from "./ventureshq.js";

const REPLY_MS = 7000;
const REPLY_WINDOW = 4000;   // only replies this soon after a button here (not the quiet refreshes)
let view = null;             // null = closed, "" = home, "new" = the wizard, a company id = its HQ
let home = null;             // the last "ventures" packet (read with readHome)
let company = null;          // the open HQ's company
let companyError = "";       // why the HQ couldn't load
let wizard = { step: 1, name: "", sector: "", error: "" };
let lastAct = 0;
let replyTimer = null;
let textTimer = null;
let pendingRender = false;   // a redraw waits while a list box is open (it would close under the player)
const lastPackets = { ventures: "", company: "" };
const inFlight = new Set();
const drafts = {};           // typed text and open/closed parts that must survive a redraw (data-focus key -> value)
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

/** Say something once to screen readers (the redrawn screen never announces itself). */
export function announce(text) {
  const live = $("ventures-live");
  live.textContent = "";
  setTimeout(() => { live.textContent = str(text); }, 60);
}

/** The latest server reply, in the line at the bottom (the chat behind the screen is hidden). */
export function noteServerText(kind, text, force = false) {
  if (!isOpen() || (!force && Date.now() - lastAct > REPLY_WINDOW)) return;
  const line = $("ventures-reply");
  const isError = kind === "error";
  line.textContent = "";
  line.setAttribute("role", isError ? "alert" : "status");
  line.className = `gs-reply gs-reply-${["error", "money", "event"].includes(kind) ? kind : "system"}`;
  clearTimeout(replyTimer);
  clearTimeout(textTimer);
  textTimer = setTimeout(() => { line.textContent = str(text).split("\n")[0]; }, 50);
  if (!isError) replyTimer = setTimeout(hideReply, REPLY_MS);
}

function hideReply() {
  clearTimeout(textTimer);
  const line = $("ventures-reply");
  line.textContent = "";
  line.className = "gs-reply visually-hidden";
}

// ---------------------------------------------------------------- drawing

/** Draw the screen again, keeping the keyboard focus (and the caret, and the conversation's scroll). */
export function render(force = false) {
  if (view === null) return;
  const body = $("ventures-body");
  const active = document.activeElement;
  if (!force && active && body.contains(active) && active.tagName === "SELECT") {   // (an open list box would snap shut)
    pendingRender = true;
    return;
  }
  pendingRender = false;
  const focusKey = active && body.contains(active) ? active.dataset.focus : "";
  const caret = focusKey && "selectionStart" in active ? [active.selectionStart, active.selectionEnd] : null;
  const convo = body.querySelector(".vs-convo");
  const atBottom = !convo || convo.scrollHeight - convo.scrollTop - convo.clientHeight < 40;
  clear(body);
  const parts = view === "" ? homeView() : view === "new" ? wizardView()
    : company && company.id === view ? renderHq(company, home) : loadingView();
  body.append(...parts.filter(Boolean));   // (a part that has nothing to show is null)
  const newConvo = body.querySelector(".vs-convo");
  if (newConvo && atBottom) newConvo.scrollTop = newConvo.scrollHeight;
  if (focusKey) {
    const again = body.querySelector(`[data-focus="${CSS.escape(focusKey)}"]`);
    if (again) {
      again.focus({ preventScroll: true });
      if (caret && "setSelectionRange" in again) try { again.setSelectionRange(...caret); } catch { /* (not a text box) */ }
    } else {
      $("ventures-title")?.focus({ preventScroll: true });   // (the button is gone: back to the heading)
    }
  }
}

export function header(title, back) {
  return el("div", { class: "gs-head" },
    el("button", { class: "icon-btn", type: "button", "aria-label": back.label, "data-focus": "back", onclick: back.go,
      text: "←" }),
    el("h2", { id: "ventures-title", class: "gs-title", tabindex: "-1", text: title }));
}

function loadingView() {
  return [header("🏢 Company", { label: "Back to Ventures", go: showHome }),
    companyError ? el("p", { class: "vs-error", text: companyError })
      : el("p", { class: "gs-muted", text: "Loading the company…" })];
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
  if (!home) return [...parts, el("p", { class: "gs-muted", text: "Loading Ventures…" })];
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
  return el("article", { class: "vs-ticket", "aria-label": `Invite to ${str(invite.name)}` },
    el("h3", { class: "ticket-title", text: `📨 ${str(invite.from)} invites you to ${str(invite.name)}` }),
    el("p", { class: "ticket-text", text: `As ${str(role.icon)} ${str(role.name || invite.role)}${equity}.` }),
    el("div", { class: "row" },
      button("Accept", () => act(key, `/join ${str(invite.group)}`), { primary: true, key, label: `Accept the invite to ${str(invite.name)}` }),
      button("Decline", () => act(`${key}:no`, `/invites decline ${str(invite.group)}`), { key: `${key}:no`, label: `Decline the invite to ${str(invite.name)}` })));
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

export function newsList(news) {
  return el("ul", { class: "vs-list vs-news" }, ...news.map((n) => el("li", {},
    el("strong", { dir: "auto", text: str(n.headline) }), n.text ? el("span", { class: "vs-row-sub", dir: "auto", text: ` ${str(n.text)}` }) : null)));
}

function newsPanel() {
  return panel("vs-news", "📰 Ventures News", home.news.length ? newsList(home.news)
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

/** A button (gold when primary). A disabled one still explains why, in a line linked to it; label: a clearer name. */
export function button(text, onclick, { primary = false, key = "", disabled = false, why = "", danger = false, small = false, label = "" } = {}) {
  const isBusy = busy(key);
  const showWhy = why && !isBusy;
  const id = showWhy ? `why-${key.replace(/[^\w-]/g, "_")}` : undefined;
  const node = el("button", { class: `btn ${danger ? "btn-danger" : primary ? "btn-primary" : "btn-ghost"}${small ? " btn-small" : ""}`,
    type: "button", "data-focus": key || undefined, "aria-describedby": id, "aria-label": label || undefined,
    "aria-busy": isBusy ? "true" : undefined, "aria-disabled": disabled || isBusy ? "true" : undefined,
    onclick: () => { if (!disabled && !busy(key)) onclick(); } }, text);
  return showWhy ? el("span", { class: "vs-btn-wrap" }, node, el("span", { id, class: "vs-why", text: why })) : node;
}

// ---------------------------------------------------------------- the wizard

const STEPS = ["Name", "Sector", "Found it"];

function startWizard() {
  wizard = { step: 1, name: "", sector: "", error: "" };
  view = "new";
  render();
  $("ventures-title")?.focus();
}

function toStep(step) {
  wizard = { ...wizard, step, error: "" };
  render();
  $("ventures-title")?.focus();
}

function wizardView() {
  const back = wizard.step === 1 ? () => showHome() : () => toStep(wizard.step - 1);
  return [header(`🚀 Start a company · step ${wizard.step} of 3: ${STEPS[wizard.step - 1]}`,
    { label: wizard.step === 1 ? "Back to Ventures" : "Back one step", go: back }),
  el("ol", { class: "vs-steps", "aria-label": "Steps" }, ...STEPS.map((s, i) => el("li", {
    class: i + 1 === wizard.step ? "now" : i + 1 < wizard.step ? "done" : "", "aria-current": i + 1 === wizard.step ? "step" : undefined },
  `${i + 1}. ${s}`, i + 1 < wizard.step ? el("span", { class: "visually-hidden", text: " (done)" }) : null))),
  wizard.step === 1 ? nameStep() : wizard.step === 2 ? sectorStep() : confirmStepView()];
}

function nameStep() {
  const error = wizard.error;
  const input = el("input", { id: "vs-name", class: "input", "data-focus": "wiz-name", value: wizard.name, maxlength: "16",
    autocomplete: "off", "aria-describedby": error ? "vs-name-error vs-name-hint" : "vs-name-hint", "aria-invalid": error ? "true" : undefined,
    oninput: (e) => { wizard = { ...wizard, name: e.target.value }; } });
  const next = () => {
    const problem = V.nameProblem(wizard.name);
    if (problem) {
      wizard = { ...wizard, error: problem };
      render();
      $("vs-name")?.focus();
      return;
    }
    toStep(2);
  };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); next(); } });
  return el("div", { class: "vs-plate vs-wizard" },
    el("label", { for: "vs-name", class: "vs-step-q", text: "What's your company called?" }), input,
    error ? el("p", { id: "vs-name-error", class: "vs-error", text: error }) : null,
    el("p", { id: "vs-name-hint", class: "gs-muted", text: `${V.NAME_RULE}. It's also the name of your company's private chat.` }),
    button("Next: pick a sector →", next, { primary: true, key: "wiz-next" }));
}

function sectorStep() {
  const cards = home.sectors.map((s) => {
    const key = str(s.key);
    return el("label", { class: `vs-sector${wizard.sector === key ? " picked" : ""}` },
      el("input", { type: "radio", name: "vs-sector", value: key, class: "visually-hidden", "data-focus": `sector:${key}`,
        checked: wizard.sector === key, "aria-labelledby": `vs-sn-${key}`, "aria-describedby": `vs-sd-${key}`,
        onchange: () => { wizard = { ...wizard, sector: key }; render(); } }),
      el("span", { class: "vs-sector-icon", "aria-hidden": "true", text: str(s.icon) }),
      el("span", { id: `vs-sn-${key}`, class: "vs-sector-name", text: str(s.name) }),
      el("span", { id: `vs-sd-${key}`, class: "vs-sector-text" },
        el("span", { class: "vs-sector-pitch", text: str(s.pitch) }),
        el("span", { class: "vs-sector-twist", text: ` Twist: ${str(s.twist)}` }),
        el("span", { class: "visually-hidden", text: ` ${V.difficulty(s.difficulty)}.` })),
      el("span", { class: "vs-chip", "aria-hidden": "true", text: `${"🌶️".repeat(Number(s.difficulty) || 2)} ${V.difficulty(s.difficulty)}` }),
      wizard.sector === key ? el("span", { class: "vs-picked-mark", "aria-hidden": "true", text: "✓ Picked" }) : null);
  });
  return el("div", { class: "vs-plate vs-wizard" },
    el("fieldset", { class: "vs-sectors" }, el("legend", { class: "vs-step-q", text: `What does ${wizard.name} do?` }), ...cards),
    button("Next: check it →", () => toStep(3), { primary: true, key: "wiz-next2", disabled: !wizard.sector,
      why: wizard.sector ? "" : "Pick a sector first." }));
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
    wizard.error ? el("p", { class: "vs-error", text: wizard.error }) : null,
    button(`🏢 Found ${wizard.name}`, found, { primary: true, key: "wiz-found" }));
}

async function found() {
  if (await act("wiz-found", V.foundLine(wizard.name, wizard.sector))) wizard = { ...wizard, error: "" };
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
  lastPackets.company = "";
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
  companyError = "";
  lastPackets.company = "";
  render();
  send({ type: "get_company", company: view });
  $("ventures-title")?.focus();
}

export const backHome = showHome;

/** {"type": "ventures"} from the server (an unchanged one isn't drawn again). */
export function onVentures(msg) {
  const text = JSON.stringify(msg);
  if (text === lastPackets.ventures) return;
  lastPackets.ventures = text;
  const before = home;
  home = V.readHome(msg);
  if (view === "new" && home.mine && (!before || !before.mine)) {   // just founded: straight into the HQ
    announce(`${home.mine.name} is founded!`);
    openCompany(home.mine.id);
    return;
  }
  if (view === "" || view === "new" || (view && company)) render();
}

/** {"type": "company"} from the server (only the open one is drawn, and only when it changed). */
export function onCompany(msg) {
  const next = V.readCompany(msg);
  if (!next || next.id !== view) return;
  const text = JSON.stringify(msg);
  if (text === lastPackets.company) return;
  lastPackets.company = text;
  const before = company;
  company = next;
  render();
  if (!before) {
    $("ventures-title")?.focus();
    return;
  }
  announceChanges(before, next);
}

/** What changed that a screen reader should hear (once). */
function announceChanges(before, next) {
  if (next.fumes && !before.fumes) announce(`🚨 ${next.name} is out of cash: on fumes!`);
  const was = (before.pitch && before.pitch.log) || [];
  const log = (next.pitch && next.pitch.log) || [];
  const newest = log[log.length - 1];
  if (log.length > was.length && newest && newest.who === "investor") announce(`${str(newest.name)}: ${str(newest.text)}`);
  if (next.sheet && (!before.sheet || before.sheet.id !== next.sheet.id)) {
    announce(`📄 A term sheet from ${str(next.sheet.investor)}: ${V.money(next.sheet.amount)} for ${V.percent(next.sheet.equity_bp)}.`);
    const where = document.activeElement;
    if (!where || where === document.body || $("ventures-body").contains(where)) $("vs-sheet-title")?.focus();
  }
}

/** Server text while the screen is open: in the reply line (and the wizard's or the loading HQ's error). */
export function onServerText(kind, text) {
  const recent = Date.now() - lastAct <= REPLY_WINDOW;
  if (kind === "error" && view === "new" && recent) {
    wizard = { ...wizard, error: str(text) };
    render();
    return;   // (shown in the wizard: not twice)
  }
  if (kind === "error" && view && view !== "new" && !company) {
    companyError = str(text);
    render();
  }
  noteServerText(kind, text);
}

/** 🔁 After a (re)login the server doesn't know the screen is open. */
export function resync() {
  if (view === null) return;
  lastPackets.ventures = "";
  lastPackets.company = "";
  send({ type: "get_ventures" });
  if (view && view !== "new") send({ type: "get_company", company: view });
}

export function resetVentures() {
  view = null;
  home = null;
  company = null;
  setOpen(false);
}

export function initVentures(nextHooks) {
  hooks = { ...hooks, ...nextHooks };
  $("ventures-open").addEventListener("click", () => (isOpen() ? close() : open()));
  $("groups-open").addEventListener("click", () => { if (isOpen()) close(false); });
  $("ventures-screen").addEventListener("focusout", () => { if (pendingRender) setTimeout(render, 0); });
  $("ventures-screen").addEventListener("change", (event) => {   // a list box picked something: draw what waited
    if (event.target.tagName === "SELECT" && pendingRender) setTimeout(() => render(true), 0);
  });
  $("ventures-screen").addEventListener("keydown", (event) => {
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName) && event.target.type !== "radio";
    if (event.key === "Escape" && !$("groups-confirm").open && !typing && !event.defaultPrevented && !event.isComposing) {
      event.preventDefault();
      if (view) showHome(); else close();
    }
  });
}
