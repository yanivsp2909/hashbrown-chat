// 🏢 Hashbrown Ventures' rules for the website, as plain functions (no page, no network), so Node can test them:
// how numbers read, the command line each button sends, chart and pie shapes, and which help lines to hide.
// The server decides everything; these only draw what it sent and type the same commands a player would.

/** $950, $12.3K, $4.5M, $1.2B (like the server's ventures_text.money). */
export function money(dollars) {
  const value = Math.abs(Number(dollars) || 0);
  const sign = Number(dollars) < 0 ? "-" : "";
  for (const [size, letter] of [[1e9, "B"], [1e6, "M"], [1e3, "K"]]) {
    const text = (value / size).toFixed(1);   // (rounded first, so $999,960 is $1M and not $1000K)
    if (Number(text) >= 1) return `${sign}$${text.replace(/\.0$/, "")}${letter}`;
  }
  return `${sign}$${Math.round(value)}`;
}

export const whole = (n) => Math.round(Number(n) || 0).toLocaleString("en-US");
export const plural = (n, word, many = `${word}s`) => `${whole(n)} ${Math.round(n) === 1 ? word : many}`;

/** Basis points (10,000 = 100%) as "12.5%". */
export const percent = (bp) => `${(Math.round((Number(bp) || 0)) / 100).toFixed(2).replace(/\.?0+$/, "")}%`;

/** "1250" or "12.5%" typed in a box -> a percent number, or null. */
export function readPercent(text) {
  const value = Number(String(text).trim().replace(/%$/, ""));
  return Number.isFinite(value) && value >= 0 && value <= 100 ? Math.round(value * 100) / 100 : null;
}

// ---------------------------------------------------------------- the commands buttons send

export const NAME_RULE = "3-16 English or Hebrew letters, digits or _";
const RESERVED = new Set(["hashbrown", "server", "admin", "lobby", "file", "ventures"]);

/** The same name rule as the server (rooms.valid_name), so the wizard can say so before sending. */
export function nameProblem(name) {
  const text = String(name).trim();
  if (text.length < 3 || text.length > 16) return `Names are ${NAME_RULE}.`;
  if (!/^[A-Za-z0-9_]+$/.test(text) && !/^[א-ת0-9_]+$/.test(text)) return `Names are ${NAME_RULE}.`;
  if (RESERVED.has(text.toLowerCase())) return "That name is taken by the chat itself.";
  return "";
}

export const foundLine = (name, sector) => `/company found ${String(name).trim()} ${sector}`;

/** One action button -> its command (hire and layoff take a kind, layoff a count, pivot a sector). */
export function actionLine(action, choice = "", count = 0) {
  if (action === "layoff") return `/company layoff ${choice} ${Math.max(1, Math.floor(count) || 1)}`;
  return `/company ${action}${choice ? ` ${choice}` : ""}`;
}

export const inviteLine = (name, role, pct) =>
  `/company invite ${String(name).trim()} ${role}${pct ? ` ${pct}` : ""}`;
export const angelLine = (accept, name) => `/company angel ${accept ? "accept" : "decline"} ${name}`;
export const investLine = (company, tokens) => `/invest ${company} ${Math.floor(tokens)}`;
export const offerLine = (answer, id) => `/offer ${answer} ${id}`;   // (the id: an old card can't answer a new sheet)

/** A counter-offer typed as "15M", "2.5b", "900k" or "15000000" -> "/offer counter 15M", or null. */
export function counterLine(text) {
  const clean = String(text).trim().toLowerCase().replace(/[$,\s]/g, "");
  if (!/^\d+(\.\d+)?[kmb]?$/.test(clean)) return null;
  return `/offer counter ${clean.toUpperCase()}`;
}

/** A pitch answer: one line, so it goes to the investor with /pitch (works from any room). */
export const pitchLine = (text) => `/pitch ${String(text).replace(/\s+/g, " ").trim()}`;

// ---------------------------------------------------------------- the help on the website

const SCREEN_COMMANDS = ["/company", "/pitch", "/offer", "/invest", "/ventures"];

/** The website uses the 🏢 Ventures screen: these commands stay out of the autocomplete. */
export const withoutScreenCommands = (commands) =>
  commands.filter((c) => !SCREEN_COMMANDS.includes(String(c.name).toLowerCase()));

/** The /help text without the "🏢 Ventures" section (one line points to the screen instead). */
export function hideVenturesHelp(text) {
  const lines = String(text).split("\n");
  const kept = [];
  let skipping = false;
  for (const line of lines) {
    if (line.trim() === "🏢 Ventures") {
      skipping = true;
      kept.push("🏢 Ventures: open 🏢 Ventures in the menu to start a company, pitch investors and invest.");
      continue;
    }
    if (skipping && line.startsWith("  /")) continue;
    skipping = false;
    if (SCREEN_COMMANDS.some((c) => line.trimStart().startsWith(`${c} `) || line.trim() === c)) continue;
    kept.push(line);
  }
  return kept.join("\n");
}

