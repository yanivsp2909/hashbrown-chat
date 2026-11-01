// 🏢 One company's HQ on the Ventures screen: cash and runway up front, the other numbers with small charts, today's
// actions, the funding timeline, the cap table pie, the team (and invites), angels, the daily reports and the sector
// panel (venturessector.js). The pitch room and the term sheet are in venturespitch.js. Members get everything;
// everyone else sees the public part and can invest.

import { el, str } from "./dom.js";
import { getState } from "./store.js";
import * as V from "./ventureslogic.js";
import { act, backHome, button, confirmStep, draft, newsList, render, setDraft } from "./ventures.js";
import { pitchRoom } from "./venturespitch.js";
import { sectorPanel } from "./venturessector.js";
import { dealsInbox, dealsWith, ipoPanel, marketPanel } from "./venturesdeals.js";

const SVG = "http://www.w3.org/2000/svg";

/** An SVG element (dom.js's el makes HTML ones). */
export function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) if (value !== undefined) node.setAttribute(key, String(value));
  node.append(...children);
  return node;
}

/** A text box whose typing survives the screen's redraws. */
export function field(key, props = {}) {
  return el("input", { class: "input", "data-focus": key, value: draft(key), autocomplete: "off", ...props,
    oninput: (e) => setDraft(key, e.target.value) });
}

/** A short visible error under a form (and in the tab order's description), or null. */
export function formError(key) {
  const text = draft(`${key}-error`);
  return text ? el("p", { id: `${key}-error`, class: "vs-error", text }) : null;
}

export const hidden = (text) => el("span", { class: "visually-hidden", text });

export function renderHq(co, home) {
  const names = (getState().online || []).map((p) => str(p.name)).filter((n) => !co.team.some((t) => t.name === n));
  const parts = [head(co), statusLine(co), el("datalist", { id: "vs-online-names" }, ...names.map((n) => el("option", { value: n })))];
  if (co.member && co.status !== "alive") {   // ⚰️ a closed company: its story, no buttons
    parts.push(lead(co), numbers(co), el("div", { class: "vs-columns" },
      el("div", { class: "vs-col" }, reports(co), companyNews(co)), el("div", { class: "vs-col" }, funding(co), capTable(co), team(co, home))));
  } else if (co.member) {
    parts.push(dealsInbox(co), lead(co), numbers(co), el("div", { class: "vs-columns" },
      el("div", { class: "vs-col" }, today(co), pitchRoom(co), sectorPanel(co), reports(co)),
      el("div", { class: "vs-col" }, ipoPanel(co), funding(co), marketPanel(co), capTable(co), team(co, home), angels(co),
        companyNews(co), dangerZone(co))));
  } else {
    parts.push(el("div", { class: "vs-columns" },
      el("div", { class: "vs-col" }, outsiderNumbers(co), ipoPanel(co), invest(co), dealsWith(co), funding(co), companyNews(co)),
      el("div", { class: "vs-col" }, capTable(co), team(co, home))));
  }
  return parts;
}

function head(co) {
  return el("div", { class: "gs-head vs-hq-head" },
    el("button", { class: "icon-btn", type: "button", "aria-label": "Back to Ventures", "data-focus": "back", onclick: backHome, text: "←" }),
    el("span", { class: "vs-icon", "aria-hidden": "true", text: str(co.icon) }),
    el("h2", { id: "ventures-title", class: "gs-title", tabindex: "-1", text: str(co.name) }),
    el("span", { class: "vs-pill", text: str(co.stage_name) }));
}

function statusLine(co) {
  if (co.status === "dead") return el("p", { class: "vs-banner vs-banner-dead", text: `⚰️ ${str(co.name)} died: ${str(co.cause)}.` });
  if (co.status === "shutdown") return el("p", { class: "vs-banner vs-banner-dead", text: `🪦 ${str(co.name)} was shut down.` });
  if (co.status === "acquired") return el("p", { class: "vs-banner vs-banner-dead", text: `🤝 ${str(co.name)} was ${str(co.cause)}. A happy ending!` });
  if (co.status === "ended") return el("p", { class: "vs-banner vs-banner-dead", text: `🏛️ ${str(co.name)}'s season is over (${str(co.cause)}).` });
  if (co.fumes) return el("p", { class: "vs-banner vs-banner-fumes",
    text: "🚨 Out of cash: on fumes! Raise money (pitch or bridge) or cut costs before the next game day, or the company dies." });
  const events = Array.isArray(co.events) ? co.events : [];
  return el("div", { class: "vs-status" },
    el("p", { class: "gs-muted", text: `${str(co.sector_name)} · day ${str(co.age)} · ${str(co.stage_ticks)} days in ${str(co.stage_name)}` }),
    ...events.map((e) => el("span", { class: "vs-chip vs-chip-event", dir: "auto", text: `🌪️ ${str(e.headline)}` })));
}

