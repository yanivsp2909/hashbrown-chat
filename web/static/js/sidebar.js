// 🧭 Sidebar: where you are, one-click commands and the challenge helper.
// (Who's online and your balance live in online.js.)

import { $, clear, el } from "./dom.js";
import { sendLine } from "./api.js";
import { subscribe } from "./store.js";

const QUICK = [
  ["🎯", "Quests", "/quests"],
  ["🎁", "Daily", "/daily"],
  ["🎮", "Games", "/games"],
  ["🟩", "Wordle", "/wordle"],
  ["🏅", "Trophies", "/achievements"],
  ["📖", "Help", "/help"],
];
const QUICK_COOLDOWN = 700;   // ms: the server allows 8 messages per 5 seconds

export function initSidebar({ onError, closeDrawer }) {
  const grid = $("quick-buttons");
  let lastQuick = 0;
  for (const [icon, label, command] of QUICK) {
    grid.append(el("button", {
      class: "btn btn-ghost", type: "button", title: command,
      onclick: async () => {
        if (Date.now() - lastQuick < QUICK_COOLDOWN) return;
        lastQuick = Date.now();
        closeDrawer();
        const error = await sendLine(command);
        if (error) onError(error);
      },
    }, el("span", { "aria-hidden": "true", text: icon }), el("span", { text: label })));
  }

  $("challenge-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = $("challenge-name").value.trim().replace(/^@/, "");
    const bet = Number.parseInt($("challenge-bet").value, 10);
    if (!/^\S{1,16}$/.test(name)) return onError("Type the name of who you want to play.");
    const command = `/challenge ${name} ${$("challenge-game").value}${bet > 0 ? ` ${bet}` : ""}`;
    const error = await sendLine(command);
    if (error) return onError(error);
    closeDrawer();
  });

  const datalist = $("known-names");
  let shownNames = null;
  subscribe((state) => {
    $("room-title").textContent = state.room;
    $("chat-room").textContent = state.room;
    $("me-nick").textContent = state.nick || "…";
    if (state.knownNames !== shownNames) {
      shownNames = state.knownNames;
      clear(datalist).append(...state.knownNames.filter((n) => n !== state.nick).map((n) => el("option", { value: n })));
    }
  });
}

/** Focus the challenge form, e.g. from the empty game panel, optionally with a name filled in. */
export function focusChallenge(name) {
  if (typeof name === "string") $("challenge-name").value = name;
  $("challenge-name").focus();
}
