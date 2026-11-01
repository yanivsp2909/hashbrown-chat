// 👥 One group on the Groups screen: about, members, the 🏦 bank, the ⬆️ upgrades and (only if the server
// sent them, which it does only for that group's admins) the 🛡️ admin tools. Every button sends an existing
// /command through groups.js act(); the server checks the rights and the balance again.

import { $, el, nameClass, str } from "./dom.js";
import { getState } from "./store.js";
import * as G from "./grouplogic.js";
import { act, actKey, badge, confirmLeave, confirmStep } from "./groups.js";

const SVG = "http://www.w3.org/2000/svg";
const CHART_W = 320;
const CHART_H = 72;
const MUTE_CHOICES = [5, 15, 60];

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  node.append(...children);
  return node;
}

export function backIcon() {
  return svg("svg", { viewBox: "0 0 24 24", width: 18, height: 18, "aria-hidden": "true", fill: "none", stroke: "currentColor",
    "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round" }, svg("path", { d: "M15 6l-6 6 6 6" }));
}

const block = (id, title, ...children) => el("section", { class: "gs-block", "aria-labelledby": id },
  el("h3", { id, class: "gs-h3", text: title }), ...children);

const memberRole = (role) => ({ owner: "👑 Owner", admin: "🛡️ Admin" })[role] || "Member";

// ---------------------------------------------------------------- about and members

function about(info) {
  const lines = [];
  if (info.topic) lines.push(el("p", { class: "gs-topic", dir: "auto", text: `📌 ${str(info.topic)}` }));
  if (info.persona) lines.push(el("p", { class: "gs-persona", dir: "auto", text: `🎭 Hashbrown here is: ${str(info.persona)}` }));
  const war = info.war;
  if (war && war.against) {
    lines.push(el("p", { class: "gs-war", text: `⚔️ At war with ${str(war.against)}: ${war.us} to ${war.them}, ${Math.ceil(war.ends_in / 60)} min left` }));
  } else if (war && war.invited_by) {
    lines.push(el("p", { class: "gs-war", text: `⚔️ ${str(war.invited_by)} declared war. An admin can type /war accept to fight.` }));
  } else if (G.isMember(info.your_role)) {
    lines.push(el("p", { class: "gs-muted", text: "⚔️ No war right now." }));
  }
  return lines.length ? el("div", { class: "gs-about" }, lines) : null;
}

function memberTools(info, member, index) {
  const target = str(member.name);
  const me = getState().nick;
  if (!info.admin || target === me || member.role === "owner") return null;
  const owner = info.your_role === "owner";
  const muteId = `gs-mute-${index}`;   // (an index: old nicknames may have characters an id can't)
  const ask = (action, title, text, yes) => async () => {
    if (await confirmStep({ title, text, yes, danger: true })) act(action, info, { target });
  };
  const tools = el("div", { class: "gs-tools", role: "toolbar", "aria-label": `Manage ${target}`, onkeydown: moveInToolbar,
    onfocusin: (event) => rove(tools, event.target) },
    el("button", { class: "mini-btn gs-tool", type: "button", text: "Kick", "aria-label": `Kick ${target}`, "data-act": actKey("kick", info, target),
      onclick: ask("kick", `Kick ${target}?`, `${target} leaves ${str(info.name)} but can join again.`, "Kick") }),
    el("label", { class: "visually-hidden", for: muteId, text: `Mute ${target} for how many minutes` }),
    el("select", { id: muteId, class: "gs-select" }, MUTE_CHOICES.map((m) => el("option", { value: String(m), text: `${m} min` }))),
    el("button", { class: "mini-btn gs-tool", type: "button", text: "Mute", "aria-label": `Mute ${target}`, "data-act": actKey("mute", info, target),
      onclick: () => act("mute", info, { target, value: $(muteId).value }) }),
    el("button", { class: "mini-btn gs-tool gs-danger", type: "button", text: "Ban", "aria-label": `Ban ${target}`, "data-act": actKey("ban", info, target),
      onclick: ask("ban", `Ban ${target}?`, `${target} is kicked and can't come back until an admin unbans them.`, "Ban") }),
    owner ? el("button", { class: "mini-btn gs-tool", type: "button", text: member.role === "admin" ? "Demote" : "Promote",
      "aria-label": `${member.role === "admin" ? "Demote" : "Promote"} ${target}`,
      "data-act": actKey(member.role === "admin" ? "demote" : "promote", info, target),
      onclick: () => act(member.role === "admin" ? "demote" : "promote", info, { target }) }) : null);
  rove(tools, tools.querySelector("button, select"));
  return tools;
}

