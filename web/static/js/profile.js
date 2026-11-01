// 👤 Profiles: a card when you click someone's name, and an Edit profile dialog for yours.
// The server sends {"type": "profile", "profile", "mine"} when we ask ({"type": "get_profile", "name"}), and your
// own at login; your theme comes with it, so it's the same on every device. Saving sends the normal
// /setprofile and /nick commands; the password goes in its own {"type": "change_password"} packet
// (so it never shows up as a chat line). The server checks everything again.

import { $, clear, el, nameClass, str } from "./dom.js";
import { send, sendLine } from "./api.js";
import { getState } from "./store.js";

const STATUS_ICON = { online: "🟢", away: "🌙", busy: "⛔" };
const GAMES = { "": "None", ttt: "Tic-Tac-Toe", damka: "Damka", math: "Math Duel", connect4: "Connect 4", battleship: "Battleship", wordle: "Wordle" };
let mine = null;              // your own profile (with your theme and privacy)
let waitingFor = "";          // the name whose card we asked for
let hooks = { onMessage: () => {}, onChallenge: () => {}, applyTheme: () => {}, onError: () => {} };

export const myTheme = () => (mine && mine.theme) || "";

/** Ask for someone's card (it opens when the answer comes). */
export function showProfile(name) {
  const who = str(name).trim();
  if (!who) return;
  waitingFor = who.toLowerCase();
  send({ type: "get_profile", name: who });
}

/** The server's {"type": "profile"}. */
export function onProfile(msg, live) {
  const profile = msg.profile && typeof msg.profile === "object" ? msg.profile : null;
  if (!profile) return;
  if (msg.mine === true) {
    mine = profile;
    if (profile.theme === "light" || profile.theme === "dark") hooks.applyTheme(profile.theme, false);
  }
  const names = [str(profile.name).toLowerCase(), str(profile.login).toLowerCase()];
  if (live && waitingFor && names.includes(waitingFor)) {
    waitingFor = "";
    drawCard(profile);
  }
}

/** You changed the theme with the button: remember it on the server too (quietly). */
export function saveTheme(theme) {
  if (getState().screen === "chat") sendLine(`/setprofile theme ${theme}`);
}

/** The server's "👤 Saved your ..." answers aren't shown in the chat: the dialog says so itself. */
export const isQuietSave = (text) => text.startsWith("👤 Saved your ");

function row(label, value) {
  return value ? el("div", { class: "pf-row" }, el("dt", { text: label }), el("dd", { dir: "auto", text: value })) : null;
}

function drawCard(p) {
  const dialog = $("profile-card");
  const body = clear($("pf-card-body"));
  const name = str(p.name);
  const status = `${STATUS_ICON[p.status] || ""} ${str(p.status)}${p.status_text ? `: ${str(p.status_text)}` : ""}`.trim();
  const colour = Number.isInteger(p.color) ? `name-${p.color}` : nameClass(name);
  body.append(
    el("div", { class: "pf-head" },
      el("span", { class: `pf-avatar ${p.avatar ? "" : colour}`, "aria-hidden": "true", text: str(p.avatar) || (Array.from(name)[0] || "?").toUpperCase() }),
      el("div", {},
        el("h2", { id: "pf-card-title", class: `pf-name ${colour}`, dir: "auto" }, name, p.badge ? el("span", { class: "badge", text: ` ${str(p.badge)}` }) : null),
        el("p", { class: "pf-login", text: `@${str(p.login)}${p.online ? " · online now" : ""}` }))),
    el("dl", { class: "pf-rows" },
      row("Status", status),
      row("Bio", str(p.bio)),
      row("Favourite game", str(p.fav_game)),
      row("Record", `${p.wins} wins · 📈 ELO ${p.elo} · 🏅 ${p.achievements} achievements`),
      row("Joined", str(p.joined)),
      row("Last seen", str(p.last_seen || ""))),
    el("div", { class: "pf-actions" }, p.you
      ? el("button", { class: "btn btn-primary", type: "button", text: "✏️ Edit profile", onclick: () => { dialog.close(); openEditor(); } })
      : [el("button", { class: "btn btn-primary", type: "button", text: "💌 Message", onclick: () => { dialog.close(); hooks.onMessage(name); } }),
        el("button", { class: "btn btn-ghost", type: "button", text: "⚔️ Challenge", onclick: () => { dialog.close(); hooks.onChallenge(name); } })]));
  if (!dialog.open) dialog.showModal();
}

// ---------------------------------------------------------------- ✏️ editing your own

const field = (label, input, hint = "") => el("label", { class: "field" }, el("span", { text: label }), input,
  hint ? el("span", { class: "field-hint", text: hint }) : null);

function select(id, options, value) {
  return el("select", { id }, Object.entries(options).map(([v, text]) => el("option", { value: v, text, selected: v === value })));
}

