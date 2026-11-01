// 🔬 Packet X-ray: look inside the network.
//
//   Packets  every JSON packet this tab sends (⬆) and gets (⬇), one line each, as it goes over the wire.
//   TCP      the raw bytes the bridge got from each recv() on its TCP socket to the chat server, and what it
//            sent with sendall(). TCP is a stream: a chunk can end in the middle of a packet, or hold several.
//
// It's a side panel (a drawer on a phone), not a modal: you can chat and play while it runs. It records from
// page load, open or not (xraylog.js keeps the newest 500 of each), so opening it shows what already happened.
// The bridge sends the raw TCP because api.js asks for it when it makes the session ({"xray": true}); it never
// shows a login packet (it has your password). Everything is shown with textContent: it's data, never HTML.

import { $, clear, el } from "./dom.js";
import { watchPackets } from "./api.js";
import { XRAY_KEEP, chunkTypes, hideSecrets, makeLog, matches } from "./xraylog.js";

const encoder = new TextEncoder();
const logs = { packets: makeLog(), tcp: makeLog() };
const lists = { packets: $("xray-packets"), tcp: $("xray-tcp") };
const tabs = [$("xray-tab-packets"), $("xray-tab-tcp")];
const rows = new Map();   // entry -> its <li>, while it's on screen (so a dropped entry's row goes too)
let paused = false;
let recvCount = 0;
let filter = "";
let hooks = { onToggle: () => {}, focusAfterClose: () => $("xray-open").focus() };

const bytesOf = (text) => encoder.encode(text).length;
const isOpen = () => !$("xray").hidden;

function clock(seconds) {
  const t = new Date(seconds * 1000);
  return `${t.toLocaleTimeString("en-GB", { hour12: false })}.${String(t.getMilliseconds()).padStart(3, "0")}`;
}

/** Newlines are where packets end: show them as ⏎ so you can see the boundaries inside a chunk. */
const showNewlines = (text) => text.replace(/\n/gu, "⏎\n");

function announce(text) {
  const status = $("xray-status");
  status.textContent = "";   // empty first, so the same words (Clear, Clear) are read again
  setTimeout(() => { status.textContent = text; }, 60);
}

// ----- remembering (always, from page load)

function packetEntry(dir, packet, wireText, live) {
  return { kind: "packets", dir, types: [String(packet.type ?? "?")], bytes: bytesOf(wireText) + 1,
    time: Date.now() / 1000, text: hideSecrets(packet, wireText), replayed: !live };   // never keep a secret
}

function tcpEntry(chunk, live) {
  const text = String(chunk.text ?? "");
  const dir = chunk.dir === "in" ? "in" : "out";
  return { kind: "tcp", dir, types: chunkTypes(text), bytes: Number(chunk.bytes) || 0, text,
    time: Number(chunk.time) || Date.now() / 1000, replayed: !live,
    label: dir === "in" ? `recv() #${++recvCount}` : "sendall()" };
}

function watch(dir, packet, wireText, live = true) {
  if (paused) return;
  if (packet.type === "xray") {
    if (dir === "in") remember(tcpEntry(packet, live));   // a raw chunk reported by the bridge
    return;
  }
  remember(packetEntry(dir, packet, wireText, live));
}

function remember(entry) {
  const dropped = logs[entry.kind].add(entry);
  if (dropped) forgetRow(dropped);
  if (isOpen() && matches(entry, filter)) addRow(entry);
  if (isOpen()) {
    updateFilterMenu();
    updateCount();
  }
}

// ----- showing (only while the panel is open)

/** "⬇ in  chat  42 B  19:26" on screen; "received, chat, 42 B, 19:26" for screen readers. */
function head(entry, ...parts) {
  const words = entry.dir === "in" ? ["⬇ in", "received"] : ["⬆ out", "sent"];
  return el("p", { class: "xray-row-head" },
    el("span", { class: `xray-dir xray-${entry.dir}` },
      el("span", { "aria-hidden": "true", text: words[0] }),
      el("span", { class: "visually-hidden", text: words[1] })),
    ...parts.map((text) => el("span", {}, el("span", { class: "visually-hidden", text: ", " }), text)),
    ...(entry.replayed ? [el("span", { class: "xr-replayed" }, el("span", { class: "visually-hidden", text: ", " }),
      el("span", { "aria-hidden": "true", text: "↺ " }), "replayed after a reload")] : []));
}

function tcpSplit(text) {
  const lineEnds = (text.match(/\n/gu) || []).length;
  const packets = `${lineEnds} packet${lineEnds === 1 ? "" : "s"}`;
  if (text.endsWith("\n")) return packets;
  return el("span", {}, `${packets} + the start of one more`, el("span", { "aria-hidden": "true", text: " ✂️" }));
}