// ⌨️ Roving tab stop: only the tool you were last on is in the Tab order (tabindex 0), the others are -1.
const toolsIn = (bar) => [...bar.querySelectorAll("button, select")];

function rove(bar, current) {
  if (!toolsIn(bar).includes(current)) return;
  for (const tool of toolsIn(bar)) tool.tabIndex = tool === current ? 0 : -1;
}

function moveInToolbar(event) {
  const tools = toolsIn(event.currentTarget);
  const next = G.toolbarIndex(event.key, tools.indexOf(event.target), tools.length);
  if (next === null || !tools.includes(event.target)) return;
  event.preventDefault();
  tools[next].focus();
}

function members(info) {
  const list = Array.isArray(info.members_list) ? info.members_list : [];
  return block("gs-members-title", `👥 Members (${list.length})`,
    el("ul", { class: "gs-members" }, list.map((member, i) => el("li", { class: "gs-member" },
      el("span", { class: `gs-dot${member.online ? " on" : ""}`, "aria-hidden": "true" }),
      el("span", { class: `gs-member-name ${nameClass(str(member.name))}`, dir: "auto", text: str(member.name) }),
      el("span", { class: "visually-hidden", text: member.online ? ", online" : ", offline" }),
      el("span", { class: `gs-chip gs-chip-${member.role}`, text: memberRole(member.role) }),
      memberTools(info, member, i)))));
}

// ---------------------------------------------------------------- 🏦 the bank

function chart(points) {
  const path = G.chartPath(points, CHART_W, CHART_H);
  if (!path) return null;
  const label = `Bank balance, last 7 days: from ${path.first} to ${path.last} tokens (lowest ${path.min}, highest ${path.max})`;
  return el("figure", { class: "gs-chart" },
    svg("svg", { viewBox: `0 -4 ${CHART_W} ${CHART_H + 8}`, role: "img", "aria-label": label, preserveAspectRatio: "none", class: "gs-chart-svg" },
      svg("path", { d: path.area, class: "gs-chart-area" }), svg("path", { d: path.line, class: "gs-chart-line" })),
    el("figcaption", { class: "gs-chart-caption", "aria-hidden": "true" },
      el("span", { text: `${path.first} 🪙` }), el("span", { text: "last 7 days" }), el("span", { text: `${path.last} 🪙` })));
}

function earning(bank) {
  if (!bank.per_minute) return "Earning nothing right now: no member is online.";
  const people = `${bank.members_online} member${bank.members_online === 1 ? "" : "s"} online`;
  return `+${bank.per_minute} 🪙 a minute right now (${people}).`;
}

function donateForm(info) {
  const submit = async (event) => {
    event.preventDefault();
    const field = $("gs-donate");
    const amount = Number.parseInt(field.value, 10);
    if (!(amount > 0)) {
      field.setAttribute("aria-invalid", "true");
      return field.focus();
    }
    field.removeAttribute("aria-invalid");
    if (await act("donate", info, { value: amount })) field.value = "";
  };
  return el("form", { class: "gs-donate", onsubmit: submit },
    el("label", { class: "visually-hidden", for: "gs-donate", text: "Tokens to donate" }),
    el("input", { id: "gs-donate", class: "input", type: "number", min: "1", step: "1", inputmode: "numeric", placeholder: "Amount 🪙" }),
    el("button", { class: "btn btn-primary", type: "submit", text: "Donate", "data-act": actKey("donate", info) }));
}

