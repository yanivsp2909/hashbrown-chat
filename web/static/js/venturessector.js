// 🏭 The sector panel on a company's HQ: each sector's own numbers and its own actions (from the server's
// "sector_panel" and the actions marked "sector"). 🤖 compute, models and the Spud-Bench; 🛡️ product lines,
// security and incidents; 📱 stock, batches and keynotes; 💻 price and retention; 🎮 the game in development.

import { el, str } from "./dom.js";
import * as V from "./ventureslogic.js";
import { actionRow } from "./ventureshq.js";

const ICONS = { compute: "🖥️", train: "🧠", release: "🚀", safety: "🦺", launch: "🚀", improve: "🔧", audit: "🔍",
  bounty: "🐛", manufacture: "🏭", supply: "🤝", keynote: "🎤", newmodel: "✨", priceup: "💲", pricedown: "🏷️",
  retention: "🫶", experiment: "🧪", develop: "🛠️", playtest: "🕹️", liveops: "📅", dlc: "🎁" };

const fact = (label, value) => el("div", { class: "vs-fact" }, el("dt", { text: label }), el("dd", { text: value }));

/** A 0-100 bar with its number (a meter for screen readers). */
function meter(label, value) {
  const v = Math.max(0, Math.min(100, Math.round(Number(value) || 0)));
  return el("div", { class: "vs-meter-row" },
    el("span", { class: "vs-meter-label", text: label }),
    el("span", { class: "vs-meter", role: "meter", "aria-label": label, "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(v) },
      el("span", { class: "vs-meter-fill", style: undefined, "data-w": String(v) })),
    el("span", { class: "num", text: `${v}` }));
}

/** CSP forbids inline styles in the HTML, but setting a property from script is fine. */
function sizeMeters(root) {
  for (const fill of root.querySelectorAll(".vs-meter-fill")) fill.style.width = `${fill.dataset.w}%`;
  return root;
}

export function sectorPanel(co) {
  const s = co.sector_panel || {};
  const rows = co.actions.filter((a) => a.sector);
  const body = { ai: aiPanel, cyber: cyberPanel, hardware: hardwarePanel, saas: saasPanel, game: gamePanel }[s.sector] || (() => []);
  return sizeMeters(el("section", { class: "vs-panel vs-sector-panel", "aria-labelledby": "vs-sector" },
    el("h3", { id: "vs-sector", class: "gs-h3", text: `${str(co.icon)} ${str(co.sector_name)}` }),
    ...body(s, co),
    co.status === "alive" && rows.length ? el("ul", { class: "vs-actions" }, ...rows.map((a) => actionRow(co, a, ICONS[a.name] || "•"))) : null));
}

function aiPanel(s) {
  const models = Array.isArray(s.models) ? s.models : [];
  const bench = Array.isArray(s.bench) ? s.bench : [];
  return [
    el("dl", { class: "vs-facts" },
      fact("Compute", `${V.whole(s.compute)} units`), fact("Needed a day", `${V.whole(s.compute_need)}`),
      fact("Price", `${V.money(s.compute_price)} a unit`), fact("Next training", `${V.whole(s.train_cost)} units`)),
    meter("Safety", s.safety),
    s.training ? el("p", { class: "vs-note", text: `🧠 Model ${str(s.training.gen)} is training: ${V.plural(s.training.left, "day")} left.` }) : null,
    models.length ? el("ul", { class: "vs-list" }, ...models.slice(-4).reverse().map((m) => el("li", { class: "vs-model" },
      el("span", { class: "vs-row-name", text: str(m.name) }),
      el("span", { class: "vs-row-sub", text: `Spud-Bench ${str(m.score)} · safety ${str(m.safety)} · ${m.released ? "released" : "ready to release"}` }))))
      : el("p", { class: "gs-muted", text: "No models yet: buy compute, then train one." }),
    bench.length ? el("details", { class: "vs-details" }, el("summary", { text: "🧠 The Spud-Bench leaderboard" }),
      el("ol", { class: "vs-bench" }, ...bench.map((r) => el("li", { class: r.npc ? "" : "vs-mine-row" },
        el("span", { class: "vs-row-name", text: `${str(r.name)} (${str(r.lab)})` }), el("span", { class: "num", text: str(r.score) }))))) : null,
  ];
}

function cyberPanel(s) {
  const names = s.names || {};
  const incidents = Array.isArray(s.incidents) ? s.incidents : [];
  return [
    meter("Your security", s.security),
    el("ul", { class: "vs-list vs-lines" }, ...Object.entries(s.lines || {}).map(([key, level]) => el("li", { class: "vs-line" },
      el("span", { class: "vs-row-name", text: str(names[key] || key) }),
      Number(level) > 0 ? meter("Level", level) : el("span", { class: "vs-row-sub", text: "not launched" })))),
    incidents.length ? el("ul", { class: "vs-list vs-incidents" }, ...incidents.slice().reverse().map((i) =>
      el("li", { class: "vs-row-sub", text: `Day ${str(i.tick)}: ${str(i.text)}` }))) : el("p", { class: "gs-muted", text: "No incidents. Keep it that way." }),
  ];
}

function hardwarePanel(s) {
  const batches = Array.isArray(s.batches) ? s.batches : [];
  return [
    el("dl", { class: "vs-facts" },
      fact("Device", `${str(s.device)} · gen ${str(s.gen)}`), fact("Price", V.money(s.price)),
      fact("Unit cost", V.money(s.unit_cost_now ?? s.unit_cost)), fact("In stock", V.whole(s.stock)),
      fact("Sold yesterday", V.whole(s.sold)), fact("Missed sales", V.whole(s.unmet))),
    batches.length ? el("p", { class: "vs-note", text: "🏭 On the way: " + batches.map((b) => `${V.whole(b.units)} (day ${str(b.arrive)})`).join(", ") }) : null,
    el("p", { class: "gs-muted", text: s.keynote_ready ? "🎤 A keynote is ready when you are." : "🎤 The next keynote needs a few more days." }),
  ];
}

function saasPanel(s) {
  return [el("dl", { class: "vs-facts" },
    fact("Price", `${Math.round(Number(s.price) * 100)}% of the usual`),
    fact("Retention push", s.retention_on ? "on" : "off"))];
}

function gamePanel(s) {
  const project = s.project || {};
  const games = Array.isArray(s.games) ? s.games : [];
  return [
    el("p", { class: "vs-row-name", text: `🛠️ Game ${str(project.number)} in development` }),
    meter("Done", project.progress), meter("Quality", project.quality),
    games.length ? el("ul", { class: "vs-list" }, ...games.slice().reverse().map((g) => el("li", { class: "vs-model" },
      el("span", { class: "vs-row-name", text: `${g.hit ? "🎉 " : ""}${str(g.name)}` }),
      el("span", { class: "vs-row-sub", text: `${V.whole(g.players)} players at launch · reviews ${str(g.review)}/100` }))))
      : el("p", { class: "gs-muted", text: "No game launched yet." }),
  ];
}
