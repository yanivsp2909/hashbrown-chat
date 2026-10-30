// ⌨️ The message box: Enter sends, Up/Down walks your history, "/" opens command suggestions.

import { $, clear, el } from "./dom.js";
import { getState } from "./store.js";
import { stopMyTyping } from "./typing.js";
import { matchingNames, mentionAt, mentionNames } from "./mentions.js";

const MAX_HISTORY = 50;
const MAX_SUGGESTIONS = 8;

const form = $("composer");
const input = $("input");
const box = $("suggestions");
const history = [];
let historyPos = 0;
let draft = "";
let matches = [];
let selected = 0;
let arrowed = false;        // did you move through the list with the arrow keys?
let shownStatus = "";

/** "3 people to mention" for screen readers, only when the count or the kind of list changes. */
function announce(text) {
  if (text === shownStatus) return;
  shownStatus = text;
  $("suggest-status").textContent = text;
}

function closeSuggestions() {
  announce("");
  arrowed = false;
  box.hidden = true;
  input.setAttribute("aria-expanded", "false");
  input.removeAttribute("aria-activedescendant");
  matches = [];
}

function commandMatches(text) {
  if (!text.startsWith("/") || text.includes(" ")) return [];
  return getState().commands.filter((c) => c.name.startsWith(text.toLowerCase())).slice(0, MAX_SUGGESTIONS)
    .map((c) => ({
      label: c.usage, desc: c.description, done: () => input.value === c.name,   // typed it all: Enter sends it
      apply: () => { input.value = c.name + (c.usage.includes(" ") ? " " : ""); },
    }));
}

function mentionMatches() {
  const mention = mentionAt(input.value, input.selectionStart ?? input.value.length);
  if (!mention || input.value.startsWith("/")) return [];
  return matchingNames(mentionNames(getState()), mention.word).slice(0, MAX_SUGGESTIONS)
    .map((name) => ({
      label: `@${name}`, desc: name === "hashbrown" ? "ask Hashbrown" : "",
      done: () => mention.word === name,
      apply: () => {
        const after = input.value.slice(mention.end).replace(/^\s*/u, " ");
        input.value = `${input.value.slice(0, mention.start)}@${name}${after}`;
        const caret = mention.start + name.length + 2;
        input.setSelectionRange(caret, caret);
      },
    }));
}

function renderSuggestions() {
  const commands = commandMatches(input.value);
  matches = commands.length ? commands : mentionMatches();
  if (!matches.length) return closeSuggestions();
  selected = Math.min(selected, matches.length - 1);
  box.setAttribute("aria-label", commands.length ? "Commands" : "People to mention");
  clear(box);
  matches.forEach((match, i) => {
    box.append(el("li", {
      id: `suggestion-${i}`, role: "option", "aria-selected": String(i === selected),
      onmousedown: (event) => { event.preventDefault(); pick(i); },
    }, el("span", { class: "usage", dir: "auto", text: match.label }),
    match.desc ? el("span", { class: "desc", text: match.desc }) : null));
  });
  box.hidden = false;
  input.setAttribute("aria-expanded", "true");
  input.setAttribute("aria-activedescendant", `suggestion-${selected}`);
  const n = matches.length;
  announce(commands.length ? `${n} command${n === 1 ? "" : "s"}` : `${n} ${n === 1 ? "person" : "people"} to mention`);
}

/** Arrow keys: move the highlight without rebuilding the list (screen readers keep their place). */
function moveSelection(step) {
  selected = (selected + step + matches.length) % matches.length;
  arrowed = true;
  for (const [i, option] of [...box.children].entries()) option.setAttribute("aria-selected", String(i === selected));
  input.setAttribute("aria-activedescendant", `suggestion-${selected}`);
  box.children[selected]?.scrollIntoView({ block: "nearest" });
}

function pick(i) {
  const match = matches[i];
  if (!match) return;
  match.apply();
  closeSuggestions();
  input.focus();
}

function walkHistory(step) {
  if (!history.length) return;
  if (historyPos === history.length) draft = input.value;
  historyPos = Math.min(Math.max(historyPos + step, 0), history.length);
  input.value = historyPos === history.length ? draft : history[historyPos];
  requestAnimationFrame(() => input.setSelectionRange(input.value.length, input.value.length));
}

/** onSubmit(text) returns true if the text was handled and should go into history. */
export function initComposer({ onSubmit }) {
  input.addEventListener("input", () => {
    selected = 0;
    renderSuggestions();
  });
  input.addEventListener("blur", () => setTimeout(() => {   // only if you really left the box
    if (document.activeElement !== input) closeSuggestions();
  }, 100));
  input.addEventListener("keydown", (event) => {
    if (event.isComposing) return;   // Enter that finishes an IME composition isn't a command
    if (!box.hidden && matches.length) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        return moveSelection(event.key === "ArrowDown" ? 1 : -1);
      }
      // Tab inserts a command, or a person you chose with the arrows; otherwise it leaves the box as usual
      const tabPicks = event.key === "Tab" && (input.value.startsWith("/") || arrowed);
      if (tabPicks || (event.key === "Enter" && !matches[selected].done())) {
        event.preventDefault();
        return pick(selected);
      }
      if (event.key === "Tab") return closeSuggestions();
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();   // only the list closes, nothing else that listens for Escape
        return closeSuggestions();
      }
    }
    if (event.key === "ArrowUp" && !input.value.includes("\n")) {
      event.preventDefault();
      walkHistory(-1);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      walkHistory(1);
    }
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    closeSuggestions();
    input.value = "";
    stopMyTyping();   // ⌨️ the others stop seeing "is typing…" now, and your next message starts fresh
    const keep = await onSubmit(text);
    if (keep === false) {
      if (!input.value) input.value = text;  // it failed: give the text back (unless they're typing again)
      return;
    }
    if (history[history.length - 1] !== text) history.push(text);
    if (history.length > MAX_HISTORY) history.shift();
    historyPos = history.length;
  });
}

export function focusInput(text) {
  if (typeof text === "string") input.value = text;
  input.focus();
}