function bankBlock(info) {
  const bank = info.bank_details;
  if (!bank) {
    if (!Number.isInteger(info.bank)) return null;
    return block("gs-bank-title", "🏦 Bank", el("p", { class: "gs-balance", text: `${info.bank} 🪙` }),
      el("p", { class: "gs-muted", text: "Join to see where the tokens come from and to donate." }));
  }
  const history = Array.isArray(bank.history) ? bank.history : [];
  const donors = Array.isArray(bank.top_donors) ? bank.top_donors : [];
  return block("gs-bank-title", "🏦 Bank",
    el("p", { class: "gs-balance" }, String(bank.balance), el("span", { class: "gs-balance-unit", text: " 🪙" })),
    el("p", { class: "gs-earning", text: earning(bank) }),
    bank.income_upgrade ? el("p", { class: "gs-muted", text: "💰 Income upgrade: members inside the group earn +2 🪙 a minute themselves." }) : null,
    chart(bank.chart),
    donateForm(info),
    donors.length ? el("div", { class: "gs-sub" }, el("h4", { class: "gs-h4", text: "🏅 Top donors" }),
      el("ol", { class: "gs-donors" }, donors.map((d) => el("li", {},
        el("span", { dir: "auto", text: str(d.name) }), el("span", { class: "gs-num", text: `${d.amount} 🪙` }))))) : null,
    el("div", { class: "gs-sub" }, el("h4", { class: "gs-h4", text: "📜 History" }),
      history.length ? el("ul", { class: "gs-history", tabindex: "0", "aria-label": "Bank history, newest first" }, history.map((row) => el("li", { class: "gs-history-row" },
        el("span", { class: "gs-time", text: G.timeLabel(row.time) }),
        el("span", { class: "gs-what", dir: "auto", text: G.historyLine(row) }),
        el("span", { class: `gs-num ${row.amount >= 0 ? "gs-plus" : "gs-minus"}`, text: `${row.amount >= 0 ? "+" : "−"}${Math.abs(row.amount)}` }),
        el("span", { class: "gs-after", text: `= ${row.balance}` }))))
        : el("p", { class: "gs-muted", text: "Nothing yet. Donations, upgrades and war prizes show up here." })));
}

// ---------------------------------------------------------------- ⬆️ upgrades

function upgradesBlock(info) {
  const upgrades = Array.isArray(info.upgrades) ? info.upgrades.filter((u) => u && typeof u === "object") : [];
  if (!upgrades.length) return null;
  const admin = G.isAdmin(info.your_role);
  const balance = Number.isInteger(info.bank) ? info.bank : 0;
  const buy = (u) => async () => {
    const after = G.balanceAfter(u, balance);
    const ok = await confirmStep({ title: `Buy ${str(u.icon)} ${str(u.name)}?`,
      text: `It costs ${u.price} 🪙 from the bank. The bank will have ${after} 🪙 left.`, yes: `Buy for ${u.price} 🪙` });
    if (ok) act("upgrade", info, { value: str(u.name) });
  };
  const admins = Array.isArray(info.admins) ? info.admins.map(str).join(", ") : "";
  return block("gs-upgrades-title", "⬆️ Upgrades",
    admin ? null : el("p", { class: "gs-muted", text: `Only admins can buy upgrades${admins ? `: ${admins}` : ""}.` }),
    el("ul", { class: "gs-upgrades" }, upgrades.map((u) => el("li", { class: `gs-upgrade gs-upgrade-${str(u.state)}` },
      el("span", { class: "gs-upgrade-icon", "aria-hidden": "true", text: str(u.icon) }),
      el("div", { class: "gs-upgrade-main" },
        el("p", { class: "gs-upgrade-name" }, el("span", { text: str(u.name) }), el("span", { class: "gs-num gs-price", text: `${u.price} 🪙` })),
        el("p", { class: "gs-upgrade-does", text: str(u.does) }),
        el("p", { class: "gs-upgrade-state", text: G.upgradeStatus(u) })),
      admin && u.state === "can_buy" ? el("button", { class: "btn btn-primary gs-buy", type: "button", text: "Buy",
        "aria-label": `Buy ${str(u.name)} for ${u.price} tokens`, "data-act": actKey("upgrade", info), onclick: buy(u) }) : null))));
}

// ---------------------------------------------------------------- 🛡️ admin tools (only sent to admins)

function settingForm(info, { id, label, action, value, placeholder, needs, max, what }) {
  const locked = needs && !(Array.isArray(info.upgrades) && info.upgrades.some((u) => u.name === needs && u.state === "owned"));
  const submit = async (event) => {
    event.preventDefault();
    if (!locked) act(action, info, { value: $(id).value.trim() });
  };
  return el("form", { class: "gs-setting", onsubmit: submit },
    el("label", { class: "field field-small", for: id }, el("span", { text: label })),
    el("div", { class: "gs-setting-row" },
      el("input", { id, class: "input", value: value || "", placeholder, maxlength: String(max), readonly: locked,
        "aria-disabled": locked ? "true" : null, "aria-describedby": locked ? `${id}-why` : null, autocomplete: "off" }),
      el("button", { class: "btn btn-ghost", type: "submit", text: "Save", "aria-label": `Save ${what}`,
        "aria-disabled": locked ? "true" : null, "aria-describedby": locked ? `${id}-why` : null,
        "data-locked": locked ? "1" : null, "data-act": actKey(action, info) })),
    locked ? el("p", { id: `${id}-why`, class: "field-hint", text: `Needs the ${needs} upgrade first.` }) : null);
}

