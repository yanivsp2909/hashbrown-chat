// 🔎 Every piece of server text the website relies on lives in this file.
//
// The chat server mostly sends plain text, so a few features only work by recognising
// exact wording. These are the server strings (from server.py) this file depends on:
//
//   welcome        auth_result: "✅ Welcome back, {nick}!"  /  "✅ Account created! Welcome, {nick}!"
//   renamed        msg:         "✏️ {old} is now called {badge} {nick}"   (badge is optional)
//   invite         msg event:   "⚔️ {who} challenges you to {game}{ for N 🪙}!  /accept {nick}  or  /decline {nick}"
//   won            msg money:   "🏆 YOU WON!..."      (also sent on resign / disconnect, with no board)
//   lost           msg error:   "💀 You lost...."
//   draw           msg game:    "🤝 Draw!..."
//   wordleOver     msg:         "🏳️ The word was {WORD}."  /  "💀 Out of tries! The word was {WORD}."
//   helpLine       msg help:    "  {usage padded to 32} {description}"  (one line per command in /help)
//   HASHBROWN      chat:        name "Hashbrown" with badge "🥔"  (chat_message("Hashbrown", "🥔", ...))
//
// web/tests/test_bridge.py runs the real server and checks every pattern below against what
// it actually sends. If you reword one of these messages in server.py, that test tells you
// which pattern to update here.

const P = (source) => new RegExp(source, "u");

export const PATTERNS = Object.freeze({
  welcome: P(String.raw`^✅ (?:Welcome back|Account created! Welcome), (\S+)!$`),
  renamed: P(String.raw`^✏️ (\S+) is now called (?:\S+ )?(\S+)$`),
  invite: P(String.raw`^⚔️ .+ challenges you to .+!\s+/accept (\S+)\s+or\s+/decline \S+$`),
  won: P(String.raw`^🏆 YOU WON!`),
  lost: P(String.raw`^💀 You lost\.`),
  draw: P(String.raw`^🤝 Draw!`),
  wordleOver: P(String.raw`^(?:🏳️ |💀 Out of tries! )The word was ([A-Z]+)\.$`),
  helpLine: P(String.raw`^  (/\S+(?: \S+)*?)\s{2,}(\S.*)$|^  (/\S+(?: \S+)*) (\S.*)$`),
});

export const HASHBROWN = Object.freeze({ name: "Hashbrown", badge: "🥔" });

/** The nick inside a successful login reply, or null. */
export function welcomeNick(text) {
  const match = PATTERNS.welcome.exec(text);
  return match ? match[1] : null;
}

/** [oldNick, newNick] from a rename notice, or null. */
export function renamed(text) {
  const match = PATTERNS.renamed.exec(text);
  return match ? [match[1], match[2]] : null;
}

/** The challenger's nick if this is an incoming challenge, or null. */
export function inviteFrom(text) {
  const match = PATTERNS.invite.exec(text);
  return match ? match[1] : null;
}

/** "won" | "lost" | "draw" | null, for the end-of-match messages. */
export function matchResult(kind, text) {
  if (kind === "money" && PATTERNS.won.test(text)) return "won";
  if (kind === "error" && PATTERNS.lost.test(text)) return "lost";
  if (kind === "game" && PATTERNS.draw.test(text)) return "draw";
  return null;
}

export function isWordleOver(text) {
  return PATTERNS.wordleOver.test(text);
}

/** The /help reply as [{name, usage, description}], one per command line. */
export function parseHelp(text) {
  const commands = [];
  for (const line of String(text).split("\n")) {
    const match = PATTERNS.helpLine.exec(line);
    if (!match) continue;
    const usage = (match[1] ?? match[3]).trim();
    commands.push({ name: usage.split(" ")[0], usage, description: (match[2] ?? match[4]).trim() });
  }
  return commands;
}

export function isHashbrown(chat) {
  return chat.name === HASHBROWN.name && chat.badge === HASHBROWN.badge;
}