// ---------------------------------------------------------------- the numbers

function sparkline(label, series, money = false) {
  const shape = series ? V.chart(series) : null;
  if (!shape) return null;
  const show = (v) => (money ? V.money(v) : V.whole(v));
  return svg("svg", { class: `vs-spark${money ? " vs-spark-money" : ""}`, viewBox: "0 0 120 36", preserveAspectRatio: "none", role: "img",
    "aria-label": `${label} over the last ${series.length} days: from ${show(shape.first)} to ${show(shape.last)}` },
  svg("path", { d: shape.area, class: "vs-spark-area" }), svg("path", { d: shape.path, class: "vs-spark-line" }));
}

/** Cash and runway first: the question every founder asks ("am I about to die?"). */
function lead(co) {
  const n = co.numbers || {};
  const runway = n.runway;
  const short = runway !== null && runway !== undefined && runway < 5;
  return el("section", { class: `vs-plate vs-lead${short || n.cash < 0 ? " vs-lead-danger" : ""}`, "aria-label": "Cash and runway" },
    el("div", { class: "vs-lead-cash" },
      el("span", { class: "vs-big-label", text: "Cash" }), el("span", { class: "vs-big", text: V.money(n.cash) }),
      el("span", { class: "vs-tile-note", text: `burn ${V.money(n.burn)} a day · revenue ${V.money(n.revenue)} a day` })),
    el("div", { class: "vs-lead-runway" },
      el("span", { class: "vs-big-label", text: "Runway" }),
      el("span", { class: "vs-big", text: runway === null || runway === undefined ? "∞" : V.plural(runway, "day") }),
      el("span", { class: "vs-tile-note", text: runway === null || runway === undefined ? "profitable" : short ? "⚠️ raise money soon" : "at today's speed" })),
    sparkline("Cash", co.history.map((d) => d.cash), true));
}

function tile(label, value, { series = null, money = false, note = "" } = {}) {
  return el("div", { class: "vs-tile" },
    el("span", { class: "vs-tile-label", text: label }),
    el("span", { class: "vs-tile-value", text: value }),
    note ? el("span", { class: "vs-tile-note", text: note }) : null,
    sparkline(label, series, money));
}

const cap1 = (text) => str(text).charAt(0).toUpperCase() + str(text).slice(1);

function numbers(co) {
  const n = co.numbers || {};
  const col = (name) => co.history.map((d) => d[name]);
  return el("section", { class: "vs-tiles", "aria-label": "The numbers" },
    tile("Revenue a day", V.money(n.revenue), { series: col("revenue"), money: true }),
    tile(cap1(co.customer_word), V.whole(n.customers)),
    tile("Quality", `${Math.round(n.quality)}/100`),
    tile("Hype", `${Math.round(n.hype)}/100`, { note: `reputation ${Math.round(n.reputation)}` }),
    tile("Team", V.plural(n.staff_total, "employee"), { note: `of ${str(n.staff_max)} at this stage` }),
    tile("Valuation", V.money(co.valuation), { series: col("valuation"), money: true }));
}

function outsiderNumbers(co) {
  return el("section", { class: "vs-tiles", "aria-label": "Public numbers" },
    tile("Valuation", V.money(co.valuation)), tile("Raised", V.money(co.raised)), tile("Peak", V.money(co.peak)));
}

// ---------------------------------------------------------------- today

const ICONS = { build: "⭐", hire: "👥", layoff: "✂️", marketing: "📣", sales: "🤝", pr: "📰", pivot: "🔀" };

function today(co) {
  const common = co.actions.filter((a) => !a.sector);
  return el("section", { class: "vs-panel", "aria-labelledby": "vs-today" },
    el("div", { class: "vs-panel-head" },
      el("h3", { id: "vs-today", class: "gs-h3", text: "⚡ Today" }),
      el("span", { class: "vs-ap" },
        ...Array.from({ length: Number(co.ap_max) || 6 }, (_, i) => el("span", { class: `vs-ap-dot${i < co.ap ? " on" : ""}`, "aria-hidden": "true" })),
        el("span", { text: ` ${co.ap} of ${co.ap_max} action points left` }))),
    el("p", { class: "gs-muted", text: `They refill when the next game day starts, ${V.countdown(co.next_tick)}. Unused ones are lost.` }),
    co.status === "alive" ? el("ul", { class: "vs-actions" }, ...common.map((a) => actionRow(co, a))) : el("p", { class: "gs-empty", text: "This company is closed." }));
}

