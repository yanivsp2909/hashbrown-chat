// ⌨️ The message box: Enter sends, Up/Down walks your history, "/" opens command suggestions.

import { $, clear, el } from "./dom.js";
import { getState } from "./store.js";
import { stopMyTyping } from "./typing.js";

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

function closeSuggestions() {
  box.hidden = true;
  input.setAttribute("aria-expanded", "false");
  input.removeAttribute("aria-activedescendant");
  matches = [];
}

function renderSuggestions() {
  const text = input.value;
  const typingCommand = text.startsWith("/") && !text.includes(" ");
  const commands = getState().commands;
  matches = typingCommand
    ? commands.filter((c) => c.name.startsWith(text.toLowerCase())).slice(0, MAX_SUGGESTIONS)
    : [];
  if (!matches.length) return closeSuggestions();
  selected = Math.min(selected, matches.length - 1);
  clear(box);
  matches.forEach((command, i) => {
    box.append(el("li", {
      id: `suggestion-${i}`, role: "option", "aria-selected": String(i === selected),
      onmousedown: (event) => { event.preventDefault(); pick(i); },
    }, el("span", { class: "usage", text: command.usage }), el("span", { class: "desc", text: command.description })));
  });
  box.hidden = false;
  input.setAttribute("aria-expanded", "true");
  input.setAttribute("aria-activedescendant", `suggestion-${selected}`);
}

function pick(i) {
  const command = matches[i];
  if (!command) return;
  const takesArgs = command.usage.includes(" ");
  input.value = command.name + (takesArgs ? " " : "");
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
  input.addEventListener("blur", () => setTimeout(closeSuggestions, 100));
  input.addEventListener("keydown", (event) => {
    if (event.isComposing) return;   // Enter that finishes an IME composition isn't a command
    if (!box.hidden && matches.length) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        selected = (selected + (event.key === "ArrowDown" ? 1 : -1) + matches.length) % matches.length;
        return renderSuggestions();
      }
      if (event.key === "Tab" || (event.key === "Enter" && input.value !== matches[selected].name)) {
        event.preventDefault();
        return pick(selected);
      }
      if (event.key === "Escape") return closeSuggestions();
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