function rowFor(entry) {
  if (entry.kind === "packets") {
    return el("li", { class: "xray-row" },
      head(entry, entry.types[0], `${entry.bytes} B`, clock(entry.time)),
      el("pre", { class: "xray-body", text: entry.text }));
  }
  return el("li", { class: "xray-row" },
    head(entry, entry.label, `${entry.bytes} B`, tcpSplit(entry.text), clock(entry.time)),
    el("pre", { class: "xray-body", text: showNewlines(entry.text) }));
}

const scroller = (list) => list.parentElement;
const nearBottom = (box) => box.scrollHeight - box.scrollTop - box.clientHeight < 40;

function addRow(entry) {
  const list = lists[entry.kind];
  // reading older rows (scrolled up, or moving through the list with a keyboard)? then don't jump to the bottom
  const follow = nearBottom(scroller(list)) && !scroller(list).contains(document.activeElement);
  const row = rowFor(entry);
  rows.set(entry, row);
  list.append(row);
  if (follow) scroller(list).scrollTop = scroller(list).scrollHeight;
}

function forgetRow(entry) {
  rows.get(entry)?.remove();
  rows.delete(entry);
}

function renderAll() {
  rows.clear();
  for (const [kind, list] of Object.entries(lists)) {
    clear(list).append(...logs[kind].list(filter).map((entry) => {
      const row = rowFor(entry);
      rows.set(entry, row);
      return row;
    }));
    scroller(list).scrollTop = scroller(list).scrollHeight;
  }
  updateFilterMenu();
  updateCount();
}

/** The filter menu lists every packet type seen so far. New types are slotted in (A to Z) without rebuilding
 * the menu, so an open menu or a screen reader's place isn't lost. Types that are gone stay until a Clear. */
function updateFilterMenu() {
  const menu = $("xray-filter");
  for (const type of [...logs.packets.types(), ...logs.tcp.types()]) {
    const options = [...menu.options].slice(1);
    if (options.some((option) => option.value === type)) continue;
    const next = options.find((option) => option.value > type);
    menu.insertBefore(el("option", { value: type, text: type }), next ?? null);
  }
}

function updateCount() {
  const packets = logs.packets.list().length;
  const tcp = logs.tcp.list().length;
  const showing = filter ? ` · showing ${logs.packets.list(filter).length} + ${logs.tcp.list(filter).length} with “${filter}”` : "";
  $("xray-count").textContent = `${packets} packets · ${tcp} TCP chunks (newest ${XRAY_KEEP} kept)${showing}${paused ? " · ⏸ paused" : ""}`;
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

// ----- opening and closing (the panel never blocks the page: no backdrop, no focus trap)

export function setXrayOpen(open) {
  if (open === isOpen()) return;
  $("xray").hidden = !open;
  $("xray-open").setAttribute("aria-expanded", String(open));
  hooks.onToggle(open);
  if (open) {
    renderAll();
    $("xray-title").focus();
  } else {
    rows.clear();
    clear(lists.packets);
    clear(lists.tcp);
    hooks.focusAfterClose();
  }
}

function togglePause(event) {
  paused = !paused;
  clear(event.currentTarget).append(el("span", { "aria-hidden": "true", text: paused ? "▶ " : "⏸ " }),
    paused ? "Resume" : "Pause");
  updateCount();
  announce(paused ? "Recording paused" : "Recording again");
}

function clearAll() {
  logs.packets.empty();
  logs.tcp.empty();
  recvCount = 0;
  filter = "";
  clear($("xray-filter")).append(el("option", { value: "", text: "All types" }));
  renderAll();
  announce("Cleared");
}

function wireTabs() {
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => selectTab(i));
    tab.addEventListener("keydown", (event) => {   // arrow keys move between tabs (the ARIA tabs pattern)
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        event.preventDefault();
        selectTab((i + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length);
      } else if (event.key === "Home" || event.key === "End") {
        event.preventDefault();
        selectTab(event.key === "Home" ? 0 : tabs.length - 1);
      }
    });
  });
}

/** hooks.onToggle(open): the page makes room for the panel; hooks.focusAfterClose(): where focus goes back to. */
export function initXray(nextHooks = {}) {
  hooks = { ...hooks, ...nextHooks };
  watchPackets(watch);
  $("xray-open").addEventListener("click", () => setXrayOpen(!isOpen()));
  $("xray-close").addEventListener("click", () => setXrayOpen(false));
  $("xray").addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !event.defaultPrevented) {
      event.preventDefault();
      setXrayOpen(false);
    }
  });
  wireTabs();
  $("xray-filter").addEventListener("change", (event) => {
    filter = event.currentTarget.value;
    renderAll();
    announce(filter ? `Showing only ${filter} packets` : "Showing every packet type");
  });
  $("xray-pause").addEventListener("click", togglePause);
  $("xray-clear").addEventListener("click", clearAll);
}
