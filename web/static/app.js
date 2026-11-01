// 🥔 Hashbrown Chat in the browser: wires the screens, the bridge connection and the panels together.

import { $, str } from "./js/dom.js";
import * as api from "./js/api.js";
import { getState, setState, subscribe } from "./js/store.js";
import * as chat from "./js/chat.js";
import { initComposer, focusInput } from "./js/composer.js";
import { closeFilePanel, initFiles, openFilePanel, revokeFiles } from "./js/files.js";
import { focusLogin, initLogin, setBusy, showLoginError } from "./js/login.js";
import { handleMessage, needsCommands, requestCommands, resetCommands, savedNick, setHooks, setPendingUsername } from "./js/protocol.js";
import { initOnline, refreshAll, resetOnline, youAsked } from "./js/online.js";
import { initRail } from "./js/rail.js";
import { focusChallenge, initSidebar } from "./js/sidebar.js";
import { initPanel } from "./js/games/panel.js";
import { initXray } from "./js/xray.js";
import { initFriends } from "./js/friends.js";
import { initRooms } from "./js/rooms.js";
import { initTyping } from "./js/typing.js";
import { initEdits, submitEdit } from "./js/edits.js";
import { showLab, showTopic } from "./js/banners.js";
import { initGroups, resetGroups } from "./js/groups.js";
import { initVentures, resetVentures } from "./js/ventures.js";
import { initNetmap } from "./js/netmap.js";
import { initDrawing } from "./js/drawing.js";
import { initMarket } from "./js/market.js";
import { initEconomy } from "./js/economy.js";
import { initProfiles, resetProfile, saveTheme, showProfile } from "./js/profile.js";
import * as resume from "./js/resume.js";

const FEATURES = ["stream", "rooms", "typing", "chunks", "offers", "profiles", "probe", "draw", "friends", "ventures"];   // what this website understands (told at login)
const RESUME_WAITS = [1, 2, 4, 8, 15, 30, 60];   // 🔁 seconds between tries to reconnect, then we give up

const THEME_KEY = "hashbrown.theme";
const SCREENS = ["loading", "login", "chat", "closed"];
const app = $("screen-chat");
const narrow = matchMedia("(max-width: 760px)");
const medium = matchMedia("(max-width: 1099px)");
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
function rememberTheme(theme) {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // private mode: the choice just isn't remembered
  }
}

$("theme-toggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  applyTheme(next);
  rememberTheme(next);
  saveTheme(next);   // 👤 on the server too, so your other devices follow
});

// ----- drawers (sidebar on phones, game panel on smaller laptops)

const DRAWERS = { side: ["sidebar", "open-sidebar", "close-sidebar"], game: ["game-panel", "open-game", "close-game"] };
let openDrawer = null;
let returnFocus = null;   // where focus was before a drawer opened, to put it back after

/** Drawers act like a modal: focus moves in, the rest of the page is inert, and focus returns on close. */
function setDrawer(name) {
  if (name === openDrawer) return;
  const previous = openDrawer;
  if (name && !previous) returnFocus = document.activeElement;
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
  $("xray").inert = Boolean(name);   // 🔬 under the scrim too while a drawer is open
  if (name) $(DRAWERS[name][2]).focus();
  else if (previous) {
    const back = returnFocus && returnFocus.isConnected && returnFocus !== document.body ? returnFocus : $(DRAWERS[previous][1]);
    back.focus();
  }
}
const closeDrawer = () => setDrawer(null);
const openGame = () => { if (medium.matches) setDrawer("game"); };
/** "Show grid" and similar: on smaller screens open the drawer, on wide ones jump to the panel. */
function showGame() {
  if (medium.matches) return setDrawer("game");
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  $("game-panel").querySelector("h2")?.scrollIntoView({ block: "nearest", behavior: calm ? "auto" : "smooth" });
}

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
  resetOnline();
  resetGroups();
  resetVentures();
  resetProfile();
  resetCommands();
  setState({ nick: "", room: "🏠 Lobby", commands: [], match: null, wordle: null, invites: [], online: null, balance: null,
    currentRoom: "", rooms: [], unread: {}, previews: {}, friends: null, groupInvites: [] });   // 💬 🤝 📨 a clean start
  showTopic({});
  showLab({});
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
  onMessage: (msg, live) => {
    if (!resume.seePacket(msg, live)) return;   // 🔁 already have it (caught up after a reconnect)
    try {
      handleMessage(msg, live, api.sendLine);
    } catch (error) {
      // A bug in drawing one message must not make it disappear without a trace
      console.error("Couldn't show a message from the chat server:", error, msg);
      chat.addNotice("error", `⚠️ A message couldn't be shown properly: ${str(msg.text ?? msg.type)}`, { live });
    }
  },
  onLive: (info) => {
    const { screen } = getState();
    if (info.logged_in && screen !== "chat") setState({ screen: "chat", nick: getState().nick || savedNick() });
    else if (!info.logged_in && screen !== "login" && !reconnecting) {   // (🔁 not while logging back in by itself)
      setState({ screen: "login" });
      focusLogin();
    }
    if (getState().screen === "chat") {
      if (needsCommands()) requestCommands(api.sendLine);
      if (info.logged_in) refreshAll();   // a reloaded tab: fill the panels again
      if (matchMedia("(pointer: fine)").matches) focusInput();  // no surprise keyboard on phones
    }
  },
  onClosed: (reason) => {
    if (quitting) {
      quitting = false;
      resume.forget();
      return showClosed("You left the chat. Bye 👋");
    }
    if (getState().screen === "chat" && resume.canResume()) return reconnect();
    if (getState().screen === "chat") return showClosed(reason);
    resetChat();
    // Still on the login screen: quietly start a fresh connection. Don't show why the old one
    // closed (e.g. the server's login time limit); nobody was logged in to lose anything.
    connect();
  },
  onGap: () => chat.addNotice("system", "✂️ Some older messages were skipped."),
  onReplaced: () => showClosed("This chat is open in another tab. Close that tab, then come back here."),
  onLost: () => (getState().screen === "chat" && resume.canResume() ? reconnect()
    : showClosed("Your session ended. Log in again to keep chatting.")),
});

