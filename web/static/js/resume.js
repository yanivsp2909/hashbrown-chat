// 🔁 Reconnect and catch up. At login the server gives a secret "resume_token"; every packet it keeps has a
// "seq" number. If the connection drops (or the website restarts), we open a new session and log in with
// {"action": "resume", username, token, seq: the last one we got}: the server sends exactly what we missed.
// Packets we already have (seq not newer) are dropped, so nothing shows twice. Not after being kicked or /quit.

let token = "";
let username = "";
let lastSeq = 0;
let kicked = false;

export function noteLogin(name) {
  username = name;
  kicked = false;
  lastSeq = 0;   // a password login starts the numbers again (the server may have restarted)
}

/** Every packet goes through here first. Returns false for one we already have. */
export function seePacket(msg, live) {
  if (msg.kicked === true) kicked = true;
  if (msg.type === "auth_result") {
    if (msg.ok && typeof msg.resume_token === "string") token = msg.resume_token;
    if (msg.resume_failed) {
      token = "";
      lastSeq = 0;
    }
  }
  if (!Number.isInteger(msg.seq)) return true;
  if (live && msg.seq <= lastSeq) return false;
  lastSeq = Math.max(lastSeq, msg.seq);
  return true;
}

export const canResume = () => Boolean(token && username && !kicked);

export function resumePacket(features) {
  return { type: "auth", action: "resume", username, token, seq: lastSeq, features };
}

/** Logged out or quit on purpose: nothing to come back to. */
export function forget() {
  token = "";
  lastSeq = 0;
  kicked = false;
}
