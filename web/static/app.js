// 🥔 Hashbrown Chat in the browser: wires the screens, the bridge connection and the panels together.

import { $ } from "./js/dom.js";
import * as api from "./js/api.js";
import { getState, setState, subscribe } from "./js/store.js";
import * as chat from "./js/chat.js";
import { initComposer, focusInput } from "./js/composer.js";
import { closeFilePanel, initFiles, openFilePanel, revokeFiles } from "./js/files.js";
import { focusLogin, initLogin, setBusy, showLoginError } from "./js/login.js";
import { handleMessage, needsCommands, requestCommands, savedNick, setPendingUsername } from "./js/protocol.js";
import { initRail } from "./js/rail.js";
import { focusChallenge, initSidebar } from "./js/sidebar.js";
import { initPanel } from "./js/games/panel.js";

const THEME_KEY = "hashbrown.theme";
const SCREENS = ["loading", "login", "chat", "closed"];
const app = $("screen-chat");
const narrow = matchMedia("(max-width: 760px)");
const medium = matchMedia("(max-width: 1180px)");
let quitting = false;

// ----- theme: follows the computer unless you pick one

function storedTheme() {
  try {
    return localStorage.getItem(THEME_KEY);
  } catch {
    return null;
  }
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $("theme-toggle").textContent = theme === "light" ? "🌙 Dark mode" : "☀️ Light mode";
  document.querySelector('meta[name="theme-color"]').content = theme === "light" ? "#f1e4d0" : "#1a120c";
}

applyTheme(storedTheme() || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"));
$("theme-toggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  applyTheme(next);
  try {
    localStorage.setItem(THEME_KEY, next);
  } catch {
    // private mode: the choice just isn't remembered
  }
});

// ----- drawers (sidebar on phones, game panel on smaller laptops)

const DRAWERS = { side: ["sidebar", "open-sidebar", "close-sidebar"], game: ["game-panel", "open-game", "close-game"] };
let openDrawer = null;

/** Drawers act like a modal: focus moves in, the rest of the page is inert, and focus returns on close. */
function setDrawer(name) {
  if (name === openDrawer) return;
  const previous = openDrawer;
  openDrawer = name;
  app.classList.toggle("side-open", name === "side");
  app.classList.toggle("game-open", name === "game");
  $("scrim").hidden = !name;
  for (const [key, [panelId, openerId]] of Object.entries(DRAWERS)) {
    $(openerId).setAttribute("aria-expanded", String(key === name));
    // the other drawer only goes inert when it's an overlay too (narrower screens)
    $(panelId).inert = Boolean(name) && key !== name && getComputedStyle($(panelId)).position === "fixed";
  }
  document.querySelector(".chat-col").inert = Boolean(name);
  if (name) $(DRAWERS[name][2]).focus();
  else if (previous) $(DRAWERS[previous][1]).focus();
}
const closeDrawer = () => setDrawer(null);
const openGame = () => { if (medium.matches) setDrawer("game"); };

$("open-sidebar").addEventListener("click", () => setDrawer("side"));
$("close-sidebar").addEventListener("click", closeDrawer);
$("open-game").addEventListener("click", () => setDrawer("game"));
$("close-game").addEventListener("click", closeDrawer);
$("scrim").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("scrim").hidden) closeDrawer();
});

// ----- screens

subscribe((state) => {
  for (const name of SCREENS) $(`screen-${name}`).hidden = state.screen !== name;
});

function showError(text) {
  chat.addNotice("error", `⚠️ ${text}`);
}

function resetChat() {
  chat.clearMessages();
  revokeFiles();
  closeFilePanel();
  closeDrawer();
  setState({ nick: "", room: "🏠 Lobby", commands: [], match: null, wordle: null, invites: [] });
}

function showClosed(reason) {
  resetChat();
  $("closed-reason").textContent = reason;
  setState({ screen: "closed" });
  $("reconnect").focus();
}

async function connect(loginError = "") {
  setBusy(false);
  if (!api.hasSession()) {
    const result = await api.newSession();
    if (!result.ok) {
      setState({ screen: "login" });
      showLoginError(result.error);
      return;
    }
  }
  api.listen();
  if (loginError) showLoginError(loginError);
}

api.setHandlers({
  onMessage: (msg, live) => handleMessage(msg, live, api.sendLine),
  onLive: (info) => {
    const { screen } = getState();
    if (info.logged_in && screen !== "chat") setState({ screen: "chat", nick: getState().nick || savedNick() });
    else if (!info.logged_in && screen !== "login") {
      setState({ screen: "login" });
      focusLogin();
    }
    if (getState().screen === "chat") {
      if (needsCommands()) requestCommands(api.sendLine);
      if (matchMedia("(pointer: fine)").matches) focusInput();  // no surprise keyboard on phones
    }
  },
  onClosed: (reason) => {
    if (quitting) {
      quitting = false;
      return showClosed("You left the chat. Bye 👋");
    }
    if (getState().screen === "chat") return showClosed(reason);
    resetChat();
    connect(reason);  // still on the login screen: quietly start a fresh connection
  },
  onGap: () => chat.addNotice("system", "✂️ Some older messages were skipped."),
  onReplaced: () => showClosed("This chat is open in another tab. Close that tab, then come back here."),
  onLost: () => showClosed("Your session ended. Log in again to keep chatting."),
});

$("reconnect").addEventListener("click", () => {
  setState({ screen: "loading" });
  connect();
});
$("logout").addEventListener("click", async () => {
  await api.logout();
  resetChat();
  setState({ screen: "loading" });
  connect();
});

initLogin({
  onSubmit: async (action, username, password) => {
    if (!api.hasSession()) {
      await connect();
      if (!api.hasSession()) return;  // connect() already showed why
      setBusy(true);
    }
    await api.whenLive();  // otherwise the reply could arrive mixed into the replay and get lost
    setPendingUsername(username);
    const error = await api.send({ type: "auth", action, username, password });
    if (error) showLoginError(error);
  },
});

initComposer({
  onSubmit: async (text) => {
    const lower = text.toLowerCase();
    if (lower === "/sendfile" || lower.startsWith("/sendfile ")) {
      openFilePanel({ to: text.split(/\s+/)[1] || "" });
      return true;
    }
    if (lower === "/quit") quitting = true;
    const error = await api.sendLine(text);
    if (error) {
      quitting = false;
      showError(error);
      return false;
    }
    chat.clearLit();
    return true;
  },
});

initFiles({ onSent: () => {} });
initSidebar({ onError: showError, closeDrawer: () => { if (narrow.matches) closeDrawer(); } });
initRail({ openGame });
initPanel({
  showError,
  focusChallenge: () => {
    if (narrow.matches) setDrawer("side");
    else closeDrawer();
    focusChallenge();
  },
});

connect();
