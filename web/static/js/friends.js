// 👥 Friends in the sidebar: who's online and what they're doing (from the server's {"type": "friends"} packet,
// pushed whenever it changes), quick buttons for each friend, an "add a friend" box, and the requests you sent.
// Requests to you are tickets on the rail (rail.js). Every button sends an existing /command.

import { $, clear, el, initial, nameClass } from "./dom.js";
import { send } from "./api.js";
import { getState, setState, subscribe } from "./store.js";
import * as F from "./friendlogic.js";

let hooks = { onProfile: () => {}, onChallenge: () => {}, onMessage: () => {}, onError: () => {} };
let openInvite = "";   // the friend whose "invite to which group?" list is open

export function say(text) {
  $("friends-status").textContent = "";   // empty first, so the same words are read again
  setTimeout(() => { $("friends-status").textContent = text; }, 60);
}

async function sendLine(text, group) {
  const error = await send({ type: "line", text, ...(group ? { group } : {}) });
  if (error) hooks.onError(error);
  return !error;
}

/** {"type": "friends"}: the list, the requests and your admin groups. */
export function onFriends(msg) {
  setState({ friends: F.readFriends(msg) });
}

export const resetFriends = () => setState({ friends: null });

async function invite(friend, group) {
  openInvite = "";
  if (await sendLine(`/invite ${friend.name}`, group.key)) say(`Invite to ${group.name} sent to ${friend.name}`);
  draw(getState(), true);
  focusKey(`invite:${friend.name}`);   // the group buttons are gone: back to the friend's 📨 button
}

const slug = (index) => `fr-groups-${index}`;   // (an id from a name could hold spaces: an index can't)

function focusKey(key) {
  $("friend-list").querySelector(`[data-key="${CSS.escape(key)}"]`)?.focus();
}

function closeChoices(friend) {
  openInvite = "";
  draw(getState(), true);
  focusKey(`invite:${friend.name}`);
}

/** 📨 One group: one button. Several: the button opens a short list of them under the friend. */
function inviteButton(friend, groups, index) {
  if (!groups.length) return null;
  const one = groups.length === 1;
  const open = openInvite === friend.name;
  return el("button", { class: "mini-btn", type: "button", title: one ? `Invite to ${groups[0].name}` : "Invite to a group",
    "aria-label": one ? `Invite ${friend.name} to ${groups[0].name}` : `Invite ${friend.name} to a group`,
    "aria-expanded": one ? null : String(open), "aria-controls": one ? null : slug(index),
    "data-key": `invite:${friend.name}`,
    onclick: () => {
      if (one) return invite(friend, groups[0]);
      openInvite = open ? "" : friend.name;
      return draw(getState(), true);
    } }, el("span", { "aria-hidden": "true", text: "📨" }));
}

function groupChoices(friend, groups, index) {
  if (openInvite !== friend.name || groups.length < 2) return null;
  return el("div", { id: slug(index), class: "fr-groups", role: "group", "aria-label": `Invite ${friend.name} to`,
    onkeydown: (event) => { if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); closeChoices(friend); } } },
    groups.map((g) => el("button", { class: "btn btn-ghost fr-group", type: "button", dir: "auto", text: g.name,
      "data-key": `invite-to:${friend.name}:${g.key}`, onclick: () => invite(friend, g) })));
}

function friendRow(friend, groups, index) {
  const where = F.doing(friend);
  return el("li", { class: `person fr-person${friend.online ? "" : " fr-offline"}` },
    el("span", { class: `avatar ${nameClass(friend.name)}`, "aria-hidden": "true", text: initial(friend.name) }),
    el("span", { class: "person-main" },
      el("button", { class: "person-name person-name-btn", type: "button", "data-key": `fprofile:${friend.name}`,
        "aria-label": `${friend.name}, ${friend.online ? "online" : "offline"}: profile`, onclick: () => hooks.onProfile(friend.name) },
      el("span", { class: `fr-dot${friend.online ? " on" : ""}`, "aria-hidden": "true" }), friend.name),
      el("span", { class: "person-room", text: where })),
    el("span", { class: "person-actions" },
      el("button", { class: "mini-btn", type: "button", "aria-label": `Private message to ${friend.name}`, title: "Private message",
        "data-key": `fmessage:${friend.name}`, onclick: () => hooks.onMessage(friend.name) },
      el("span", { "aria-hidden": "true", text: "💌" })),
      friend.online ? el("button", { class: "mini-btn", type: "button", "aria-label": `Challenge ${friend.name}`, title: "Challenge",
        "data-key": `fchallenge:${friend.name}`, onclick: () => hooks.onChallenge(friend.name) },
      el("span", { "aria-hidden": "true", text: "⚔️" })) : null,
      inviteButton(friend, groups, index)),
    groupChoices(friend, groups, index));
}

let drawn = "";
function draw(state, force = false) {
  const data = state.friends;
  const fingerprint = JSON.stringify([data, state.currentRoom, openInvite]);
  if (!force && fingerprint === drawn) return;   // only redraw on a real change: keeps keyboard focus
  drawn = fingerprint;
  const list = $("friend-list");
  const focusedKey = list.contains(document.activeElement) ? document.activeElement.dataset.key : null;
  const friends = data ? data.friends : [];
  const groups = data ? F.inviteChoices(data.groups, state.currentRoom) : [];
  const online = F.onlineCount(friends);
  $("friends-count").textContent = data ? `· ${online}/${friends.length}` : "";
  $("friends-sr").textContent = data ? `${online} of ${friends.length} online` : "";
  clear(list).append(...(!data ? [el("li", { class: "people-empty", text: "Loading your friends…" })]
    : friends.length ? friends.map((f, i) => friendRow(f, groups, i))
      : [el("li", { class: "people-empty", text: "No friends yet. Add someone below." })]));
  $("friends-sent").textContent = data && data.sent.length ? `⏳ Waiting for: ${data.sent.join(", ")}` : "";
  // the focused button may be gone (a friend went offline: no ⚔️): then their name, then the list's heading
  const name = focusedKey ? focusedKey.slice(focusedKey.indexOf(":") + 1).split(":")[0] : "";
  const again = focusedKey && (list.querySelector(`[data-key="${CSS.escape(focusedKey)}"]`)
    || list.querySelector(`[data-key="fprofile:${CSS.escape(name)}"]`));
  if (again) again.focus();
  else if (focusedKey) $("friends-title").focus();
}

/** options: onProfile(name), onChallenge(name), onMessage(name), onError(text) */
export function initFriends(options) {
  hooks = { ...hooks, ...options };
  $("friend-add").addEventListener("submit", async (event) => {
    event.preventDefault();
    const field = $("friend-name");
    const name = field.value.trim();
    if (!name) {
      say("Type a friend's name first");
      return field.focus();
    }
    if (await sendLine(`/friend add ${name}`)) {
      field.value = "";
      say(`Friend request sent to ${name}`);
    }
    return undefined;
  });
  subscribe((state) => draw(state));
}

/** The rail's friend request tickets answer with these (and the list updates when the server says so). */
export async function answerRequest(name, word) {
  const data = getState().friends;
  if (data) setState({ friends: { ...data, requests: data.requests.filter((n) => n !== name) } });
  $("friends-title").focus();   // the ticket (and its buttons) is gone: focus lands on the friends list
  const sent = await sendLine(`/friend ${word} ${name}`);
  if (sent) say(word === "accept" ? `You and ${name} are friends now` : `Declined ${name}'s friend request`);
  else if (data) setState({ friends: getState().friends ? { ...getState().friends, requests: [...getState().friends.requests, name] } : data });
  return sent;
}
