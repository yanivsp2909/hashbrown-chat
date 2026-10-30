// ✓✓ Read receipts for private messages. Your copy of a /send has "pm": {"id", "status"}; {"type": "receipt"}
// packets move it on to ✓ delivered and ✓✓ seen. When someone's private message to you is on screen (and the
// tab is in front), we tell the server {"type": "seen", "id"} once.

import { $, el } from "./dom.js";
import { send } from "./api.js";

const ORDER = { sent: 0, delivered: 1, seen: 2 };
const SHOWN = { sent: ["", "Sent"], delivered: ["✓", "Delivered"], seen: ["✓✓", "Seen"] };
const watching = new Map();   // a private message card on screen -> its number (waiting for the tab to be in front)
let observer = null;

/** The little ✓ / ✓✓ in the header of your own private message. */
export function receiptMark(pm) {
  const status = Object.hasOwn(ORDER, pm?.status) ? pm.status : "sent";
  const [mark, words] = SHOWN[status];
  return el("span", { class: `receipt receipt-${status}`, "data-pm-id": String(pm.id), "data-status": status, title: words },
    el("span", { "aria-hidden": "true", text: mark }), el("span", { class: "visually-hidden", text: ` ${words}` }));
}

/** {"type": "receipt", "id", "status"}: only ever moves forward (a late "delivered" never undoes "seen"). */
export function applyReceipt(msg) {
  if (!Number.isInteger(msg.id) || !Object.hasOwn(ORDER, msg.status)) return;
  for (const old of document.querySelectorAll(`.receipt[data-pm-id="${msg.id}"]`)) {
    if (ORDER[msg.status] > ORDER[old.dataset.status]) old.replaceWith(receiptMark({ id: msg.id, status: msg.status }));
  }
}

function tellSeen(node) {
  const id = watching.get(node);
  watching.delete(node);
  delete node.dataset.waiting;
  observer.unobserve(node);
  send({ type: "seen", id });
}

function onSight(entries) {
  for (const entry of entries) {
    if (entry.isIntersecting && !document.hidden) tellSeen(entry.target);
    else if (entry.isIntersecting) entry.target.dataset.onScreen = "1";
    else delete entry.target.dataset.onScreen;
  }
}

/** Say "seen" for this card (a private message to you) once it's really on screen. */
export function watchSeen(node, id) {
  if (!Number.isInteger(id) || typeof IntersectionObserver !== "function") return;
  if (!observer) {
    observer = new IntersectionObserver(onSight, { root: $("messages"), threshold: 0.6 });
    document.addEventListener("visibilitychange", () => {   // back to this tab: what's on screen is seen now
      if (!document.hidden) for (const node of [...watching.keys()]) if (node.dataset.onScreen) tellSeen(node);
    });
  }
  watching.set(node, id);
  observer.observe(node);
}
