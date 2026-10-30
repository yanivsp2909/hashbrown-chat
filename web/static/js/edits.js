// ✏️🗑️ Editing and deleting your own messages (the server allows it for a few minutes after sending).
// Edit: the text goes into the message box; Enter saves it, Esc cancels. Delete: press 🗑️ twice.

import { $, el } from "./dom.js";
import { send } from "./api.js";

let editing = null;   // the id of the message being edited, or null

function showBanner(text) {
  const banner = $("edit-banner");
  banner.textContent = text;
  banner.hidden = !text;
}

export function startEdit(id, text) {
  editing = id;
  const input = $("input");
  input.value = text;
  input.focus();
  showBanner("✏️ Editing your message: Enter saves it, Esc cancels.");
}

export function cancelEdit() {
  if (editing === null) return false;
  editing = null;
  $("input").value = "";
  showBanner("");
  return true;
}

/** The message box was submitted: if we're editing, send the new text. Returns true if it was an edit. */
export function submitEdit(text) {
  if (editing === null) return false;
  const id = editing;
  editing = null;
  showBanner("");
  send({ type: "edit", id, text });
  return true;
}

/** The ✏️ and 🗑️ buttons under one of your own messages. */
export function ownButtons(id, getText) {
  let armed = null;
  const remove = el("button", { class: "reaction-add", type: "button", "aria-label": "Delete this message" }, "🗑️");
  remove.addEventListener("click", () => {
    if (armed) {
      clearTimeout(armed);
      send({ type: "delete", id });
      return;
    }
    remove.textContent = "Delete?";
    armed = setTimeout(() => { armed = null; remove.textContent = "🗑️"; }, 3000);
  });
  return [el("button", { class: "reaction-add", type: "button", "aria-label": "Edit this message",
    onclick: () => startEdit(id, getText()) }, "✏️"), remove];
}

/** {"type": "edited"} / {"type": "deleted"} from the server. */
export function applyEdit(msg) {
  const bubble = document.querySelector(`#messages [data-id="${CSS.escape(String(msg.id))}"]`);
  if (!bubble) return;
  if (msg.type === "deleted") {
    bubble.remove();
    return;
  }
  const text = bubble.querySelector(".msg-text");
  if (text) text.textContent = String(msg.text ?? "");
  if (!bubble.querySelector(".edited")) text?.after(el("span", { class: "edited", text: "(edited)" }));
}

export function initEdits() {
  $("input").addEventListener("keydown", (event) => {
    if (event.key === "Escape" && cancelEdit()) event.preventDefault();
  });
}
