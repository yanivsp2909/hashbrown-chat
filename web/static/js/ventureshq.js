// 🏢 One company's HQ on the Ventures screen: the numbers with small charts, today's actions, the funding timeline,
// the cap table pie, the team (and invites), angels, the daily reports and the sector panel. The pitch room and the
// term sheet are in venturespitch.js. Members get everything; everyone else sees the public part and can invest.

import { el, str } from "./dom.js";
import { getState } from "./store.js";
import * as V from "./ventureslogic.js";
import { act, backHome, button, confirmStep, draft, setDraft } from "./ventures.js";
import { pitchRoom } from "./venturespitch.js";

const SVG = "http://www.w3.org/2000/svg";

/** An SVG element (dom.js's el makes HTML ones). */
function svg(tag, attrs = {}, ...children) {
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

export function renderHq(co, home) {
  const names = (getState().online || []).map((p) => str(p.name)).filter((n) => !co.team.some((t) => t.name === n));
  const parts = [head(co), statusLine(co), el("datalist", { id: "vs-online-names" }, ...names.map((n) => el("option", { value: n })))];
  if (co.member) {
    parts.push(numbers(co), el("div", { class: "vs-columns" },
      el("div", { class: "vs-col" }, today(co), pitchRoom(co), sectorPanel(co), reports(co)),
      el("div", { class: "vs-col" }, funding(co), capTable(co), team(co, home), angels(co), dangerZone(co))));
  } else {
    parts.push(el("div", { class: "vs-columns" },
      el("div", { class: "vs-col" }, outsiderNumbers(co), invest(co), funding(co)),
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
  if (co.status === "dead") return el("p", { class: "vs-banner vs-banner-dead", role: "status", text: `⚰️ ${str(co.name)} died: ${str(co.cause)}.` });
  if (co.status === "shutdown") return el("p", { class: "vs-banner vs-banner-dead", role: "status", text: `🪦 ${str(co.name)} was shut down.` });
  if (co.fumes) return el("p", { class: "vs-banner vs-banner-fumes", role: "alert",
    text: "🚨 Out of cash: on fumes! Raise money (pitch or bridge) or cut costs before the next game day, or the company dies." });
  return el("p", { class: "gs-muted", text: `${str(co.sector_name)} · day ${str(co.age)} · ${str(co.stage_ticks)} days in ${str(co.stage_name)}` });
}

// ---------------------------------------------------------------- the numbers

function tile(label, value, { series = null, tone = "", note = "" } = {}) {
  const shape = series ? V.chart(series) : null;
  return el("div", { class: `vs-tile${tone ? ` vs-tone-${tone}` : ""}` },
    el("span", { class: "vs-tile-label", text: label }),
    el("span", { class: "vs-tile-value", text: value }),
    note ? el("span", { class: "vs-tile-note", text: note }) : null,
    shape ? svg("svg", { class: "vs-spark", viewBox: "0 0 120 36", role: "img",
      "aria-label": `${label} over the last ${series.length} days: from ${tileValue(label, shape.first)} to ${tileValue(label, shape.last)}` },
    svg("path", { d: shape.area, class: "vs-spark-area" }), svg("path", { d: shape.path, class: "vs-spark-line" })) : null);
}

function tileValue(label, v) {
  return ["Cash", "Revenue a day", "Valuation"].includes(label) ? V.money(v) : V.whole(v);
}

function numbers(co) {
  const n = co.numbers || {};
  const h = co.history;
  const col = (name) => h.map((d) => d[name]);
  const runway = n.runway;
  const short = runway !== null && runway !== undefined && runway < 5;
  return el("section", { class: "vs-tiles", "aria-label": "The numbers" },
    tile("Cash", V.money(n.cash), { series: col("cash"), tone: n.cash < 0 ? "danger" : "" }),
    tile("Burn a day", V.money(n.burn), { note: `${V.plural(n.staff_total, "employee")} of ${str(n.staff_max)}` }),
    tile("Runway", V.runwayText(runway), { tone: short ? "danger" : runway === null ? "good" : "" }),
    tile("Revenue a day", V.money(n.revenue), { series: col("revenue") }),
    tile(cap1(co.customer_word), V.whole(n.customers), { series: col("customers") }),
    tile("Quality", `${Math.round(n.quality)}/100`, { series: col("quality") }),
    tile("Hype", `${Math.round(n.hype)}/100`, { series: col("hype"), note: `reputation ${Math.round(n.reputation)}` }),
    tile("Valuation", V.money(co.valuation), { series: col("valuation") }));
}

const cap1 = (text) => str(text).charAt(0).toUpperCase() + str(text).slice(1);

function outsiderNumbers(co) {
  return el("section", { class: "vs-tiles vs-tiles-small", "aria-label": "Public numbers" },
    tile("Valuation", V.money(co.valuation)), tile("Raised", V.money(co.raised)), tile("Peak", V.money(co.peak)));
}

// ---------------------------------------------------------------- today

const ICONS = { build: "⭐", hire: "👥", layoff: "✂️", marketing: "📣", sales: "🤝", pr: "📰", pivot: "🔀" };

function today(co) {
  const rows = co.actions.map((a) => actionRow(co, a));
  return el("section", { class: "vs-panel", "aria-labelledby": "vs-today" },
    el("div", { class: "vs-panel-head" },
      el("h3", { id: "vs-today", class: "gs-h3", text: "⚡ Today" }),
      el("span", { class: "vs-ap", "aria-label": `${co.ap} of ${co.ap_max} action points left` },
        ...Array.from({ length: Number(co.ap_max) || 6 }, (_, i) => el("span", { class: `vs-ap-dot${i < co.ap ? " on" : ""}`, "aria-hidden": "true" })),
        el("span", { "aria-hidden": "true", text: ` ${co.ap} left` }))),
    el("p", { class: "gs-muted", text: `Action points refill when the next game day starts, ${V.countdown(co.next_tick)}. Unused ones are lost.` }),
    co.status === "alive" ? el("ul", { class: "vs-actions" }, ...rows) : el("p", { class: "gs-empty", text: "This company is closed." }));
}

function costText(a) {
  return `${a.ap} ⚡${Number(a.cost) ? ` · ${V.money(a.cost)}` : ""}`;
}

function actionRow(co, a) {
  const name = str(a.name);
  const label = `${ICONS[name] || "•"} ${cap1(name === "pr" ? "PR" : name)}`;
  const key = `act:${name}`;
  let controls;
  if (name === "hire") {
    controls = el("div", { class: "row" }, ...a.choices.map((kind) => button(`+ ${cap1(kind)}`,
      () => act(`${key}:${kind}`, V.actionLine("hire", kind)), { key: `${key}:${kind}`, small: true, disabled: !a.ok })));
  } else if (name === "layoff") {
    const pick = el("select", { class: "input input-small", "data-focus": "layoff-kind", "aria-label": "Who to let go",
      onchange: (e) => setDraft("layoff-kind", e.target.value) },
    ...a.choices.map((kind) => el("option", { value: kind, selected: draft("layoff-kind") === kind, text: cap1(kind) })));
    controls = el("div", { class: "row" }, pick, button("Let go 1", () => act(key,
      V.actionLine("layoff", draft("layoff-kind") || a.choices[0], 1)), { key, small: true, disabled: !a.ok || !a.choices.length }));
  } else if (name === "pivot") {
    const pick = el("select", { class: "input input-small", "data-focus": "pivot-sector", "aria-label": "Pivot to which sector",
      onchange: (e) => setDraft("pivot-sector", e.target.value) },
    ...a.choices.map((sector) => el("option", { value: sector, selected: (draft("pivot-sector") || co.sector) === sector, text: sector })));
    controls = el("div", { class: "row" }, pick, button("Pivot…", () => pivot(co), { key, small: true, disabled: !a.ok }));
  } else {
    controls = button("Do it", () => act(key, V.actionLine(name)), { key, small: true, primary: a.ok, disabled: !a.ok });
  }
  const wide = ["hire", "layoff", "pivot"].includes(name);
  return el("li", { class: `vs-action${a.ok ? "" : " off"}${wide ? " vs-action-wide" : ""}` },
    el("div", { class: "vs-action-main" },
      el("span", { class: "vs-action-name", text: label }),
      el("span", { class: "vs-action-help", text: str(a.help).replace(/^\S+\s/, "") }),
      a.why ? el("span", { class: "vs-why", text: str(a.why) }) : null),
    el("span", { class: "vs-cost", text: costText(a) }), controls);
}

async function pivot(co) {
  const sector = draft("pivot-sector") || co.sector;
  const ok = await confirmStep({ title: "🔀 Pivot?", text: `Start over on a new idea (${sector}), once per stage: quality halves, ` +
    `hype resets and most ${str(co.customer_word)} leave. It costs 3 action points.`, yes: "Pivot" });
  if (ok) act("act:pivot", V.actionLine("pivot", sector));
}

// ---------------------------------------------------------------- money: the timeline, the cap table, angels

function funding(co) {
  const steps = el("ol", { class: "vs-timeline", "aria-label": "Funding stages" }, ...co.timeline.map((t) => el("li", {
    class: `vs-stage vs-stage-${str(t.state)}`, "aria-current": t.state === "now" ? "step" : undefined },
  el("span", { class: "vs-stage-dot", "aria-hidden": "true", text: t.state === "done" ? "✓" : "" }),
  el("span", { class: "vs-stage-name", text: str(t.name) }))));
  const needs = co.member && co.milestones.length ? el("ul", { class: "vs-needs", "aria-label": "What the next stage needs" },
    ...co.milestones.map((m) => el("li", { class: m.ok ? "ok" : "", text: str(m.text) }))) : null;
  const rounds = co.rounds.length ? el("ul", { class: "vs-list vs-rounds" }, ...co.rounds.map((r) => el("li", {},
    el("span", { class: "vs-row-name", text: `${str(r.stage_name)}: ${V.money(r.amount)}` }),
    el("span", { class: "vs-row-sub", text: ` from ${str(r.investor_name)} for ${V.percent(r.bp)} (valued ${V.money(r.post)})` })))) : null;
  return el("section", { class: "vs-panel", "aria-labelledby": "vs-funding" },
    el("h3", { id: "vs-funding", class: "gs-h3", text: "🧭 Funding" }), steps,
    needs ? el("h4", { class: "gs-h4", text: "The next round needs" }) : null, needs,
    co.member && co.interest && co.interest.text ? el("p", { class: `vs-interest vs-interest-${str(co.interest.level)}`, text: `Investor interest: ${str(co.interest.text)}` }) : null,
    rounds, co.member ? bridge(co) : null);
}

function bridge(co) {
  const b = co.bridge || {};
  if (!b.amount) return null;
  return el("div", { class: "vs-bridge" }, button(`🌉 Bridge round: ${V.money(b.amount)} for ${V.percent(b.bp)}`,
    () => act("bridge", "/company bridge"), { key: "bridge", small: true, disabled: !b.ok, why: str(b.why) }));
}

const SLICE_CLASSES = ["s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7"];

function capTable(co) {
  const slices = V.pie(co.cap);
  const label = co.cap.map((r) => `${str(r.name)} ${V.percent(r.bp)}`).join(", ");
  return el("section", { class: "vs-panel", "aria-labelledby": "vs-cap" },
    el("h3", { id: "vs-cap", class: "gs-h3", text: "🥧 Who owns it" }),
    el("div", { class: "vs-cap" },
      svg("svg", { class: "vs-pie", viewBox: "0 0 100 100", role: "img", "aria-label": `Cap table: ${label}` },
        ...slices.map((s, i) => svg("path", { d: s.path, class: `vs-slice ${SLICE_CLASSES[i % 8]}` }))),
      el("table", { class: "vs-cap-table" },
        el("caption", { class: "visually-hidden", text: "Owners and their share" }),
        el("tbody", {}, ...co.cap.map((r, i) => el("tr", {},
          el("td", {}, el("span", { class: `vs-key ${SLICE_CLASSES[i % 8]}`, "aria-hidden": "true" }), str(r.name)),
          el("td", { class: "num", text: V.percent(r.bp) })))))));
}

function invest(co) {
  const you = co.you || {};
  const parts = [el("h3", { id: "vs-angel", class: "gs-h3", text: "😇 Invest as an angel" })];
  if (you.angel_waiting) {
    parts.push(el("p", { text: `⏳ Your ${you.angel_waiting.tokens} 🪙 offer (${V.percent(you.angel_waiting.bp)}) is waiting for the CEO.` }),
      button("Take it back", () => act("invest-cancel", `/invest cancel ${co.name}`), { key: "invest-cancel", small: true }));
  } else if (you.can_invest) {
    const amount = field("invest-amount", { type: "number", min: String(you.invest_min), max: String(you.invest_max), inputmode: "numeric",
      id: "vs-invest-amount", "aria-describedby": "vs-invest-hint" });
    parts.push(el("label", { for: "vs-invest-amount", class: "gs-h4", text: "Tokens to put in" }), el("div", { class: "row" }, amount,
      button("😇 Offer", () => act("invest", V.investLine(co.name, Number(draft("invest-amount")))), { key: "invest", primary: true })),
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
  return el("section", { class: "vs-panel", "aria-labelledby": "vs-angels" },
    el("h3", { id: "vs-angels", class: "gs-h3", text: "😇 Angel offers" }),
    el("ul", { class: "vs-list" }, ...co.angels.map((a) => el("li", { class: "vs-row vs-row-static" },
      el("span", { class: "vs-row-main" }, el("span", { class: "vs-row-name", text: str(a.name) }),
        el("span", { class: "vs-row-sub", text: `${a.tokens} 🪙 = ${V.money(a.dollars)} for ${V.percent(a.bp)}` })),
      ceo ? el("span", { class: "row" },
        button("Accept", () => act(`angel:${a.name}`, V.angelLine(true, str(a.name))), { key: `angel:${a.name}`, primary: true, small: true }),
        button("Decline", () => act(`angel-no:${a.name}`, V.angelLine(false, str(a.name))), { key: `angel-no:${a.name}`, small: true }))
        : el("span", { class: "vs-row-sub", text: "The CEO decides" })))));
}

// ---------------------------------------------------------------- the team

function team(co, home) {
  const you = co.you || {};
  const rows = co.team.map((t) => el("li", { class: "vs-member" },
    el("span", { class: `vs-dot${t.online ? " on" : ""}`, "aria-label": t.online ? "online" : "offline" }),
    el("span", { class: "vs-row-name", text: str(t.name) }),
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
  return el("form", { class: "vs-invite", "aria-label": "Invite someone", onsubmit: (e) => {
    e.preventDefault();
    const name = draft("invite-name").trim();
    if (!name) return;
    act("invite", V.inviteLine(name, role, you.ceo ? V.readPercent(draft("invite-pct") || "0") || 0 : 0));
  } },
  el("label", { for: "vs-invite-name", class: "gs-h4", text: "Invite a co-founder" }),
  el("div", { class: "vs-invite-row" },
    field("invite-name", { id: "vs-invite-name", placeholder: "Their name", maxlength: "16", list: "vs-online-names" }),
    el("select", { class: "input", "data-focus": "invite-role", "aria-label": "Role", onchange: (e) => setDraft("invite-role", e.target.value) },
      ...roles.map((r) => el("option", { value: r.key, selected: r.key === role, text: `${str(r.icon)} ${str(r.name)}` }))),
    you.ceo ? field("invite-pct", { type: "number", min: "0", max: "100", step: "0.5", placeholder: "Equity %", "aria-label": "Equity percent (from your shares)" }) : null,
    el("button", { class: "btn btn-primary btn-small", type: "submit", "data-focus": "invite", text: "📨 Invite" })),
  el("p", { class: "gs-muted", text: you.ceo ? "Equity comes from your own shares and vests over 28 days." : "Only the CEO gives C-level seats and equity." }));
}

// ---------------------------------------------------------------- the rest

function reports(co) {
  return el("section", { class: "vs-panel", "aria-labelledby": "vs-reports" },
    el("h3", { id: "vs-reports", class: "gs-h3", text: "📊 Daily reports" }),
    co.reports.length ? el("ol", { class: "vs-reports" }, ...co.reports.map((r) => el("li", {},
      el("pre", { class: "vs-report", text: str(r.text) }))))
      : el("p", { class: "gs-empty", text: `The first report comes when the next game day starts, ${V.countdown(co.next_tick)}.` }));
}

/** Step B fills this with the sector's own tools. */
function sectorPanel(co) {
  return el("section", { class: "vs-panel", "aria-labelledby": "vs-sector", id: "vs-sector-panel" },
    el("h3", { id: "vs-sector", class: "gs-h3", text: `${str(co.icon)} ${str(co.sector_name)}` }),
    el("p", { class: "gs-muted", text: `${cap1(co.customer_word)}: ${V.whole((co.numbers || {}).customers)}.` }));
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
