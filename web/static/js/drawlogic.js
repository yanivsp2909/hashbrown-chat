// 🎨 The drawer's outbox: the canvas gives it points, and it sends them as {"type": "stroke"} packets, at most one
// every EVERY_MS (about 10 a second, inside the bridge's and the server's stroke budgets). Points pile up in
// between, so a fast drawer's line arrives whole, just in bigger pieces. Each line is its own packet (a packet is
// one connected line); a long line is cut in pieces that share their end point, so the pieces join up.
// No DOM here, so the rules can be tested in Node (web/tests/test_draw_logic.py).

export const EVERY_MS = 100;
export const MAX_POINTS = 60;    // per packet (the server allows 64)

/**
 * post(packet) sends one stroke packet; now() and later(fn, ms) are the clock (Date.now and setTimeout in the page).
 * Returns { start(point, color, size), add(point), end(), drop() }.
 */
export function makeBatcher(post, now = () => Date.now(), later = (fn, ms) => setTimeout(fn, ms)) {
  let lines = [];          // [{points, color, size, open, sent}] oldest first
  let timer = false;
  let lastSent = -Infinity;
  let generation = 0;      // drop() makes a waiting timer harmless

  // a line has something new while it holds more than the point the last piece ended on
  const hasNew = (line) => line.points.length > (line.sent ? 1 : 0);

  function tick(gen) {
    if (gen !== generation) return;
    timer = false;
    while (lines.length && !lines[0].open && !hasNew(lines[0])) lines = lines.slice(1);
    const line = lines[0];
    if (!line || !hasNew(line)) return;
    const points = line.points.slice(0, MAX_POINTS);
    post({ type: "stroke", points, color: line.color, size: line.size });
    lastSent = now();
    line.points = line.points.slice(points.length - 1);   // the next piece starts where this one ended
    line.sent = true;
    schedule();
  }

  function schedule() {
    if (timer || !lines.some(hasNew)) return;
    timer = true;
    const gen = generation;
    later(() => tick(gen), Math.max(0, lastSent + EVERY_MS - now()));
  }

  return {
    start(point, color, size) {
      lines = [...lines.map((l) => ({ ...l, open: false })), { points: [point], color, size, open: true, sent: false }];
      schedule();
    },
    add(point) {
      const line = lines[lines.length - 1];
      if (!line || !line.open) return;
      line.points = [...line.points, point];
      schedule();
    },
    end() {
      lines = lines.map((l) => ({ ...l, open: false }));
      schedule();
    },
    drop() {
      lines = [];
      generation += 1;
      timer = false;
    },
  };
}
