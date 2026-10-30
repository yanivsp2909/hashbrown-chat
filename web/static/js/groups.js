// 👥 The Groups screen: see and manage groups by clicking. It takes the chat column's place (the whole
// screen on a phone). What it shows comes from the server's {"type": "groups"} and {"type": "group_info"}
// packets; every button sends an existing /command (grouplogic.js says which), so the server's own checks
// decide what's allowed. Server replies (errors too) show in a line at the bottom, since the chat is hidden.

import { $, clear, el, str } from "./dom.js";
import { send, sendLine } from "./api.js";
import { getState } from "./store.js";
import * as G from "./grouplogic.js";
import { backIcon, renderDetails } from "./groupdetails.js";

const REPLY_MS = 7000;        // how long a server reply stays in the line at the bottom
const REPLY_WINDOW = 4000;    // only replies this soon after a button on this screen (not the site's quiet refreshes)
let lastAct = 0;
let cards = [];
let info = null;              // the open group's details
let view = null;              // null = closed, "" = the list, a group key = that group
let query = "";
let creating = false;
let loaded = false;           // has the first list arrived? (until then: "Loading groups…", not a false "no groups")
let detailsTimer = null;
const DETAILS_WAIT = 5000;    // ms before "Couldn't load this group"
const inFlight = new Set();   // buttons still sending (action:target), so a double click doesn't send twice
let replyTimer = null;
let hooks = { onError: () => {}, closeDrawer: () => {} };

export const isOpen = () => view !== null;

const roleChip = (role) => ({ owner: "👑 Owner", admin: "🛡️ Admin", member: "Member", requested: "⏳ Requested" })[role] || "";

/** A group's badge: its emoji, or its first letter. */
export function badge(card) {
  const emoji = str(card.emoji);
  return el("span", { class: `gs-badge${emoji ? "" : " gs-badge-letter"}`, "aria-hidden": "true",
    text: emoji || (Array.from(str(card.name))[0] || "?").toUpperCase() });
}

/** Send the lines one button means, one after another (stop at the first that doesn't get through). */
export async function act(action, group, extra = {}) {
  const id = `${action}:${group.key ?? group.name}:${extra.target || ""}`;
  if (inFlight.has(id)) return false;   // still sending the last click
  inFlight.add(id);
  lastAct = Date.now();
  markBusy();
  try {
    for (const line of G.commandsFor(action, group, { currentRoom: getState().currentRoom, ...extra })) {
      const error = await sendLine(line);
      if (error) {
        noteServerText("error", `⚠️ ${error}`, true);
        hooks.onError(error);
        return false;
      }
    }
    return true;
  } finally {
    inFlight.delete(id);
    markBusy();
  }
}

/** Buttons whose action is still on its way are disabled (render() draws new ones: this runs after it too). */
function markBusy() {
  for (const button of $("groups-body").querySelectorAll("[data-act]")) {
    const busy = inFlight.has(button.dataset.act);
    button.disabled = busy || button.dataset.locked === "1";
    button.toggleAttribute("aria-busy", busy);
  }
}

/** The data-act key act() uses, for a button that runs it. */
export const actKey = (action, group, target = "") => `${action}:${group.key ?? group.name}:${target}`;

/** A confirm step in a small dialog. requireText: they must type it (like the group's name) first. */
export function confirmStep({ title, text, yes, requireText = "", label = "", danger = false }) {
  const dialog = $("groups-confirm");
  const opener = document.activeElement;
  $("gs-confirm-title").textContent = title;
  $("gs-confirm-text").textContent = text;
  $("gs-confirm-yes").textContent = yes;
  $("gs-confirm-field").hidden = !requireText;
  $("gs-confirm-label").textContent = label;
  const input = $("gs-confirm-input");
  input.value = "";
  const yesButton = $("gs-confirm-yes");
  yesButton.className = `btn ${danger ? "btn-danger" : "btn-primary"}`;   // losing something is ketchup, not gold
  yesButton.disabled = Boolean(requireText);
  input.oninput = () => { yesButton.disabled = input.value.trim().toLowerCase() !== requireText.toLowerCase(); };
  dialog.returnValue = "";
  dialog.showModal();
  if (requireText) input.focus();
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => {
      if (opener && document.contains(opener)) opener.focus();
      resolve(dialog.returnValue === "yes");
    }, { once: true });
  });
}

/** The latest server reply, shown at the bottom of the screen (the chat behind it is hidden). */
export function noteServerText(kind, text, force = false) {
  if (!isOpen() || (!force && Date.now() - lastAct > REPLY_WINDOW)) return;
  const line = $("groups-reply");
  line.textContent = str(text).split("\n")[0];
  line.className = `gs-reply gs-reply-${["error", "money", "event"].includes(kind) ? kind : "system"}`;
  line.hidden = false;
  clearTimeout(replyTimer);
  replyTimer = setTimeout(() => { line.hidden = true; }, REPLY_MS);
}