function costText(a) {
  return `${a.ap} ⚡${Number(a.cost) ? ` · ${V.money(a.cost)}` : ""}`;
}

/** One action: its name, what it does, the cost and its button(s). Sector panels use it too. */
const LABELS = { pr: "PR", priceup: "Raise the price", pricedown: "Lower the price", newmodel: "New model",
  liveops: "Live ops", dlc: "DLC", compute: "Buy compute", manufacture: "Manufacture" };

export function actionRow(co, a, icon = ICONS[str(a.name)] || "•") {
  const name = str(a.name);
  const label = LABELS[name] || cap1(name);
  a = { ...a, why: str(a.why).startsWith("⚡") ? "No action points left today." : a.why };
  const key = `act:${name}`;
  const whyId = a.why ? `why-act-${name}` : undefined;
  let controls;
  if (name === "hire") {
    controls = el("div", { class: "row" }, ...a.choices.map((kind) => button(`+ ${cap1(kind)}`,
      () => act(`${key}:${kind}`, V.actionLine("hire", kind)), { key: `${key}:${kind}`, small: true, disabled: !a.ok, label: `Hire ${kind}` })));
  } else if (name === "layoff") {
    const pick = el("select", { class: "input input-small", "data-focus": "layoff-kind", "aria-label": "Who to let go",
      onchange: (e) => setDraft("layoff-kind", e.target.value) },
    ...a.choices.map((kind) => el("option", { value: kind, selected: draft("layoff-kind") === kind, text: cap1(kind) })));
    controls = el("div", { class: "row" }, pick, button("Let go 1", () => act(key,
      V.actionLine("layoff", draft("layoff-kind") || a.choices[0], 1)), { key, small: true, disabled: !a.ok || !a.choices.length, label: "Let one person go" }));
  } else if (name === "pivot") {
    const pick = el("select", { class: "input input-small", "data-focus": "pivot-sector", "aria-label": "Pivot to which sector",
      onchange: (e) => setDraft("pivot-sector", e.target.value) },
    ...a.choices.map((sector) => el("option", { value: sector, selected: (draft("pivot-sector") || co.sector) === sector, text: sector })));
    controls = el("div", { class: "row" }, pick, button("Pivot…", () => pivot(co), { key, small: true, disabled: !a.ok }));
  } else if (a.choices && a.choices.length) {   // a sector action with a choice (like a cyber product line)
    controls = el("div", { class: "row" }, ...a.choices.map((choice) => button(cap1(choice),
      () => act(`${key}:${choice}`, V.actionLine(name, choice)), { key: `${key}:${choice}`, small: true, disabled: !a.ok, label: `${label}: ${choice}` })));
  } else {
    controls = button("Do it", () => act(key, V.actionLine(name, a.arg || "")), { key, small: true, disabled: !a.ok, label: `${label}: ${str(a.help).replace(/^\S+\s/, "")}` });
  }
  const wide = ["hire", "layoff", "pivot"].includes(name) || (a.choices && a.choices.length > 1);
  return el("li", { class: `vs-action${a.ok ? "" : " off"}${wide ? " vs-action-wide" : ""}`, "aria-describedby": whyId },
    el("div", { class: "vs-action-main" },
      el("span", { class: "vs-action-name" }, el("span", { "aria-hidden": "true", text: `${icon} ` }), label),
      el("span", { class: "vs-action-help", text: str(a.help).replace(/^\S+\s/, "") }),
      a.why ? el("span", { id: whyId, class: "vs-why", text: str(a.why) }) : null),
    el("span", { class: "vs-cost", text: costText(a) }), controls);
}

async function pivot(co) {
  const sector = draft("pivot-sector") || co.sector;
  const ok = await confirmStep({ title: "🔀 Pivot?", text: `Start over on a new idea (${sector}), once per stage: quality halves, ` +
    `hype resets and most ${str(co.customer_word)} leave. It costs 3 action points.`, yes: "Pivot" });
  if (ok) act("act:pivot", V.actionLine("pivot", sector));
}

// ---------------------------------------------------------------- money: the timeline, the cap table, angels

