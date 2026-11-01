// 🤝 The friends list's rules, with no page in them (web/tests/test_friend_logic.py runs them in Node).
//
// The server sends {"type": "friends", friends: [{name, online, status, room, playing}], requests: [names],
// sent: [names], groups: [{key, name}]} (groups: the ones you're an admin of, for "invite to my group").

const isName = (value) => typeof value === "string" && value.length > 0 && value.length <= 40;
const names = (list) => (Array.isArray(list) ? list.filter(isName) : []);
const STATUS = { away: "🌙 away", busy: "⛔ busy" };

/** A friends packet -> {friends, requests, sent, groups}, keeping only well-formed parts. */
export function readFriends(packet) {
  const rows = Array.isArray(packet?.friends) ? packet.friends : [];
  const friends = rows.filter((f) => f && isName(f.name)).map((f) => ({
    name: f.name, online: f.online === true, status: typeof f.status === "string" ? f.status : "online",
    room: typeof f.room === "string" ? f.room : "", playing: f.playing === true }));
  const groups = (Array.isArray(packet?.groups) ? packet.groups : []).filter((g) => g && isName(g.key) && isName(g.name))
    .map((g) => ({ key: g.key, name: g.name }));
  return { friends, requests: names(packet?.requests), sent: names(packet?.sent), groups };
}

/** The line under a friend's name: what they're doing, or "offline". */
export function doing(friend) {
  if (!friend.online) return "offline";
  const first = friend.playing ? "🎮 in a game" : STATUS[friend.status] || "";
  return [first, friend.room].filter(Boolean).join(" · ");
}

export const onlineCount = (friends) => friends.filter((f) => f.online).length;

/** The groups "invite to my group" offers: the group you're in first (if you're its admin), then the rest. */
export function inviteChoices(groups, currentRoom) {
  return [...groups.filter((g) => g.key === currentRoom), ...groups.filter((g) => g.key !== currentRoom)];
}
