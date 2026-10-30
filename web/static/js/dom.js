// 🧱 Tiny DOM helpers. Everything from the server goes in as text (textContent / text nodes),
// never as HTML, so a message like "<img onerror=...>" just shows up as those characters.

/**
 * el("button", { class: "btn", text: "Hi", onclick: fn, "aria-label": "Say hi" }, child, ...)
 * Attribute names always come from our own code; only values may come from the server.
 */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = String(value);
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : String(child));
  }
  return node;
}

export const $ = (id) => document.getElementById(id);

export function clear(node) {
  node.replaceChildren();
  return node;
}

// Bidi overrides can make "gpj.exe" read as "exe.jpg": nobody types them, so drop them
const BIDI_OVERRIDES = /[\u202a-\u202e\u2066-\u2069]/gu;

/** Any value from the server, as plain text. */
export function str(value, fallback = "") {
  const text = typeof value === "string" ? value : value === undefined || value === null ? fallback : String(value);
  return text.replace(BIDI_OVERRIDES, "");
}
