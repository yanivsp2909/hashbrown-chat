// 🧪 Small banners at the top of the chat. The network lab one: the host made the network worse on purpose
// (lag / loss in the server window), so everyone sees why messages are slow. {"type": "lab", lag_ms, loss_percent}.

import { $ } from "./dom.js";

const whole = (n) => (Number.isInteger(n) && n > 0 ? n : 0);

/** "🧪 Network lab: 300 ms lag, 20% loss", or "" when the lab is off. */
export function labText(msg) {
  const parts = [whole(msg.lag_ms) && `${whole(msg.lag_ms)} ms lag`, whole(msg.loss_percent) && `${whole(msg.loss_percent)}% loss`];
  const on = parts.filter(Boolean);
  return on.length ? `🧪 Network lab: ${on.join(", ")}` : "";
}

/** Show (or hide) the lab banner. After a reload the replay runs through every change: the last one wins. */
export function showLab(msg) {
  const banner = $("lab-banner");
  banner.textContent = labText(msg);
  banner.hidden = !banner.textContent;
}