/** The confirm step before leaving a group (from its row or its details). */
export const confirmLeave = (card) => confirmStep({ title: `Leave ${str(card.name)}?`, danger: true, yes: "Leave",
  text: card.private ? "It's private: you'd have to ask to come back." : "You can join again any time." });

// ---------------------------------------------------------------- the list

function groupRow(card) {
  const role = str(card.your_role, "none");
  const name = str(card.name);
  const member = G.isMember(role);
  const meta = [`👥 ${card.members}`];
  if (Number.isInteger(card.online)) meta.push(`🟢 ${card.online} online`);   // (not for private groups you're not in)
  if (Number.isInteger(card.bank)) meta.push(`🏦 ${card.bank} 🪙`);
  const upgrades = Array.isArray(card.upgrades) && card.upgrades.length ? card.upgrades.map(str).join(" · ") : "";
  const actions = member
    ? [el("button", { class: "btn btn-primary", type: "button", text: "Open chat", "aria-label": `Open the chat of ${name}`,
      "data-act": actKey("open", card),
      onclick: async () => { if (await act("open", card)) close(); } }),
    role !== "owner" ? el("button", { class: "btn btn-ghost", type: "button", text: "Leave", "aria-label": `Leave ${name}`,
      onclick: async () => {
        if (await confirmLeave(card)) act("leave", card);
      } }) : null]
    : role === "requested" ? [el("span", { class: "gs-waiting", text: "⏳ Waiting for an admin" })]
      : [el("button", { class: "btn btn-primary", type: "button", text: card.private ? "Request to join" : "Join",
        "aria-label": `${card.private ? "Request to join" : "Join"} ${name}`, "data-act": actKey("join", card),
        onclick: () => act("join", card) })];
  return el("li", { class: "gs-row" },
    badge(card),
    el("div", { class: "gs-row-main" },
      el("p", { class: "gs-row-title" },
        el("button", { class: "gs-name", type: "button", dir: "auto", text: name, "data-focus": `open-${card.key}`,
          "aria-label": `${name}: details`, onclick: () => openGroup(card.key) }),
        card.private ? el("span", { class: "gs-chip", text: "🔒 Private" }) : null,
        roleChip(role) ? el("span", { class: `gs-chip gs-chip-${role}`, text: roleChip(role) }) : null),
      card.topic ? el("p", { class: "gs-topic", dir: "auto", text: `📌 ${str(card.topic)}` }) : null,
      el("p", { class: "gs-meta", text: meta.join(" · ") + (upgrades ? ` · ⬆️ ${upgrades}` : "") }),
      card.persona ? el("p", { class: "gs-persona", dir: "auto", text: `🎭 ${str(card.persona)}` }) : null),
    el("div", { class: "gs-row-actions" }, actions));
}

function section(title, list, empty) {
  return el("section", { class: "gs-section", "aria-label": title },
    el("h3", { class: "gs-h3", text: title }),
    list.length ? el("ul", { class: "gs-list" }, list.map(groupRow)) : el("p", { class: "gs-empty", text: empty }));
}

function createForm() {
  const submit = async (event) => {
    event.preventDefault();
    const name = $("gs-create-name").value.trim();
    if (!name) return $("gs-create-name").focus();
    if (await act("create", { key: "", name }, { private: $("gs-create-private").checked })) {
      creating = false;
      render();
    }
  };
  return el("form", { class: "gs-create", onsubmit: submit, "aria-label": "Create a group" },
    el("label", { class: "field field-small" }, el("span", { text: "Group name" }),
      el("input", { id: "gs-create-name", maxlength: "16", required: true, autocomplete: "off", spellcheck: "false",
        "aria-describedby": "gs-create-hint" })),
    el("label", { class: "gs-check" }, el("input", { id: "gs-create-private", type: "checkbox" }),
      el("span", { text: "🔒 Private: people ask to join and an admin approves them" })),
    el("p", { id: "gs-create-hint", class: "field-hint", text: "3-16 English or Hebrew letters, digits or _. Creating a group costs tokens." }),
    el("div", { class: "gs-create-actions" },
      el("button", { class: "btn btn-primary", type: "submit", text: "Create group", "data-act": actKey("create", { name: "" }) }),
      el("button", { class: "btn btn-ghost", type: "button", text: "Cancel", onclick: () => { creating = false; render(); } })));
}