/** 🔁 The connection dropped: a new session, then log back in with the resume token (a few tries). */
let reconnecting = false;
async function reconnect() {
  if (reconnecting) return;
  reconnecting = true;
  chat.addNotice("system", "🔁 The connection dropped. Reconnecting…");
  for (const wait of RESUME_WAITS) {
    await new Promise((done) => setTimeout(done, wait * 1000));
    if (!resume.canResume()) break;
    api.forgetSession();
    const result = await api.newSession();
    if (!result.ok) continue;   // the website itself isn't back yet
    api.listen();
    await api.whenLive();
    const error = await api.send(resume.resumePacket(FEATURES));
    if (!error) {
      reconnecting = false;
      return;
    }
  }
  reconnecting = false;
  showClosed("Couldn't reconnect. Log in again to keep chatting.");
}

$("reconnect").addEventListener("click", () => {
  setState({ screen: "loading" });
  connect();
});
$("logout").addEventListener("click", async () => {
  resume.forget();
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
    resume.noteLogin(username);
    const error = await api.send({ type: "auth", action, username, password, features: FEATURES });
    if (error) showLoginError(error);
  },
});

initComposer({
  onSubmit: async (text) => {
    if (submitEdit(text)) return true;   // ✏️ we were editing one of our messages
    const lower = text.toLowerCase();
    if (lower === "/sendfile" || lower.startsWith("/sendfile ")) {
      openFilePanel({ to: text.split(/\s+/)[1] || "" });
      return true;
    }
    if (lower === "/ping") {   // 🏓 the server sends the time straight back: the difference is the round trip
      const error = await api.send({ type: "ping", t: Date.now() });
      if (error) showError(error);
      return true;
    }
    if (lower === "/quit") quitting = true;
    const command = lower.split(/\s+/u)[0];
    if (command === "/users" || command === "/balance") youAsked(command.slice(1));   // show you the answer
    const error = await api.sendLine(text);
    if (error) {
      quitting = false;
      showError(error);
      return false;
    }
    chat.clearLit();
    chat.followLatest();   // you just sent something: show it, even if you were reading older messages
    return true;
  },
});

initFiles({ onSent: () => {} });
initSidebar({ onError: showError, closeDrawer: () => { if (narrow.matches) closeDrawer(); } });
initRail({ openGame });
initXray({
  onToggle: (open) => {
    app.classList.toggle("xray-on", open);   // 🔬 the grid makes room: the chat stays usable next to it
    if (open && narrow.matches) closeDrawer();   // (on a phone the button is in the sidebar drawer)
  },
  // on a phone the X-ray button is hidden in the closed sidebar: go back to the ☰ button instead
  focusAfterClose: () => (narrow.matches ? $("open-sidebar") : $("xray-open")).focus(),
});
initTyping();
initEdits();
initRooms({ onError: showError, closeDrawer: () => { if (narrow.matches) closeDrawer(); } });
initProfiles({
  onError: showError,
  applyTheme: (theme) => { applyTheme(theme); rememberTheme(theme); },
  onMessage: (name) => focusInput(`/send ${name} `),
  onChallenge: (name) => { if (narrow.matches) setDrawer("side"); focusChallenge(name); },
});
initNetmap();
initDrawing();
initMarket();
initEconomy();
initGroups({ onError: showError, closeDrawer: () => { if (narrow.matches) closeDrawer(); } });
initVentures({ onError: showError, closeDrawer: () => { if (narrow.matches) closeDrawer(); } });
initFriends({   // 🤝 the same quick buttons as the Online list
  onError: showError,
  onProfile: (name) => showProfile(name),
  onChallenge: (name) => {
    if (!narrow.matches) closeDrawer();
    focusChallenge(name);
  },
  onMessage: (name) => {
    if (narrow.matches) closeDrawer();
    focusInput(`/send ${name} `);
  },
});
initOnline({
  sendLine: api.sendLine,
  onProfile: (name) => showProfile(name),
  onChallenge: (name) => {
    if (!narrow.matches) closeDrawer();
    focusChallenge(name);
  },
  onMessage: (name) => {
    if (narrow.matches) closeDrawer();
    focusInput(`/send ${name} `);
  },
});
setHooks({
  // A game just started. If YOU started it (accepted, /wordle...), open it; if a friend's /accept
  // started it while you were typing, don't steal your focus: the 🎮 Game button lights up instead.
  onNewGame: () => { if (medium.matches && api.sentRecently(/^\/(?:accept|wordle|g)\b/iu, 10_000)) setDrawer("game"); },
  showOnline: () => { if (narrow.matches) setDrawer("side"); },  // you asked who's online: there's the list
  showGame,
});
// The game column only exists while a game or a Wordle is on; otherwise the chat gets the room
subscribe((state) => app.classList.toggle("has-game", Boolean(state.match || state.wordle)));
initPanel({
  showError,
  focusChallenge: () => {
    if (narrow.matches) setDrawer("side");
    else closeDrawer();
    focusChallenge();
  },
});

connect();