const inviteNames = (info) => G.inviteCandidates(getState().online, getState().knownNames,
  (Array.isArray(info.members_list) ? info.members_list : []).map((m) => str(m.name)), getState().nick);

/** 📨 Invite someone (a name picker: who's online, then names this page has seen), and the invites still waiting. */
function inviteBlock(info) {
  const waiting = Array.isArray(info.admin.invites) ? info.admin.invites : [];
  const submit = async (event) => {
    event.preventDefault();
    const field = $("gs-invite");
    const target = field.value.trim();
    if (!target) return field.focus();
    if (await act("invite", info, { target })) field.value = "";
  };
  return el("div", { class: "gs-sub" },
    el("form", { class: "gs-setting", onsubmit: submit },
      el("label", { class: "field field-small", for: "gs-invite" }, el("span", { text: "📨 Invite someone (even to a private group)" })),
      el("div", { class: "gs-setting-row" },
        el("input", { id: "gs-invite", class: "input", list: "gs-invite-names", placeholder: "Their name", maxlength: "16",
          autocomplete: "off", autocapitalize: "none", spellcheck: "false", "aria-describedby": "gs-invite-hint" }),
        el("button", { class: "btn btn-primary", type: "submit", text: "Invite", "data-act": actKey("invite", info, "") })),
      el("datalist", { id: "gs-invite-names" }, inviteNames(info).map((n) => el("option", { value: n }))),
      el("p", { id: "gs-invite-hint", class: "field-hint", text: "They get a card with Accept and Decline. An invite lasts 24 hours." })),
    waiting.length ? el("div", {}, el("h4", { class: "gs-h4", text: `📨 Waiting invites (${waiting.length})` }),
      el("ul", { class: "gs-people" }, waiting.map((w) => el("li", { class: "gs-person" },
        el("span", { dir: "auto", text: `${str(w.name)} · ${Number(w.hours_left) || 1} h left` }))))) : null);
}

function adminBlock(info) {
  const admin = info.admin;
  if (!admin) return null;
  const name = str(info.name);
  const muted = Array.isArray(admin.muted) ? admin.muted : [];
  const banned = Array.isArray(admin.banned) ? admin.banned.map(str) : [];
  const person = (who, ...buttons) => el("li", { class: "gs-person" }, el("span", { dir: "auto", text: who }),
    el("div", { class: "gs-tools", role: "group", "aria-label": who }, buttons));
  return block("gs-admin-title", "🛡️ Admin tools",
    el("p", { class: "gs-muted", text: `These act on ${name} from wherever you are: you stay in the chat you're in.` }),
    inviteBlock(info),
    muted.length ? el("div", { class: "gs-sub" }, el("h4", { class: "gs-h4", text: "🔇 Muted" }),
      el("ul", { class: "gs-people" }, muted.map((m) => person(`${str(m.name)} · ${m.minutes} min left`,
        el("button", { class: "btn btn-ghost gs-small", type: "button", text: "Unmute", "aria-label": `Unmute ${str(m.name)}`,
          "data-act": actKey("unmute", info, str(m.name)),
          onclick: () => act("unmute", info, { target: str(m.name) }) }))))) : null,
    banned.length ? el("div", { class: "gs-sub" }, el("h4", { class: "gs-h4", text: "🚫 Banned" }),
      el("ul", { class: "gs-people" }, banned.map((who) => person(who,
        el("button", { class: "btn btn-ghost gs-small", type: "button", text: "Unban", "aria-label": `Unban ${who}`,
          "data-act": actKey("unban", info, who),
          onclick: () => act("unban", info, { target: who }) }))))) : null,
    el("div", { class: "gs-sub gs-settings" },
      settingForm(info, { id: "gs-topic", label: "📌 Pinned topic (empty: take it down)", action: "topic", value: info.topic, placeholder: "Nothing pinned", max: 120, what: "topic" }),
      settingForm(info, { id: "gs-emoji", label: "🎨 Group emoji", action: "emoji", value: info.emoji, placeholder: "One emoji, like 🍟", needs: "emoji", max: 8, what: "emoji" }),
      settingForm(info, { id: "gs-persona", label: "🎭 Hashbrown's persona here (empty: normal)", action: "persona", value: info.persona, placeholder: "Like: a pirate who loves potatoes", needs: "personality", max: 120, what: "persona" })),
    info.your_role === "owner" ? el("div", { class: "gs-sub gs-disband" },
      el("h4", { class: "gs-h4", text: "💥 Disband" }),
      el("p", { class: "gs-muted", text: "Deletes the group and its chat. Whatever is in the bank goes to you." }),
      el("button", { class: "btn btn-ghost gs-danger", type: "button", text: `Disband ${name}…`,
        onclick: async () => {
          const ok = await confirmStep({ title: `Disband ${name}?`, text: "This can't be undone: the group, its chat and its bank history are deleted.",
            yes: "Disband", requireText: name, label: `Type ${name} to confirm`, danger: true });
          if (ok && await act("disband", info)) $("gs-details-title")?.closest(".gs-body")?.querySelector(".gs-back")?.click();
        } })) : null);
}