const STAGE_WORDS = { done: " (done)", now: " (now)", next: " (next)", later: "" };

function funding(co) {
  const steps = el("ol", { class: "vs-timeline", "aria-label": "Funding stages", tabindex: "0" }, ...co.timeline.map((t) => el("li", {
    class: `vs-stage vs-stage-${str(t.state)}`, "aria-current": t.state === "now" ? "step" : undefined },
  el("span", { class: "vs-stage-dot", "aria-hidden": "true", text: t.state === "done" ? "✓" : "" }),
  el("span", { class: "vs-stage-name", "aria-hidden": "true", text: str(t.name).replace("Series ", "") }),
  hidden(`${str(t.name)}${STAGE_WORDS[t.state] || ""}`))));
  const needs = co.member && co.milestones.length ? el("ul", { class: "vs-needs", "aria-label": "What the next stage needs" },
    ...co.milestones.map((m) => el("li", { class: m.ok ? "ok" : "" }, hidden(m.ok ? "Done: " : "Not yet: "), str(m.text)))) : null;
  const rounds = co.rounds.length ? el("ul", { class: "vs-list vs-rounds" }, ...co.rounds.map((r) => el("li", {},
    el("span", { class: "vs-row-name", text: `${str(r.stage_name)}: ${V.money(r.amount)}` }),
    el("span", { class: "vs-row-sub", text: ` from ${str(r.investor_name)} for ${V.percent(r.bp)} (valued ${V.money(r.post)})` })))) : null;
  return el("section", { class: "vs-panel", "aria-labelledby": "vs-funding" },
    el("h3", { id: "vs-funding", class: "gs-h3", text: "🧭 Funding" }), steps,
    needs ? el("h4", { class: "gs-h4", text: "The next round needs" }) : null, needs,
    co.member && co.interest && co.interest.text ? el("p", { class: `vs-interest vs-interest-${str(co.interest.level)}`, text: `Investor interest: ${str(co.interest.text)}` }) : null,
    rounds, co.member && co.status === "alive" ? bridge(co) : null);
}

function bridge(co) {
  const b = co.bridge || {};
  if (!b.amount) return null;
  const go = async () => {
    if (await confirmStep({ title: "🌉 Take the bridge round?", text: `Bridge Capital gives ${V.money(b.amount)} for ${V.percent(b.bp)} of the company. ` +
      "Once per stage; it doesn't move you to the next stage.", yes: "Take it" })) act("bridge", "/company bridge");
  };
  return el("div", { class: "vs-bridge" }, button(`🌉 Bridge round: ${V.money(b.amount)} for ${V.percent(b.bp)}`,
    go, { key: "bridge", small: true, disabled: !b.ok, why: str(b.why) }));
}

const SLICE_CLASSES = ["s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7"];

function capTable(co) {
  const slices = V.pie(co.cap);
  return el("section", { class: "vs-panel", "aria-labelledby": "vs-cap" },
    el("h3", { id: "vs-cap", class: "gs-h3", text: "🥧 Who owns it" }),
    el("div", { class: "vs-cap" },
      svg("svg", { class: "vs-pie", viewBox: "0 0 100 100", "aria-hidden": "true" },
        ...slices.map((s, i) => svg("path", { d: s.path, class: `vs-slice ${SLICE_CLASSES[i % 8]}` }))),
      el("table", { class: "vs-cap-table" },
        el("caption", { class: "visually-hidden", text: "Owners and their share" }),
        el("thead", { class: "visually-hidden" }, el("tr", {}, el("th", { scope: "col", text: "Owner" }), el("th", { scope: "col", text: "Share" }))),
        el("tbody", {}, ...co.cap.map((r, i) => el("tr", {},
          el("th", { scope: "row" }, el("span", { class: `vs-key ${SLICE_CLASSES[i % 8]}`, "aria-hidden": "true" }), str(r.name)),
          el("td", { class: "num", text: V.percent(r.bp) })))))));
}

