// 🎨 The drawing game's board, above the chat. The drawer paints with the mouse or a finger; every short piece of
// a line goes to the server as one small {"type": "stroke"} packet (you can watch them in Packet X-ray), and the
// others see it appear. They guess in the chat; the server checks, so their app never knows the word.

import { $, clear, el, str } from "./dom.js";
import { send, sendLine } from "./api.js";
import { getState } from "./store.js";

const SIZE = 1000;               // stroke coordinates are 0-1000 on both sides (the server checks)
const COLORS = ["#2b1d12", "#e2412a", "#4f9a2b", "#e9a21d", "#7a5cff", "#2a8fd6", "#8a5a2b", "#ffffff"];
const WIDTHS = [0, 3, 7, 14];    // brush size 1-3, in canvas pixels at 1000 wide
const FLUSH_MS = 70;             // how often the drawer's points go out as one packet
const SHOW_WORD_MS = 6000;       // the word stays up this long after a round ends
const MAX_POINTS = 60;           // per packet (the server allows 64)
let drawer = "";
let mine = false;
let color = 0;
let width = 2;
let pending = [];                // points not sent yet
let lastPoint = null;
let flushTimer = null;
let tickTimer = null;
let endsAt = 0;

const canvas = () => $("draw-canvas");

function line(points, colorIndex, size) {
  const ctx = canvas().getContext("2d");
  const scale = canvas().width / SIZE;
  ctx.strokeStyle = COLORS[colorIndex] || COLORS[0];
  ctx.lineWidth = WIDTHS[size] || WIDTHS[2];
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  points.forEach(([x, y], i) => (i ? ctx.lineTo(x * scale, y * scale) : ctx.moveTo(x * scale, y * scale)));
  if (points.length === 1) ctx.lineTo(points[0][0] * scale + 0.1, points[0][1] * scale);
  ctx.stroke();
}

function wipe() {
  const ctx = canvas().getContext("2d");
  ctx.fillStyle = "#fffaf2";
  ctx.fillRect(0, 0, canvas().width, canvas().height);
}

function paint(strokes) {
  wipe();
  for (const s of strokes) if (Array.isArray(s.points)) line(s.points, s.color, s.size);
}

// ---------------------------------------------------------------- the drawer's brush

function pointFrom(event) {
  const box = canvas().getBoundingClientRect();
  const x = Math.round(((event.clientX - box.left) / box.width) * SIZE);
  const y = Math.round(((event.clientY - box.top) / box.height) * SIZE);
  return [Math.min(SIZE, Math.max(0, x)), Math.min(SIZE, Math.max(0, y))];
}

function flush() {
  flushTimer = null;
  if (!pending.length) return;
  const points = pending.slice(0, MAX_POINTS);
  pending = pending.slice(MAX_POINTS);
  send({ type: "stroke", points, color, size: width });
  if (pending.length) flushTimer = setTimeout(flush, FLUSH_MS);
}

function addPoint(point) {
  if (lastPoint) line([lastPoint, point], color, width);
  else line([point], color, width);
  pending.push(point);
  lastPoint = point;
  if (!flushTimer) flushTimer = setTimeout(flush, FLUSH_MS);
}

function onDown(event) {
  if (!mine) return;
  event.preventDefault();
  canvas().setPointerCapture(event.pointerId);
  lastPoint = null;
  if (pending.length) flush();
  addPoint(pointFrom(event));
}

function onMove(event) {
  if (!mine || !lastPoint || !(event.buttons & 1)) return;
  addPoint(pointFrom(event));
}

function onUp() {
  if (!mine) return;
  clearTimeout(flushTimer);
  flush();
  // the next line starts fresh (its first packet repeats nothing from this one)
  lastPoint = null;
}

// ---------------------------------------------------------------- the round

function tools() {
  const box = clear($("draw-tools"));
  if (!mine) {
    box.append(el("p", { class: "draw-hint", text: "Guess the word in the chat! ✏️" }));
    return;
  }
  box.append(
    el("div", { class: "draw-colors", role: "radiogroup", "aria-label": "Colour" }, COLORS.map((c, i) =>
      el("button", { class: `draw-color${i === color ? " on" : ""}`, type: "button", role: "radio", "aria-checked": String(i === color),
        "aria-label": ["Brown", "Red", "Green", "Gold", "Purple", "Blue", "Wood", "White (eraser)"][i], "data-color": String(i),
        onclick: () => { color = i; tools(); } }))),
    el("label", { class: "draw-size" }, el("span", { text: "Size" }),
      el("input", { type: "range", min: "1", max: "3", value: String(width), oninput: (e) => { width = Number(e.target.value); } })),
    el("button", { class: "btn btn-ghost", type: "button", text: "🧽 Clear", onclick: () => { wipe(); send({ type: "stroke", clear: true }); } }),
    el("button", { class: "btn btn-ghost gs-danger", type: "button", text: "Give up", onclick: () => sendLine("/draw stop") }));
}

function countdown() {
  clearInterval(tickTimer);
  const update = () => {
    const left = Math.max(0, Math.round((endsAt - Date.now()) / 1000));
    $("draw-timer").textContent = `⏱️ ${left}s`;
    if (!left) clearInterval(tickTimer);
  };
  update();
  tickTimer = setInterval(update, 1000);
}

/** The server's {"type": "draw_round"}. */
export function onRound(msg, live) {
  const board = $("draw-board");
  if (msg.state === "ended") {
    clearInterval(tickTimer);
    mine = false;
    $("draw-title").textContent = msg.word ? `🎨 The word was ${str(msg.word).toUpperCase()}` : "🎨 Round over";
    tools();
    clear($("draw-tools"));
    setTimeout(() => { if (!drawer || $("draw-title").textContent.startsWith("🎨 The word")) board.hidden = true; }, live ? SHOW_WORD_MS : 0);
    drawer = "";
    return;
  }
  drawer = str(msg.drawer);
  mine = drawer === getState().nick;
  board.hidden = false;
  $("draw-title").textContent = mine ? "🎨 You're drawing" : `🎨 ${drawer} is drawing (${msg.letters} letters)`;
  endsAt = Date.now() + (Number.isInteger(msg.seconds) ? msg.seconds : 0) * 1000;
  countdown();
  paint(Array.isArray(msg.strokes) ? msg.strokes : []);
  tools();
  canvas().classList.toggle("drawing", mine);
}

/** Someone else's brush stroke. */
export function onStroke(msg) {
  if ($("draw-board").hidden) return;
  if (msg.clear === true) return wipe();
  if (Array.isArray(msg.points)) line(msg.points, msg.color, msg.size);
  return undefined;
}

/** Our own word, from the private "🎨 Your word: CAT." line: shown on the board for the drawer. */
export function noteWord(text) {
  const match = /^🎨 Your word: (.+?)\. Draw it!/u.exec(text);
  if (match) $("draw-title").textContent = `🎨 Draw: ${match[1]}`;
}

export function initDrawing() {
  const c = canvas();
  c.addEventListener("pointerdown", onDown);
  c.addEventListener("pointermove", onMove);
  c.addEventListener("pointerup", onUp);
  c.addEventListener("pointercancel", onUp);
  wipe();
}
