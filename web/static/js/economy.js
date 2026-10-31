// 📊 The economy dashboard: every token in the game, the public fund, the richest players, today's hottest
// stock and the inflation over the week. {"type": "get_economy"} -> {"type": "economy"}.

import { $, clear, el, str } from "./dom.js";
import { send } from "./api.js";
import { chartPath } from "./grouplogic.js";

const SVG = "http://www.w3.org/2000/svg";

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  node.append(...children);
  return node;
}

// A value too long for its tile (a group stock like #CHESSCLUB) ends in "…"; the full text shows on hover (title)
// and is still the text screen readers get.
const tile = (label, value, note = "") => el("div", { class: "ec-tile" },
  el("p", { class: "ec-label", text: label }), el("p", { class: "ec-value", text: value, title: value, dir: "auto" }),
  note ? el("p", { class: "ec-note", text: note }) : null);

/** {"type": "economy"} */
export function onEconomy(msg) {
  if (!$("economy").open) return;
  const body = clear($("ec-body"));
  const inflation = Number.isFinite(msg.inflation_week) ? `${msg.inflation_week > 0 ? "+" : ""}${msg.inflation_week}%` : "not yet";
  const hot = msg.hottest ? str(msg.hottest.symbol).toUpperCase() : "—";   // (the change goes on the note line, so it's never cut)
  const hotNote = msg.hottest ? `${msg.hottest.change > 0 ? "▲" : "▼"} ${Math.abs(msg.hottest.change)}% · now ${msg.hottest.price} 🪙` : "";
  body.append(
    el("div", { class: "ec-tiles" },
      tile("🪙 Every token in the game", String(msg.total), "wallets, savings, group banks, the fund"),
      tile("🧾 Public fund", String(msg.fund), `today: +${msg.fund_today?.in || 0} in, −${msg.fund_today?.out || 0} paid out`),
      tile("📈 Hottest stock today", hot, hotNote),
      tile("🎈 Inflation this week", inflation, "how much the total grew")));
  const points = (Array.isArray(msg.supply) ? msg.supply : []).map(([day, total], i) => ({ time: i, balance: total, day }));
  const path = chartPath(points, 520, 90);
  if (path) {
    body.append(el("figure", { class: "ec-chart" },
      svg("svg", { viewBox: "0 -4 520 98", preserveAspectRatio: "none", role: "img", class: "gs-chart-svg",
        "aria-label": `Every token in the game, one number a day: from ${path.first} to ${path.last}` },
      svg("path", { d: path.area, class: "gs-chart-area" }), svg("path", { d: path.line, class: "gs-chart-line" })),
      el("figcaption", { class: "gs-chart-caption", "aria-hidden": "true" },
        el("span", { text: str(points[0].day) }), el("span", { text: str(points[points.length - 1].day) }))));
  }
  body.append(el("h3", { class: "gs-h3", text: "🏆 Richest players" }),
    el("ol", { class: "ec-richest" }, (msg.richest || []).map((p) => el("li", {},
      el("span", { dir: "auto", text: str(p.name) }), el("span", { class: "gs-num", text: `${p.tokens} 🪙` })))));
}

export function initEconomy() {
  const dialog = $("economy");
  $("economy-open").addEventListener("click", () => {
    clear($("ec-body")).append(el("p", { class: "loading-text", text: "Counting every token…" }));
    dialog.showModal();
    send({ type: "get_economy" });
  });
  $("economy-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => $("economy-open").focus());
}
