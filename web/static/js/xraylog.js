// 🔬 Packet X-ray's memory: the newest XRAY_KEEP entries since the page loaded, kept even while the panel is
// closed, so opening it shows what already happened. No DOM here (web/tests/test_xray_log.py runs it in Node).
//
// An entry is any object with `types`: the packet types it holds. A packet has one; a raw TCP chunk can hold
// several packets, or only the start of one.

export const XRAY_KEEP = 500;

/** Does this entry pass the type filter? ("" = every type) */
export const matches = (entry, filter) => !filter || entry.types.includes(filter);

/** What the X-ray may show of a packet: passwords and reconnect tokens become •••, everything else is exact.
 * (The bridge blanks the token in the TCP tab the same way.) */
export function hideSecrets(packet, wireText) {
  const hidden = ["password", "token", "resume_token", "old", "new"].filter((key) => key in packet);
  const secretType = packet.type === "auth" || packet.type === "change_password";
  if (!hidden.length || (!secretType && !("resume_token" in packet))) return wireText;
  const keys = secretType ? hidden : ["resume_token"];
  return JSON.stringify({ ...packet, ...Object.fromEntries(keys.map((key) => [key, "•••"])) });
}

/** A packet's type from one line of JSON, even a line cut off in the middle (then the first "type" in it). */
function lineType(line) {
  try {
    const packet = JSON.parse(line);
    if (packet && typeof packet.type === "string") return packet.type;
  } catch {
    // not a whole packet: TCP cut it, fall through
  }
  return line.match(/"type"\s*:\s*"([^"\\]{1,40})"/u)?.[1] ?? null;
}

/** The packet types in a raw TCP chunk, in order, each once. */
export function chunkTypes(text) {
  const found = String(text).split("\n").map(lineType).filter(Boolean);
  return [...new Set(found)];
}

export function makeLog(keep = XRAY_KEEP) {
  let entries = [];
  return {
    /** Keep this entry. Returns the oldest one if it had to make room, else null. */
    add(entry) {
      const dropped = entries.length >= keep ? entries[0] : null;
      entries = [...entries.slice(Math.max(0, entries.length - keep + 1)), entry];
      return dropped;
    },
    empty() {
      entries = [];
    },
    list(filter = "") {
      return entries.filter((entry) => matches(entry, filter));
    },
    /** Every packet type seen so far, A to Z (for the filter menu). */
    types() {
      return [...new Set(entries.flatMap((entry) => entry.types))].sort();
    },
  };
}
