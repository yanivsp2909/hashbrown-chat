// 🗺️ The live network map: the server in the middle, every connected player around it, and the packets flying
// along the lines (towards the server: what they sent; away from it: what they got), coloured by type, with each
// player's ping. Only counts and types: the server never puts message content in the map.
// {"type": "get_netmap"} opens it; {"type": "netmap"} comes once a second; {"type": "netmap_closed"} stops it.

import { $, clear, el, str } from "./dom.js";
import { send } from "./api.js";

const SVG = "http://www.w3.org/2000/svg";
const W = 640;
const H = 420;
const CENTER = { x: W / 2, y: H / 2 };
const RADIUS = 160;
const FLIGHT_MS = 900;         // a packet's trip along its line
const MAX_DOTS = 6;            // per player and direction per second (more just means "busy")
const KINDS = [                // type -> colour group (legend order)
  ["chat", "💬 Chat", ["chat", "line", "stream", "typing", "typing_stop", "react", "reactions", "edit", "edited", "delete", "deleted"]],
  ["game", "🎮 Games", ["board"]],
  ["file", "📁 Files", ["file", "file_start", "file_chunk", "file_ack", "file_end", "file_cancel"]],
  ["net", "🏓 Ping", ["ping", "pong", "probe", "probe_back"]],
  ["other", "📦 Other", []],
];
const kindOf = (type) => (KINDS.find(([, , types]) => types.includes(type)) || KINDS[KINDS.length - 1])[0];
const still = matchMedia("(prefers-reduced-motion: reduce)");
let players = [];
let positions = {};

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  node.append(...children);
  return node;
}

const total = (counts) => Object.values(counts || {}).reduce((a, b) => a + (Number.isFinite(b) ? b : 0), 0);

const SERVER_R = 36;           // the server's circle; its label must fit inside
const LABEL_MAX = SERVER_R * 2 - 16;

/** "🖥️" over "Server", both inside the circle (on top of the lines). A font that runs wider is squeezed to fit. */
function serverLabel() {
  const word = svg("text", { x: CENTER.x, y: CENTER.y + 15, class: "nm-server-label", "text-anchor": "middle" }, "Server");
  const icon = svg("text", { x: CENTER.x, y: CENTER.y + 1, class: "nm-server-icon", "text-anchor": "middle", "aria-hidden": "true" }, "🖥️");
  return [icon, word];
}

function fit(label) {
  if (label.getComputedTextLength && label.getComputedTextLength() > LABEL_MAX) {
    label.setAttribute("textLength", String(LABEL_MAX));
    label.setAttribute("lengthAdjust", "spacingAndGlyphs");
  }
}

function draw() {
  const map = clear($("netmap-svg"));
  positions = {};
  players.forEach((p, i) => {
    const angle = (i / Math.max(players.length, 1)) * Math.PI * 2 - Math.PI / 2;
    positions[p.name] = { x: CENTER.x + Math.cos(angle) * RADIUS, y: CENTER.y + Math.sin(angle) * RADIUS };
  });
  // the lines first, so the server and the players sit on top of them
  map.append(...players.map((p) => svg("line", { x1: CENTER.x, y1: CENTER.y, x2: positions[p.name].x, y2: positions[p.name].y, class: "nm-link" })));
  const [icon, word] = serverLabel();
  map.append(svg("circle", { cx: CENTER.x, cy: CENTER.y, r: SERVER_R, class: "nm-server" }), icon, word);
  fit(word);
  fit(icon);
  for (const p of players) {
    const pos = positions[p.name];
    const ping = Number.isFinite(p.ping_ms) ? `${Math.round(p.ping_ms)} ms` : "ping ?";
    map.append(
      svg("circle", { cx: pos.x, cy: pos.y, r: 16, class: "nm-player" }),
      svg("text", { x: pos.x, y: pos.y + 32, class: "nm-name", "text-anchor": "middle" }, str(p.name)),
      svg("text", { x: pos.x, y: pos.y + 48, class: "nm-ping", "text-anchor": "middle" }, ping));
  }
}

