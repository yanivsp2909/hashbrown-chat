// 💬 The chat switcher's rules, with no page in them (so web/tests/test_room_logic.py can run them in Node).
//
// Every chat (the Lobby and each group) is its own conversation: its own message list, preview line and
// unread count. The server tags the chat of your other rooms with "room" (the room's key), and every
// room's history comes with "key" when you switch.

const PREVIEW = 60;   // characters of the last message shown under a room's name

export const previewOf = (msg) => `${String(msg?.name ?? "")}: ${String(msg?.text ?? "")}`.slice(0, PREVIEW);

/** Which room a packet belongs to: its own tag, or the room you're in (private notices, errors...). */
export function roomOf(msg, currentRoom) {
  if (msg.type === "history") return typeof msg.key === "string" ? msg.key : currentRoom;
  return typeof msg.room === "string" && msg.room ? msg.room : currentRoom;
}

/** A room's history after the first one (the first comes at login, after the welcome lines):
 *  you switched rooms, so the screen starts that room's own list instead of adding to the old one. */
export function startsNewList(msg, currentRoom) {
  return msg.type === "history" && Boolean(currentRoom);
}

/** The previews table with this packet's room updated (a chat line, or the last line of a history). */
export function withPreview(previews, msg, currentRoom) {
  if (msg.type === "chat") return { ...previews, [roomOf(msg, currentRoom)]: previewOf(msg) };
  if (msg.type === "history" && typeof msg.key === "string" && Array.isArray(msg.messages) && msg.messages.length) {
    return { ...previews, [msg.key]: previewOf(msg.messages[msg.messages.length - 1]) };
  }
  return previews;
}
