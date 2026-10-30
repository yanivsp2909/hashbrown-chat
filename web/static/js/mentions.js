// @ autocomplete's rules, with no page in them (web/tests/test_room_logic.py runs them in Node).

/** The @word that ends at the caret ("hey @no|" -> {start: 4, end: 7, word: "no"}), or null. */
export function mentionAt(text, caret) {
  const match = /(^|\s)@([^\s@]{0,16})$/u.exec(text.slice(0, caret));
  return match ? { start: caret - match[2].length - 1, end: caret, word: match[2] } : null;
}

/** Who you can mention here: Hashbrown first, then the people online in this room (or everyone you've
 *  seen while the online list isn't in yet), never yourself, in the order given, no repeats. */
export function mentionNames({ online, room, nick, knownNames }) {
  const here = Array.isArray(online) ? online.filter((p) => p.room === room).map((p) => p.name) : knownNames || [];
  return ["hashbrown", ...new Set(here.filter((name) => name && name !== nick && name.toLowerCase() !== "hashbrown"))];
}

/** The names that start with what you typed after the @ (any case). */
export function matchingNames(names, word) {
  const start = word.toLowerCase();
  return names.filter((name) => name.toLowerCase().startsWith(start));
}
