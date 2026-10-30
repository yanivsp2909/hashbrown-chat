// 📈 The market screen: every stock with a live price chart, your shares, and Buy / Sell. The data comes from
// {"type": "market_info"} (asked for when the screen opens) and the once-a-minute {"type": "market"} tick;
// the buttons send the normal /buy FRY 5 and /sell FRY 5 commands (the server checks the money and the fee).

import { $, clear, el, str } from "./dom.js";
import { send, sendLine } from "./api.js";
import { chartPath } from "./grouplogic.js";

const SVG = "http://www.w3.org/2000/svg";
const W = 260;
const H = 70;
const REFRESH_AFTER_TRADE_MS = 600;
let info = null;

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  node.append(...children);
  return node;
}

function chart(sym, stock) {
  const points = (Array.isArray(stock.history) ? stock.history : []).map(([time, balance]) => ({ time, balance }));
  const path = chartPath(points, W, H);
  if (!path) return el("p", { class: "mk-chart-empty", text: "The chart fills in as the minutes go by." });
  const up = (Number(stock.change) || 0) >= 0;   // the colour says the same as "today" next to it
  return svg("svg", { viewBox: `0 -4 ${W} ${H + 8}`, class: `mk-chart ${up ? "mk-up" : "mk-down"}`, role: "img",
    preserveAspectRatio: "none", "aria-label": `${sym} over the last ${points.length} minutes: from ${path.first} to ${path.last} tokens` },
  svg("path", { d: path.area, class: "mk-area" }), svg("path", { d: path.line, class: "mk-line" }));
}

async function trade(verb, sym) {
  const field = $(`mk-n-${sym}`);
  const shares = Number.parseInt(field.value, 10);
  if (!(shares > 0)) {
    field.setAttribute("aria-invalid", "true");
    field.focus();
    return;
  }
  field.removeAttribute("aria-invalid");
  const error = await sendLine(`/${verb} ${sym} ${shares}`);
  $("mk-status").textContent = error ? `⚠️ ${error}` : `Sent: ${verb} ${shares} ${sym}. The answer is in the chat.`;
  setTimeout(() => send({ type: "get_market" }), REFRESH_AFTER_TRADE_MS);
}

function card(sym, stock) {
  const owned = info.portfolio[sym] || 0;
  const change = Number(stock.change) || 0;
  const typed = $(`mk-n-${sym}`)?.value || "";
  return el("li", { class: "mk-card" },
    el("div", { class: "mk-head" },
      el("span", { class: "mk-icon", "aria-hidden": "true", text: str(stock.icon) }),
      el("div", { class: "mk-names" }, el("h3", { class: "mk-sym", text: sym.toUpperCase() }), el("p", { class: "mk-name", text: str(stock.name) })),
      el("div", { class: "mk-price" }, el("span", { class: "mk-num", text: `${stock.price} 🪙` }),
        el("span", { class: `mk-change ${change > 0 ? "mk-up" : change < 0 ? "mk-down" : ""}`, text: `${change > 0 ? "▲" : change < 0 ? "▼" : "·"} ${change.toFixed(1)}% today` }))),
    chart(sym, stock),
    el("p", { class: "mk-owned", text: owned ? `You have ${owned} (worth ${owned * stock.price} 🪙)` : "You have none" }),
    el("div", { class: "mk-trade" },
      el("label", { class: "visually-hidden", for: `mk-n-${sym}`, text: `How many ${sym} shares` }),
      el("input", { id: `mk-n-${sym}`, class: "input mk-n", type: "number", min: "1", step: "1", inputmode: "numeric", placeholder: "Shares", value: typed }),
      el("button", { class: "btn btn-primary", type: "button", text: "Buy", "aria-label": `Buy ${sym}`, onclick: () => trade("buy", sym) }),
      el("button", { class: "btn btn-ghost", type: "button", text: "Sell", "aria-label": `Sell ${sym}`, disabled: !owned, onclick: () => trade("sell", sym) })));
}

function draw() {
  if (!info) return;
  const focused = document.activeElement?.id;
  clear($("mk-list")).append(...Object.entries(info.stocks).map(([sym, stock]) => card(sym, stock)));
  $("mk-wallet").textContent = `🪙 You have ${info.tokens} tokens. Every buy and sell costs a ${info.fee_percent}% fee (at least 1 🪙) that goes to the public fund.`;
  if (focused) document.getElementById(focused)?.focus();
}

/** {"type": "market_info"}: the whole screen. */
export function onInfo(msg) {
  if (!msg.stocks || typeof msg.stocks !== "object") return;
  info = { ...msg, portfolio: msg.portfolio || {} };
  if ($("market").open) draw();
}

/** {"type": "market"}: the minute's prices (one packet to everyone). */
export function onTick(msg) {
  if (!info || !msg.prices) return;
  const stocks = {};
  for (const [sym, stock] of Object.entries(info.stocks)) {
    const price = Number.isInteger(msg.prices[sym]) ? msg.prices[sym] : stock.price;
    stocks[sym] = { ...stock, price, change: msg.changes?.[sym] ?? stock.change,
      history: [...(stock.history || []), [msg.time, price]].slice(-180) };
  }
  info = { ...info, stocks };
  if ($("market").open) draw();
}

export function initMarket() {
  const dialog = $("market");
  $("market-open").addEventListener("click", () => {
    dialog.showModal();
    send({ type: "get_market" });
  });
  $("market-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => $("market-open").focus());
}
