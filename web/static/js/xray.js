// 🔬 Packet X-ray: look inside the network.
//
//   Packets  every JSON packet this tab sends (⬆) and gets (⬇), one line each, as it goes over the wire.
//   TCP      the raw bytes the bridge got from each recv() on its TCP socket to the chat server, and what it
//            sent with sendall(). TCP is a stream: a chunk can end in the middle of a packet, or hold several.
//
// The bridge only records raw TCP while this window is open ({"type": "xray", "on": true}), and never
// a login packet (it has your password). Everything is shown with textContent: it's data, never HTML.

import { $, clear, el } from "./dom.js";
import { send, watchPackets } from "./api.js";

const MAX_ROWS = 300;
const encoder = new TextEncoder();
const lists = { packets: $("xray-packets"), tcp: $("xray-tcp") };
const tabs = [$("xray-tab-packets"), $("xray-tab-tcp")];
let paused = false;
let recvCount = 0;

const bytesOf = (text) => encoder.encode(text).length;

function clock(seconds) {
  const t = new Date(seconds * 1000);
  return `${t.toLocaleTimeString("en-GB", { hour12: false })}.${String(t.getMilliseconds()).padStart(3, "0")}`;
}

/** Newlines are where packets end: show them as ⏎ so you can see the boundaries inside a chunk. */
const showNewlines = (text) => text.replace(/\n/gu, "⏎\n");

function addRow(list, row) {
  const atBottom = list.parentElement.scrollHeight - list.parentElement.scrollTop - list.parentElement.clientHeight < 40;
  list.append(row);
  while (list.childElementCount > MAX_ROWS) list.firstElementChild.remove();
  if (atBottom) list.parentElement.scrollTop = list.parentElement.scrollHeight;
  $("xray-count").textContent = `${lists.packets.childElementCount} packets · ${lists.tcp.childElementCount} TCP chunks`;
}

/** "⬇ in  chat  42 B  19:26" on screen; "received, chat, 42 B, 19:26" for screen readers. */
function head(dir, ...parts) {
  return el("p", { class: "xray-row-head" },
    el("span", { class: `xray-dir xray-${dir}` },
      el("span", { "aria-hidden": "true", text: dir === "in" ? "⬇ in" : "⬆ out" }),
      el("span", { class: "visually-hidden", text: dir === "in" ? "received" : "sent" })),
    ...parts.map((text) => el("span", {}, el("span", { class: "visually-hidden", text: ", " }), text)));
}

function announce(text) {
  $("xray-status").textContent = text;
}

function packetRow(dir, packet, wireText) {
  const secret = packet.type === "auth" || packet.type === "change_password";   // never show a password
  const shown = secret ? JSON.stringify({ ...packet, ...(packet.password ? { password: "•••" } : {}), ...(packet.token ? { token: "•••" } : {}),
    ...(packet.old ? { old: "•••", new: "•••" } : {}) }) : wireText;
  return el("li", { class: "xray-row" },
    head(dir, String(packet.type ?? "?"), `${bytesOf(wireText) + 1} B`, clock(Date.now() / 1000)),
    el("pre", { class: "xray-body", text: shown }));
}

function tcpRow(chunk) {
  const text = String(chunk.text ?? "");
  const lineEnds = (text.match(/\n/gu) || []).length;
  const label = chunk.dir === "in" ? `recv() #${++recvCount}` : "sendall()";
  const split = text.endsWith("\n") ? `${lineEnds} packet${lineEnds === 1 ? "" : "s"}`
    : `${lineEnds} packet${lineEnds === 1 ? "" : "s"} + the start of one more ✂️`;
  return el("li", { class: "xray-row" },
    head(chunk.dir === "in" ? "in" : "out", label, `${chunk.bytes} B`, split, clock(Number(chunk.time) || Date.now() / 1000)),
    el("pre", { class: "xray-body", text: showNewlines(text) }));
}

function watch(dir, packet, wireText) {
  if (paused || !$("xray").open) return;
  if (packet.type === "xray") {
    if (dir === "in") addRow(lists.tcp, tcpRow(packet));   // a raw chunk reported by the bridge
    return;                                                // ("out" xray packets are just our on/off switch)
  }
  addRow(lists.packets, packetRow(dir, packet, wireText));
}

function selectTab(index) {
  tabs.forEach((tab, i) => {
    const selected = i === index;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    $(tab.getAttribute("aria-controls")).hidden = !selected;
  });
  tabs[index].focus();
}

export function initXray() {
  const dialog = $("xray");
  watchPackets(watch);
  $("xray-open").addEventListener("click", () => {
    dialog.showModal();
    send({ type: "xray", on: true });
  });
  $("xray-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    send({ type: "xray", on: false });
    $("xray-open").focus();
  });
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => selectTab(i));
    tab.addEventListener("keydown", (event) => {   // arrow keys move between tabs (the ARIA tabs pattern)
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        event.preventDefault();
        selectTab((i + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length);
      }
    });
  });
  $("xray-pause").addEventListener("click", (event) => {
    paused = !paused;
    clear(event.currentTarget).append(el("span", { "aria-hidden": "true", text: paused ? "▶ " : "⏸ " }),
      paused ? "Resume" : "Pause");
    announce(paused ? "Capture paused" : "Capture resumed");
  });
  $("xray-clear").addEventListener("click", () => {
    clear(lists.packets);
    clear(lists.tcp);
    recvCount = 0;
    $("xray-count").textContent = "";
    announce("Cleared");
  });
}