function renderList(body) {
  const { mine, others } = G.split(cards, query);
  body.append(...[
    el("header", { class: "gs-head" },
      el("button", { class: "icon-btn gs-back", type: "button", "aria-label": "Back to the chat", onclick: close }, backIcon()),
      el("h2", { id: "groups-title", class: "gs-title", tabindex: "-1" }, el("span", { "aria-hidden": "true", text: "👥 " }), "Groups"),
      el("button", { class: "btn btn-primary gs-new", type: "button", "aria-expanded": String(creating), "data-focus": "create",
        text: "+ Create group", onclick: () => { creating = !creating; render(); if (creating) $("gs-create-name").focus(); } })),
    creating ? createForm() : null,
    el("label", { class: "gs-search" }, el("span", { class: "visually-hidden", text: "Search groups" }),
      el("input", { id: "gs-search", class: "input", type: "search", placeholder: "🔍 Search groups…", value: query,
        autocomplete: "off", oninput: (event) => { query = event.target.value; render(); } })),
    !loaded ? el("p", { class: "loading-text", text: "Loading groups…" }) : null,
    loaded && !cards.length ? el("div", { class: "empty-grill" }, el("span", { class: "big", "aria-hidden": "true", text: "👥" }),
      el("h2", { text: "No groups yet" }), el("p", { text: "Make the first one and invite your friends. 🎉" }),
      el("div", { class: "row" }, el("button", { class: "btn btn-primary", type: "button", text: "+ Create group",
        onclick: () => { creating = true; render(); $("gs-create-name").focus(); } }))) : null,
    cards.length ? section("Your groups", mine, query ? "None of yours match." : "You're not in a group yet. Join one below!") : null,
    cards.length ? section("Other groups", others, query ? `No other group matches "${query}".` : "That's every group.") : null,
  ].filter(Boolean));
}

// ---------------------------------------------------------------- the shell

/** Draw again, keeping what you typed and where the keyboard was. */
function render() {
  const body = $("groups-body");
  const typed = Object.fromEntries([...body.querySelectorAll("input[id], textarea[id], select[id]")].map((f) => [f.id, f.value]));
  const active = document.activeElement;
  const focusKey = body.contains(active) ? (active.id || active.dataset.focus || "") : "";
  const caret = focusKey && typeof active.selectionStart === "number" ? [active.selectionStart, active.selectionEnd] : null;
  clear(body);
  if (view === "") renderList(body);
  else if (view) renderDetails(body, info, { back: showList });
  for (const [id, value] of Object.entries(typed)) {
    const field = document.getElementById(id);
    if (field && body.contains(field) && field.type !== "checkbox" && id !== "gs-search") field.value = value;
  }
  markBusy();
  if (focusKey) {
    const again = body.querySelector(`#${CSS.escape(focusKey)}`) || body.querySelector(`[data-focus="${CSS.escape(focusKey)}"]`);
    if (again) {
      again.focus({ preventScroll: true });
      if (caret && typeof again.setSelectionRange === "function") again.setSelectionRange(...caret);
    }
  }
}

function setOpen(open) {
  const screen = $("groups-screen");
  screen.hidden = !open;
  $("screen-chat").classList.toggle("groups-open", open);
  $("groups-open").setAttribute("aria-expanded", String(open));
}

export function open() {
  hooks.closeDrawer();
  view = "";
  info = null;
  loaded = false;
  setOpen(true);
  render();
  send({ type: "get_groups" });
  $("groups-title")?.focus();
}

export function close() {
  if (view === null) return;
  view = null;
  setOpen(false);
  $("groups-reply").hidden = true;
  send({ type: "groups_closed" });
  $("groups-open").focus();
}

function openGroup(key) {
  view = key;
  info = null;
  render();
  send({ type: "get_group", group: key });
  clearTimeout(detailsTimer);
  detailsTimer = setTimeout(() => {
    if (view !== key || info) return;
    const body = $("groups-body");
    body.append(el("div", { class: "empty-grill" }, el("p", { text: "Couldn't load this group." }),
      el("div", { class: "row" },
        el("button", { class: "btn btn-primary", type: "button", text: "Try again", onclick: () => openGroup(key) }),
        el("button", { class: "btn btn-ghost", type: "button", text: "Back", onclick: showList }))));
  }, DETAILS_WAIT);
}

function showList() {
  const was = view;
  view = "";
  info = null;
  render();
  send({ type: "get_groups" });
  (document.querySelector(`[data-focus="open-${CSS.escape(String(was))}"]`) || $("groups-title"))?.focus();
}

/** {"type": "groups"} from the server. */
export function onGroups(msg) {
  cards = Array.isArray(msg.groups) ? msg.groups.filter((c) => c && typeof c.key === "string") : [];
  loaded = true;
  if (view && !cards.some((c) => c.key === view)) {   // the group you were looking at is gone (disbanded)
    showList();
    noteServerText("event", "💥 That group is gone.", true);
    return;
  }
  if (view === "") render();
}

/** {"type": "group_info"} from the server (only the one we're looking at is drawn). */
export function onGroupInfo(msg) {
  const group = msg.group;
  if (!group || typeof group.key !== "string" || group.key !== view) return;
  const first = info === null;
  info = group;
  render();
  if (first) $("gs-details-title")?.focus();
}

/** After logout: closed and empty. */
export function resetGroups() {
  view = null;
  cards = [];
  info = null;
  setOpen(false);
}

export function initGroups(nextHooks) {
  hooks = { ...hooks, ...nextHooks };
  $("groups-open").addEventListener("click", () => (isOpen() ? close() : open()));
  $("groups-screen").addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("groups-confirm").open) {
      event.preventDefault();
      if (view) showList(); else close();
    }
  });
}
