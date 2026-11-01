// 👥 The Groups screen's rules, with no page in them (web/tests/test_group_logic.py runs them in Node).
//
// Every button sends an existing /command: the server's own checks decide what's allowed. Group commands
// (/kick, /donate...) work only for a group: a button says which one in the line's "group" field, so the server
// runs it for that group and you stay in the chat you're in (no /join first).

const FOR_THE_GROUP = new Set(["leave", "donate", "upgrade", "emoji", "persona", "topic", "kick", "mute", "ban",
  "unban", "unmute", "promote", "demote", "disband", "approve", "reject", "invite"]);

/** The packets one button sends. group = {key, name}; ctx = {target, value, private}. */
export function packetsFor(action, group, ctx = {}) {
  const { target = "", value = "" } = ctx;
  const one = {
    join: `/join ${group.name}`,
    open: `/join ${group.name}`,
    create: `/create ${group.name}${ctx.private ? " private" : ""}`,
    approve: `/approve ${target}`,
    reject: `/reject ${target}`,
    invite: `/invite ${target}`,
    leave: "/leave",
    donate: `/donate ${value}`,
    upgrade: `/upgrade ${value}`,
    emoji: `/groupemoji ${value}`,
    persona: value ? `/personality ${value}` : "/personality",
    topic: value ? `/pin ${value}` : "/pin clear",
    kick: `/kick ${target}`,
    mute: `/mute ${target} ${value}`,
    unmute: `/unmute ${target}`,
    ban: `/ban ${target}`,
    unban: `/unban ${target}`,
    promote: `/promote ${target}`,
    demote: `/demote ${target}`,
    disband: "/disband",
  }[action];
  if (!one) return [];
  const packet = { type: "line", text: one.trim() };
  return [FOR_THE_GROUP.has(action) ? { ...packet, group: group.key } : packet];
}

export const isMember = (role) => role === "owner" || role === "admin" || role === "member";
export const isAdmin = (role) => role === "owner" || role === "admin";

/** Your groups first, then the others (each in the server's order), keeping only those that match the search. */
export function split(cards, query) {
  const wanted = String(query || "").trim().toLowerCase();
  const matches = (card) => !wanted || [card.name, card.topic].some((text) => String(text || "").toLowerCase().includes(wanted));
  const shown = (Array.isArray(cards) ? cards : []).filter(matches);
  return { mine: shown.filter((c) => isMember(c.your_role)), others: shown.filter((c) => !isMember(c.your_role)) };
}

/** One row of the bank's history, in words (the amount and the time are shown next to it). */
export function historyLine(row) {
  const who = String(row.who || "someone");
  switch (row.kind) {
    case "donate": return `🤝 ${who} donated`;
    case "upgrade": return `⬆️ ${who} bought ${row.note}`;
    case "war_won": return `⚔️ Won the war against #${row.note}`;
    case "war_lost": return `⚔️ Lost the war against #${row.note}`;
    case "hashbrown": return `🥔 Hashbrown answered ${who}`;
    case "refund": return `↩️ Refund for ${who}'s question`;
    default: return "🏦 Bank";
  }
}

export function upgradeStatus(upgrade) {
  if (upgrade.state === "owned") return "✅ Owned";
  if (upgrade.state === "can_buy") return "🟢 The bank can buy it now";
  return `🔒 ${upgrade.missing} 🪙 more needed`;
}

export const balanceAfter = (upgrade, balance) => balance - upgrade.price;

/** An SVG path of the balance over time inside a width x height box, or null with fewer than 3 points. */
export function chartPath(points, width, height) {
  const good = (Array.isArray(points) ? points : []).filter((p) => Number.isFinite(p?.time) && Number.isFinite(p?.balance));
  if (good.length < 3) return null;
  const times = good.map((p) => p.time);
  const values = good.map((p) => p.balance);
  const [t0, t1] = [Math.min(...times), Math.max(...times)];
  const [min, max] = [Math.min(...values), Math.max(...values)];
  const x = (t) => (t1 === t0 ? 0 : ((t - t0) / (t1 - t0)) * width);
  const y = (v) => (max === min ? height / 2 : height - ((v - min) / (max - min)) * height);
  const round = (n) => Math.round(n * 10) / 10;
  const line = good.map((p, i) => `${i ? "L" : "M"}${round(x(p.time))},${round(y(p.balance))}`).join(" ");
  return { line, area: `${line} L${round(x(t1))},${height} L0,${height} Z`, min, max,
    first: values[0], last: values[values.length - 1] };
}

/** "09:05" today, "28/10 09:05" on another day (times are seconds, like the server's). */
export function timeLabel(seconds, now = Date.now() / 1000) {
  const when = new Date(seconds * 1000);
  const today = new Date(now * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  const clock = `${pad(when.getHours())}:${pad(when.getMinutes())}`;
  return when.toDateString() === today.toDateString() ? clock : `${pad(when.getDate())}/${pad(when.getMonth() + 1)} ${clock}`;
}

/** ⌨️ An admin's tools for one member are one toolbar: one Tab stop, and the arrow keys move inside it.
 * Returns the tool to focus after `key` (the tools wrap around), or null when the key isn't the toolbar's. */
export function toolbarIndex(key, index, count) {
  if (key === "ArrowRight") return (index + 1) % count;
  if (key === "ArrowLeft") return (index - 1 + count) % count;
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  return null;   // (Up and Down stay with the minutes list)
}