/** One packet dot flying along a line (towards the server when `up`). */
function fly(from, to, kind, delay) {
  const dot = svg("circle", { r: 5, class: `nm-dot nm-${kind}`, cx: from.x, cy: from.y });
  $("netmap-svg").append(dot);
  const start = performance.now() + delay;
  const step = (now) => {
    const t = Math.min(1, Math.max(0, (now - start) / FLIGHT_MS));
    dot.setAttribute("cx", String(from.x + (to.x - from.x) * t));
    dot.setAttribute("cy", String(from.y + (to.y - from.y) * t));
    if (t < 1) requestAnimationFrame(step);
    else dot.remove();
  };
  requestAnimationFrame(step);
}

const MAX_LIVE_DOTS = 200;     // never more dots flying at once than this

function animate() {
  if (still.matches || document.hidden) return;   // (a hidden tab doesn't animate: don't pile dots up)
  if ($("netmap-svg").querySelectorAll(".nm-dot").length > MAX_LIVE_DOTS) return;
  for (const p of players) {
    const pos = positions[p.name];
    if (!pos) continue;
    for (const [counts, from, to] of [[p.in, pos, CENTER], [p.out, CENTER, pos]]) {
      let n = 0;
      for (const [type, count] of Object.entries(counts || {})) {
        for (let i = 0; i < count && n < MAX_DOTS; i += 1, n += 1) fly(from, to, kindOf(type), n * (900 / MAX_DOTS));
      }
    }
  }
}

function table() {
  const rows = players.map((p) => el("tr", {},
    el("th", { scope: "row", dir: "auto", text: str(p.name) }),
    el("td", { dir: "auto", text: str(p.room) }),
    el("td", { class: "nm-num", text: Number.isFinite(p.ping_ms) ? `${Math.round(p.ping_ms)} ms` : "?" }),
    el("td", { class: "nm-num", text: String(total(p.in)) }),
    el("td", { class: "nm-num", text: String(total(p.out)) })));
  clear($("netmap-table")).append(
    el("caption", { class: "visually-hidden", text: "Players: room, ping and packets in the last second" }),
    el("thead", {}, el("tr", {}, ["Player", "Room", "Ping", "⬆ Sent", "⬇ Got"].map((h) => el("th", { scope: "col", text: h })))),
    el("tbody", {}, rows));
}

export function onMap(msg) {
  if (!$("netmap").open || !Array.isArray(msg.players)) return;
  const names = JSON.stringify(msg.players.map((p) => p && p.name));
  const changed = names !== JSON.stringify(players.map((p) => p.name));
  players = msg.players.filter((p) => p && typeof p.name === "string");
  if (changed) draw();
  else for (const p of players) {   // just the ping labels
    const label = [...$("netmap-svg").querySelectorAll(".nm-name")].find((t) => t.textContent === p.name)?.nextSibling;
    if (label) label.textContent = Number.isFinite(p.ping_ms) ? `${Math.round(p.ping_ms)} ms` : "ping ?";
  }
  animate();
  table();
}

/** The server's ping probe: answer at once (that's what it measures). */
export function onProbe(msg) {
  if (Number.isInteger(msg.id)) send({ type: "probe_back", id: msg.id });
}

export function initNetmap() {
  const dialog = $("netmap");
  $("netmap-legend").append(...KINDS.map(([kind, label]) => el("li", {}, el("span", { class: `nm-key nm-${kind}`, "aria-hidden": "true" }), label)));
  $("netmap-open").addEventListener("click", () => {
    players = [];
    dialog.showModal();
    draw();   // (after showModal: the label can only be measured on screen)
    send({ type: "get_netmap" });
  });
  $("netmap-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    send({ type: "netmap_closed" });
    $("netmap-open").focus();
  });
}
