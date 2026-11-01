// 🌉 Talking to web_server.py: one session per tab, messages in through Server-Sent Events,
// messages out through POST /api/send.

const SID_KEY = "hashbrown.sid";   // sessionStorage: per tab, survives a reload
const OFFLINE = "Can't reach the website. Is web_server.py still running?";

let sid = sessionStorage.getItem(SID_KEY);
let source = null;
let handlers = {};
let leaving = false;   // a reload or a closing tab also "breaks" the stream: that's not a lost session
let live = false;      // false while a (re)opened stream is still replaying old events
let liveWaiters = [];

window.addEventListener("pagehide", () => {
  leaving = true;
  source?.close();
});
window.addEventListener("beforeunload", () => {
  leaving = true;
});
window.addEventListener("pageshow", (event) => {
  leaving = false;
  if (event.persisted && sid) listen();  // restored from the back/forward cache: the stream was closed
});

/** Resolves once the stream has finished replaying and is live. */
export function whenLive() {
  return live ? Promise.resolve() : new Promise((resolve) => liveWaiters.push(resolve));
}

async function post(path, body) {
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Hashbrown": "1", ...(sid ? { "X-Session-Id": sid } : {}) },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    return { ok: response.ok, status: response.status, error: data.error || (response.ok ? null : "Something went wrong."), data };
  } catch {
    return { ok: false, status: 0, error: OFFLINE, data: {} };
  }
}

/**
 * handlers: onMessage(msg, isLive), onLive({logged_in}), onGap(), onClosed(reason), onReplaced(), onLost()
 * isLive is false while a reloaded tab is replaying what it already received before.
 */
export function setHandlers(next) {
  handlers = next;
}

export const hasSession = () => Boolean(sid);

export async function newSession() {
  sid = null;
  const result = await post("/api/session", { xray: true });   // 🔬 the Packet X-ray records the raw TCP from the start
  if (!result.ok) return result;
  sid = result.data.sid;
  sessionStorage.setItem(SID_KEY, sid);
  return result;
}

export function listen() {
  source?.close();
  live = false;
  source = new EventSource(`/api/events?sid=${encodeURIComponent(sid)}&last=0`);
  source.onmessage = (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }
    if (msg && typeof msg === "object" && !Array.isArray(msg)) {
      for (const watch of packetWatchers) watch("in", msg, event.data, live);
      handlers.onMessage(msg, live);
    }
  };
  source.addEventListener("bridge", (event) => {
    let info = {};
    try {
      info = JSON.parse(event.data);
    } catch {
      return;
    }
    if (info.event === "live") {
      if (!live) {
        live = true;
        handlers.onLive({ logged_in: info.logged_in === true });
        liveWaiters.forEach((resolve) => resolve());
        liveWaiters = [];
      }
    } else if (info.event === "gap") {
      handlers.onGap();
    } else if (info.event === "closed") {
      stop();
      handlers.onClosed(String(info.reason || "Disconnected."));
    } else if (info.event === "replaced") {
      source.close();
      handlers.onReplaced();
    }
  });
  source.onerror = () => {
    // A dropped connection retries on its own. CLOSED means the bridge refused us (the session is gone).
    if (source.readyState === EventSource.CLOSED && !leaving) {
      stop();
      handlers.onLost();
    }
  };
}

/** 🔁 Drop the old session (it's gone) before starting a new one. */
export const forgetSession = () => stop();

function stop() {
  source?.close();
  source = null;
  live = false;
  sid = null;
  sessionStorage.removeItem(SID_KEY);
}

/** Send one message to the chat server. Returns null on success, or an error text. */
let recentLines = [];   // the last lines you sent: [{text, at}]

/** Did you send a line matching `pattern` in the last `ms` milliseconds? */
export function sentRecently(pattern, ms) {
  return recentLines.some((line) => Date.now() - line.at < ms && pattern.test(line.text));
}

/** 🔬 watch(direction, packet, wireText, live) sees every packet this tab gets ("in") or sends ("out").
 * live is false for packets a reloaded tab gets again from the bridge's replay. */
let packetWatchers = [];
export function watchPackets(watch) {
  packetWatchers = [...packetWatchers, watch];
}

export async function send(msg) {
  for (const watch of packetWatchers) watch("out", msg, JSON.stringify(msg));
  if (msg.type === "line") recentLines = [...recentLines.slice(-7), { text: String(msg.text), at: Date.now() }];
  if (!sid) return "Not connected.";
  const result = await post("/api/send", msg);
  if (result.status === 404 || result.status === 410) {
    stop();
    handlers.onLost();
  }
  return result.ok ? null : result.error;
}

export const sendLine = (text) => send({ type: "line", text });

export async function logout() {
  if (sid) await post("/api/close", {});
  stop();
}