// ---------------------------------------------------------------- charts and the pie

/** Points of a small line chart in a w x h box: {path, area, first, last, min, max} (null with < 2 points). */
export function chart(values, w = 120, h = 36, pad = 3) {
  const nums = values.map(Number).filter(Number.isFinite);
  if (nums.length < 2) return null;
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const span = max - min || 1;
  const x = (i) => pad + (i * (w - 2 * pad)) / (nums.length - 1);
  const y = (v) => h - pad - ((v - min) / span) * (h - 2 * pad);
  const points = nums.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
  const path = `M${points.join("L")}`;
  const area = `${path}L${x(nums.length - 1).toFixed(1)},${h}L${x(0).toFixed(1)},${h}Z`;
  return { path, area, first: nums[0], last: nums[nums.length - 1], min, max };
}

/** Pie slices for the cap table on a 100x100 board: [{name, kind, bp, path}] (one owner: a full circle). */
export function pie(rows, r = 46, cx = 50, cy = 50) {
  const total = rows.reduce((sum, row) => sum + Math.max(0, Number(row.bp) || 0), 0) || 1;
  let angle = -Math.PI / 2;
  return rows.filter((row) => Number(row.bp) > 0).map((row) => {
    const part = Number(row.bp) / total;
    if (part >= 0.9999) {
      return { ...row, path: `M${cx},${cy - r}A${r},${r} 0 1 1 ${cx - 0.01},${cy - r}Z` };
    }
    const start = angle;
    angle += part * 2 * Math.PI;
    const [x1, y1] = [cx + r * Math.cos(start), cy + r * Math.sin(start)];
    const [x2, y2] = [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
    const large = part > 0.5 ? 1 : 0;
    return { ...row, path: `M${cx},${cy}L${x1.toFixed(2)},${y1.toFixed(2)}A${r},${r} 0 ${large} 1 ${x2.toFixed(2)},${y2.toFixed(2)}Z` };
  });
}

// ---------------------------------------------------------------- time

/** "in 3 h 12 min", "in 5 min", "any minute now" until a Unix time (seconds). */
export function countdown(at, nowMs = Date.now()) {
  const minutes = Math.round((Number(at) * 1000 - nowMs) / 60000);
  if (!Number.isFinite(minutes) || minutes <= 1) return "any minute now";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `in ${h} h${m ? ` ${m} min` : ""}` : `in ${m} min`;
}

/** The runway in words: "∞ (profitable)", "3 days", "today". */
export function runwayText(days) {
  if (days === null || days === undefined) return "∞ profitable";
  return Number(days) <= 0 ? "out today" : plural(days, "day");
}

// ---------------------------------------------------------------- reading the packets safely

const asList = (value) => (Array.isArray(value) ? value.filter((x) => x && typeof x === "object") : []);

/** The "ventures" packet with every list a list (a broken one draws as empty, never crashes the screen). */
export function readHome(msg) {
  const m = msg && typeof msg === "object" ? msg : {};
  const inv = m.investments && typeof m.investments === "object" ? m.investments : {};
  return {
    season: m.season && typeof m.season === "object" ? m.season : { number: 1, day: 0, days: 28, next_tick: 0 },
    me: m.me && typeof m.me === "object" ? m.me : { tokens: 0, found_cost: 200, can_found: false, why: "" },
    mine: m.mine && typeof m.mine === "object" && typeof m.mine.id === "string" ? m.mine : null,
    board: asList(m.board), graveyard: asList(m.graveyard), news: asList(m.news),
    investments: { held: asList(inv.held), waiting: asList(inv.waiting) },
    invites: asList(m.invites), sectors: asList(m.sectors), roles: asList(m.roles),
  };
}

/** The "company" packet's company, or null when it isn't one. */
export function readCompany(msg) {
  const c = msg && typeof msg === "object" ? msg.company : null;
  if (!c || typeof c !== "object" || typeof c.id !== "string") return null;
  return { ...c, team: asList(c.team), cap: asList(c.cap), timeline: asList(c.timeline), rounds: asList(c.rounds),
    actions: asList(c.actions), reports: asList(c.reports), history: asList(c.history), milestones: asList(c.milestones),
    angels: asList(c.angels), invites_out: asList(c.invites_out) };
}

/** How hard a sector is, in words (from 1-3). */
export const difficulty = (n) => ["", "Easy start", "Medium", "Hard mode"][Number(n)] || "Medium";
