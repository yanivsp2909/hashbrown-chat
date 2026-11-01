// 📨 Group invite tickets, with no page in them (web/tests/test_group_invite_logic.py runs them in Node).
//
// The server's invite is a normal msg with an optional "group_invite" field: {group, name, from, expires}
// (expires in seconds, like the server's clocks). It ends with {"type": "invite_closed", "group": key}.

const isText = (value) => typeof value === "string" && value.length > 0 && value.length <= 40;

/** The invite in a msg's group_invite field, or null if it isn't a good one. */
export function readInvite(field) {
  if (!field || typeof field !== "object" || Array.isArray(field)) return null;
  const { group, name, from, expires } = field;
  if (!isText(group) || !isText(name) || !isText(from) || !Number.isFinite(expires)) return null;
  return { group, name, from, expires };
}

/** The list with this invite in it: one per group (a newer invite to the same group replaces the old one). */
export const withInvite = (list, invite) => [...list.filter((i) => i.group !== invite.group), invite];

export const withoutInvite = (list, group) => list.filter((i) => i.group !== group);

/** Only the invites that haven't ended by `now` (seconds). */
export const stillOpen = (list, now) => list.filter((i) => i.expires > now);

/** "24 h left", "45 min left" or "ended". */
export function timeLeft(expires, now) {
  const seconds = expires - now;
  if (seconds <= 0) return "ended";
  if (seconds >= 3600) return `${Math.ceil(seconds / 3600)} h left`;
  return `${Math.max(1, Math.ceil(seconds / 60))} min left`;
}

/** What a ticket's button sends: Accept is /join (an invite lets you in), Decline is /invites decline. */
export const answerLine = (invite, answer) => (answer === "accept" ? `/join ${invite.name}` : `/invites decline ${invite.name}`);