function invest(co) {
  const you = co.you || {};
  const parts = [el("h3", { id: "vs-angel", class: "gs-h3", text: "😇 Invest as an angel" })];
  if (you.angel_waiting) {
    parts.push(el("p", { text: `⏳ Your ${you.angel_waiting.tokens} 🪙 offer (${V.percent(you.angel_waiting.bp)}) is waiting for the CEO.` }),
      button("Take it back", () => act("invest-cancel", `/invest cancel ${co.name}`), { key: "invest-cancel", small: true }));
  } else if (you.can_invest) {
    const send = () => {
      const amount = Number(draft("invest-amount"));
      if (!Number.isInteger(amount) || amount < you.invest_min || amount > you.invest_max) {
        setDraft("invest-amount-error", `Type a whole number of tokens from ${you.invest_min} to ${you.invest_max}.`);
        render();
        document.getElementById("vs-invest-amount")?.focus();
        return;
      }
      setDraft("invest-amount-error", "");
      act("invest", V.investLine(co.name, amount));
    };
    const error = draft("invest-amount-error");
    const amount = field("invest-amount", { type: "number", min: String(you.invest_min), max: String(you.invest_max), inputmode: "numeric",
      id: "vs-invest-amount", "aria-describedby": error ? "invest-amount-error vs-invest-hint" : "vs-invest-hint", "aria-invalid": error ? "true" : undefined });
    parts.push(el("label", { for: "vs-invest-amount", class: "gs-h4", text: "Tokens to put in" }),
      el("div", { class: "row" }, amount, button("😇 Offer", send, { key: "invest", primary: true, label: `Offer tokens to ${str(co.name)}` })),
      formError("invest-amount"),
      el("p", { id: "vs-invest-hint", class: "gs-muted", text: `${you.invest_min}-${you.invest_max} 🪙. The CEO says yes or no; ` +
        "the tokens are held until then and come back if they say no or don't answer in 24 h." }));
  } else {
    parts.push(el("p", { class: "gs-muted", text: str(you.invest_why) }));
  }
  if (you.bp) parts.push(el("p", { class: "vs-own", text: `You own ${V.percent(you.bp)} of ${str(co.name)}.` }));
  return el("section", { class: "vs-panel", "aria-labelledby": "vs-angel" }, ...parts);
}

function angels(co) {
  if (!co.angels.length) return null;
  const ceo = co.you && co.you.ceo;
  const accept = async (a) => {
    if (await confirmStep({ title: `😇 Take ${str(a.name)}'s money?`, text: `${a.tokens} 🪙 become ${V.money(a.dollars)} of cash, and ` +
      `${str(a.name)} gets ${V.percent(a.bp)} of the company (everyone else shrinks a little).`, yes: "Accept" })) {
      act(`angel:${a.name}`, V.angelLine(true, str(a.name)));
    }
  };
  return el("section", { class: "vs-panel", "aria-labelledby": "vs-angels" },
    el("h3", { id: "vs-angels", class: "gs-h3", text: "😇 Angel offers" }),
    el("ul", { class: "vs-list" }, ...co.angels.map((a) => el("li", { class: "vs-row vs-row-static" },
      el("span", { class: "vs-row-main" }, el("span", { class: "vs-row-name", text: str(a.name) }),
        el("span", { class: "vs-row-sub", text: `${a.tokens} 🪙 = ${V.money(a.dollars)} for ${V.percent(a.bp)}` })),
      ceo ? el("span", { class: "row" },
        button("Accept", () => accept(a), { key: `angel:${a.name}`, small: true, label: `Accept ${str(a.name)}'s offer` }),
        button("Decline", () => act(`angel-no:${a.name}`, V.angelLine(false, str(a.name))), { key: `angel-no:${a.name}`, small: true, label: `Decline ${str(a.name)}'s offer` }))
        : el("span", { class: "vs-row-sub", text: "The CEO decides" })))));
}

// ---------------------------------------------------------------- the team

function team(co, home) {
  const you = co.you || {};
  const rows = co.team.map((t) => el("li", { class: "vs-member" },
    el("span", { class: `vs-dot${t.online ? " on" : ""}`, "aria-hidden": "true" }),
    el("span", { class: "vs-row-name" }, str(t.name), hidden(t.online ? " (online)" : " (offline)")),
    el("span", { class: "vs-row-sub", text: str(t.role_title) }),
    el("span", { class: "num", text: Number(t.bp) ? V.percent(t.bp) : "" })));
  return el("section", { class: "vs-panel", "aria-labelledby": "vs-team" },
    el("h3", { id: "vs-team", class: "gs-h3", text: "👥 Team" }),
    el("ul", { class: "vs-list vs-team" }, ...rows),
    co.member && you.c_level && co.status === "alive" ? inviteForm(co, home, you) : null,
    co.member && co.invites_out.length ? el("p", { class: "gs-muted", text: "⏳ Invited: " + co.invites_out.map((i) =>
      `${str(i.name)} (${str(i.role)}${Number(i.bp) ? ` ${V.percent(i.bp)}` : ""})`).join(", ") }) : null);
}