/** 📨 Join requests hang on paper tickets above everything (in this world, what needs you is a ticket). */
function requestTickets(info) {
  const requests = info.admin && Array.isArray(info.admin.requests) ? info.admin.requests.map(str) : [];
  if (!requests.length) return null;
  return el("section", { class: "gs-tickets", "aria-labelledby": "gs-requests-title" },
    el("h3", { id: "gs-requests-title", class: "gs-h3", text: `📨 Join requests (${requests.length})` }),
    el("ul", { class: "gs-ticket-list" }, requests.map((who) => el("li", { class: "gs-ticket" },
      el("span", { class: "gs-ticket-name", dir: "auto", text: `${who} wants to join` }),
      el("div", { class: "gs-tools", role: "group", "aria-label": `Answer ${who}` },
        el("button", { class: "btn btn-primary gs-small", type: "button", text: "Approve", "aria-label": `Approve ${who}`,
          "data-act": actKey("approve", info, who), onclick: () => act("approve", info, { target: who }) }),
        el("button", { class: "btn btn-ghost gs-small gs-ticket-reject", type: "button", text: "Reject", "aria-label": `Reject ${who}`,
          "data-act": actKey("reject", info, who), onclick: () => act("reject", info, { target: who }) }))))));
}

// ---------------------------------------------------------------- the whole view

export function renderDetails(body, info, { back }) {
  const header = el("header", { class: "gs-head" },
    el("button", { class: "icon-btn gs-back", type: "button", "aria-label": "Back to all groups", onclick: back }, backIcon()),
    info ? badge(info) : null,
    el("h2", { id: "gs-details-title", class: "gs-title", tabindex: "-1", dir: "auto", text: info ? str(info.name) : "Loading…" }),
    info && info.private ? el("span", { class: "gs-chip", text: "🔒 Private" }) : null);
  body.append(header);
  if (!info) return;
  const role = str(info.your_role, "none");
  const member = G.isMember(role);
  const joinRow = member ? el("div", { class: "gs-row-actions" },
    el("button", { class: "btn btn-primary", type: "button", text: "Open chat", "data-act": actKey("open", info), onclick: () => act("open", info) }),
    role !== "owner" ? el("button", { class: "btn btn-ghost", type: "button", text: "Leave", "data-act": actKey("leave", info),
      onclick: async () => { if (await confirmLeave(info)) act("leave", info); } }) : null)
    : role === "requested" ? el("p", { class: "gs-waiting", text: "⏳ Your request is waiting for an admin." })
      : el("div", { class: "gs-row-actions" }, el("button", { class: "btn btn-primary", type: "button",
        text: info.private ? "Request to join" : "Join", "data-act": actKey("join", info), onclick: () => act("join", info) }));
  const inside = Array.isArray(info.members_list);
  const people = `👥 ${info.members} member${info.members === 1 ? "" : "s"}${Number.isInteger(info.online) ? ` · 🟢 ${info.online} online` : ""}`;
  body.append(el("div", { class: "gs-summary" }, el("div", { class: "gs-summary-text" }, el("p", { class: "gs-meta", text: people }),
    inside ? about(info) : el("p", { class: "gs-muted", text: "🔒 A private group: only its members see what's inside." })), joinRow));
  if (!inside) return;
  const tickets = requestTickets(info);
  if (tickets) body.append(tickets);
  body.append(el("div", { class: "gs-columns" },   // (el() skips the parts that are null)
    el("div", { class: "gs-col" }, members(info), adminBlock(info)),
    el("div", { class: "gs-col" }, bankBlock(info), upgradesBlock(info))));
}