export function openEditor() {
  if (!mine) return showProfile(getState().nick);
  const p = mine;
  const dialog = $("profile-edit");
  const form = clear($("pf-edit-form"));
  const colours = el("div", { class: "pf-colours", role: "radiogroup", "aria-label": "Name colour" },
    ["auto", 0, 1, 2, 3, 4, 5, 6, 7].map((c) => el("label", { class: `pf-swatch ${c === "auto" ? "" : `name-${c}`}` },
      el("input", { type: "radio", name: "pf-colour", value: String(c), checked: (p.color ?? "auto") === c }),
      el("span", { text: c === "auto" ? "Auto" : "Aa" }))));
  form.append(
    el("h2", { id: "pf-edit-title", text: "✏️ Edit profile" }),
    el("p", { class: "field-hint", text: `Your username stays @${str(p.login)}. Everyone can see these, except the theme and privacy.` }),
    field("Avatar (one emoji)", el("input", { id: "pf-avatar", value: str(p.avatar), maxlength: "8", placeholder: "🍟", autocomplete: "off" })),
    field("Display name", el("input", { id: "pf-name", value: str(p.name), maxlength: "16", autocomplete: "off" })),
    field("Bio", el("textarea", { id: "pf-bio", maxlength: "140", rows: "2", text: str(p.bio) }), "Up to 140 characters"),
    el("div", { class: "pf-two" },
      field("Status", select("pf-status", { online: "🟢 Online", away: "🌙 Away", busy: "⛔ Busy" }, str(p.status, "online"))),
      field("Status line", el("input", { id: "pf-status-text", value: str(p.status_text), maxlength: "60", placeholder: "doing homework" }))),
    el("fieldset", { class: "pf-fieldset" }, el("legend", { text: "Name colour" }), colours),
    el("div", { class: "pf-two" },
      field("Favourite game", select("pf-game", GAMES, Object.keys(GAMES).find((k) => GAMES[k] === p.fav_game) || "")),
      field("Theme", select("pf-theme", { "": "Follow the computer", light: "☀️ Light", dark: "🌙 Dark" }, str(p.theme)))),
    el("fieldset", { class: "pf-fieldset" }, el("legend", { text: "Privacy" }),
      el("label", { class: "gs-check" }, el("input", { id: "pf-lastseen", type: "checkbox", checked: !(p.privacy && p.privacy.last_seen === false) }),
        el("span", { text: "Show when I was last online" })),
      field("Who can send me private messages", select("pf-dms", { everyone: "Everyone", groups: "People in my groups", friends: "Friends only", nobody: "Nobody" },
        str(p.privacy && p.privacy.dms, "everyone")))),
    el("fieldset", { class: "pf-fieldset" }, el("legend", { text: "🔑 Change password" }),
      field("Old password", el("input", { id: "pf-old", type: "password", autocomplete: "current-password" })),
      field("New password", el("input", { id: "pf-new", type: "password", autocomplete: "new-password", minlength: "6" }), "6 to 64 characters")),
    el("p", { id: "pf-edit-status", class: "field-hint", role: "status" }),
    el("div", { class: "pf-actions" },
      el("button", { class: "btn btn-ghost", type: "button", text: "Cancel", onclick: () => dialog.close() }),
      el("button", { class: "btn btn-primary", type: "submit", text: "Save" })));
  form.onsubmit = (event) => { event.preventDefault(); save(p); };
  dialog.showModal();
  $("pf-avatar").focus();
}

/** Send only what changed, one command at a time (the server checks each one). */
async function save(p) {
  const value = (id) => $(id).value.trim();
  const colour = document.querySelector('input[name="pf-colour"]:checked')?.value || "auto";
  const changes = [
    ["avatar", value("pf-avatar"), str(p.avatar)],
    ["bio", value("pf-bio"), str(p.bio)],
    ["status", value("pf-status"), str(p.status)],
    ["statustext", value("pf-status-text"), str(p.status_text)],
    ["color", colour, Number.isInteger(p.color) ? String(p.color) : "auto"],
    ["game", value("pf-game"), Object.keys(GAMES).find((k) => GAMES[k] === p.fav_game) || ""],
    ["theme", value("pf-theme"), str(p.theme)],
    ["lastseen", $("pf-lastseen").checked ? "show" : "hide", p.privacy && p.privacy.last_seen === false ? "hide" : "show"],
    ["dms", value("pf-dms"), str(p.privacy && p.privacy.dms, "everyone")],
  ].filter(([, now, before]) => now !== before);
  const lines = changes.map(([f, now]) => `/setprofile ${f} ${now}`.trim());
  if (value("pf-name") && value("pf-name") !== str(p.name)) lines.push(`/nick ${value("pf-name")}`);
  const status = $("pf-edit-status");
  for (const line of lines) {
    const error = await sendLine(line);
    if (error) {
      status.textContent = `⚠️ ${error}`;
      return;
    }
  }
  if ($("pf-old").value || $("pf-new").value) {
    const error = await send({ type: "change_password", old: $("pf-old").value, new: $("pf-new").value });
    if (error) {
      status.textContent = `⚠️ ${error}`;
      return;
    }
  }
  status.textContent = lines.length || $("pf-new").value ? "✅ Sent. Any problem shows up in the chat." : "Nothing changed.";
  if (lines.length || $("pf-new").value) setTimeout(() => $("profile-edit").close(), 900);
}

export function resetProfile() {
  mine = null;
  waitingFor = "";
}

export function initProfiles(nextHooks) {
  hooks = { ...hooks, ...nextHooks };
  $("pf-card-close").addEventListener("click", () => $("profile-card").close());
  $("profile-open").addEventListener("click", () => showProfile(getState().nick));
  // Names in chat bubbles open a card too (the online list has its own buttons)
  $("messages").addEventListener("click", (event) => {
    const who = event.target.closest(".msg-head .who");
    if (who) showProfile(who.textContent === "You" ? getState().nick : who.textContent);
  });
}