function inviteForm(co, home, you) {
  const roles = (home ? home.roles : []).filter((r) => r.key !== "ceo" && (you.ceo || !r.c_level));
  const role = draft("invite-role") || "engineer";
  const error = draft("invite-name-error");
  return el("form", { class: "vs-invite", "aria-label": "Invite someone", onsubmit: (e) => {
    e.preventDefault();
    const name = draft("invite-name").trim();
    if (!name) {
      setDraft("invite-name-error", "Type the name of the person to invite.");
      render();
      document.getElementById("vs-invite-name")?.focus();
      return;
    }
    setDraft("invite-name-error", "");
    act("invite", V.inviteLine(name, role, you.ceo ? V.readPercent(draft("invite-pct") || "0") || 0 : 0));
  } },
  el("label", { for: "vs-invite-name", class: "gs-h4", text: "Invite a co-founder" }),
  el("div", { class: "vs-invite-row" },
    field("invite-name", { id: "vs-invite-name", placeholder: "Their name", maxlength: "16", list: "vs-online-names",
      "aria-invalid": error ? "true" : undefined, "aria-describedby": error ? "invite-name-error" : undefined }),
    el("select", { class: "input", "data-focus": "invite-role", "aria-label": "Role", onchange: (e) => setDraft("invite-role", e.target.value) },
      ...roles.map((r) => el("option", { value: r.key, selected: r.key === role, text: `${str(r.icon)} ${str(r.name)}` }))),
    you.ceo ? field("invite-pct", { type: "number", min: "0", max: "100", step: "0.5", placeholder: "Equity %", "aria-label": "Equity percent (from your shares)" }) : null,
    el("button", { class: "btn btn-primary btn-small", type: "submit", "data-focus": "invite", text: "📨 Invite" })),
  formError("invite-name"),
  el("p", { class: "gs-muted", text: you.ceo ? "Equity comes from your own shares and vests over 28 days." : "Only the CEO gives C-level seats and equity." }));
}

// ---------------------------------------------------------------- the rest

function reports(co) {
  const [newest, ...older] = co.reports;
  return el("section", { class: "vs-panel", "aria-labelledby": "vs-reports" },
    el("h3", { id: "vs-reports", class: "gs-h3", text: "📊 Daily reports" }),
    newest ? el("pre", { class: "vs-report vs-report-new", tabindex: "0", text: str(newest.text) })
      : el("p", { class: "gs-empty", text: `The first report comes when the next game day starts, ${V.countdown(co.next_tick)}.` }),
    older.length ? detailsKeep("older-reports", `Older reports (${older.length})`,
      el("ol", { class: "vs-reports" }, ...older.map((r) => el("li", {}, el("pre", { class: "vs-report", text: str(r.text) }))))) : null);
}

/** A <details> whose open/closed state survives the redraws. */
export function detailsKeep(key, summary, ...children) {
  return el("details", { class: "vs-details", open: draft(`open:${key}`) === "1",
    ontoggle: (e) => setDraft(`open:${key}`, e.target.open ? "1" : "") },
  el("summary", { "data-focus": `sum:${key}`, text: summary }), ...children);
}

function companyNews(co) {
  const news = Array.isArray(co.news) ? co.news : [];
  if (!news.length) return null;
  return el("section", { class: "vs-panel", "aria-labelledby": "vs-co-news" },
    el("h3", { id: "vs-co-news", class: "gs-h3", text: "📰 In the news" }), newsList(news));
}

function dangerZone(co) {
  if (co.status !== "alive") return null;
  const you = co.you || {};
  const leave = async () => {
    if (await confirmStep({ title: `Leave ${co.name}?`, text: "You keep the shares that have vested; the rest go back.", yes: "Leave", danger: true })) {
      act("leave", "/company leave");
    }
  };
  const shut = async () => {
    if (await confirmStep({ title: `Shut down ${co.name}?`, text: "It goes to the graveyard for good. Type its name to be sure.",
      yes: "Shut it down", requireText: co.name, label: "Company name", danger: true })) {
      act("shutdown", `/company shutdown ${co.name}`);
    }
  };
  return el("section", { class: "vs-panel vs-danger", "aria-labelledby": "vs-danger" },
    el("h3", { id: "vs-danger", class: "gs-h3", text: "Leaving" }),
    you.ceo ? button("🪦 Shut down the company…", shut, { key: "shutdown", danger: true, small: true })
      : button("👋 Leave the company…", leave, { key: "leave", danger: true, small: true }));
}
