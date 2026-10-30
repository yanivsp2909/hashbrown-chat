// 📦 Big files (2 to 15 MB) in 1 MB chunks. We send "file_start", then one chunk each time the server's
// "file_ack" asks for the next one (so only one chunk is ever on its way: flow control). Receiving: the
// pieces are collected and turned into a download link at "file_end". Small files use the old single packet.

import { send } from "./api.js";
import { addTransferCard, endTransferCard, setTransferProgress } from "./chat.js";
import { keepUrl, readAsBase64, sanitizeFilename } from "./files.js";
import { str } from "./dom.js";

export const MAX_BIG_FILE = 15 * 1024 * 1024;
const CHUNK = 1024 * 1024;
const outgoing = {};   // our id -> {file, chunks, done(error)}
const incoming = {};   // server id -> {from, filename, size, chunks, parts}

const mb = (bytes) => `${(bytes / 1048576).toFixed(1)} MB`;

/** Send a big file. Resolves with an error text, or null when it's all there. */
export function sendBig(file, to) {
  const id = `f${Date.now().toString(36)}`;
  const chunks = Math.ceil(file.size / CHUNK);
  addTransferCard(id, `📤 Sending ${file.name} (${mb(file.size)}) to ${to}…`, chunks);
  return new Promise((resolve) => {
    outgoing[id] = { file, chunks, done: resolve };
    send({ type: "file_start", id, to, filename: file.name, size: file.size, chunks }).then((error) => {
      if (error) finishOutgoing(id, error);
    });
  });
}

function finishOutgoing(id, error) {
  const transfer = outgoing[id];
  if (!transfer) return;
  delete outgoing[id];
  endTransferCard(id, { text: error ? `📦 ${transfer.file.name}: ${error}` : `📤 ${transfer.file.name} sent.` });
  transfer.done(error);
}

/** {"type": "file_ack", "id", "next"}: the server wants the next chunk (or has them all). */
export async function onAck(msg) {
  const id = str(msg.id);
  const transfer = outgoing[id];
  if (!transfer) return;
  const next = Number(msg.next);
  setTransferProgress(id, next, transfer.chunks);
  if (next >= transfer.chunks) return finishOutgoing(id, null);
  try {
    const data = await readAsBase64(transfer.file.slice(next * CHUNK, (next + 1) * CHUNK));
    const error = await send({ type: "file_chunk", id, index: next, data });
    if (error) finishOutgoing(id, error);
  } catch {
    send({ type: "file_cancel", id });
    finishOutgoing(id, "couldn't read the file.");
  }
}

export function onStart(msg) {
  const id = str(msg.id);
  const chunks = Number(msg.chunks) || 0;
  incoming[id] = { from: str(msg.from, "Someone"), filename: sanitizeFilename(msg.filename || "file"),
    size: Number(msg.size) || 0, chunks, parts: [] };
  addTransferCard(id, `📥 ${incoming[id].from} is sending you ${incoming[id].filename} (${mb(incoming[id].size)})…`, chunks);
}

export function onChunk(msg) {
  const transfer = incoming[str(msg.id)];
  if (!transfer || msg.index !== transfer.parts.length) return;
  transfer.parts.push(str(msg.data));
  setTransferProgress(str(msg.id), transfer.parts.length, transfer.chunks);
}

export function onEnd(msg) {
  const id = str(msg.id);
  const transfer = incoming[id];
  if (!transfer) return;
  delete incoming[id];
  try {
    const pieces = transfer.parts.map((part) => Uint8Array.from(atob(part), (ch) => ch.charCodeAt(0)));
    // octet-stream: the browser downloads it instead of opening HTML or SVG on our page
    const url = URL.createObjectURL(new Blob(pieces, { type: "application/octet-stream" }));
    keepUrl(url);
    endTransferCard(id, { file: { from: transfer.from, filename: transfer.filename, size: transfer.size, url } });
  } catch {
    endTransferCard(id, { text: `📦 ${transfer.filename} arrived broken.` });
  }
}

export function onCancel(msg) {
  const id = str(msg.id);
  if (outgoing[id]) return finishOutgoing(id, "cancelled.");
  if (incoming[id]) {
    endTransferCard(id, { text: `📦 ${incoming[id].filename}: cancelled.` });
    delete incoming[id];
  }
  return undefined;
}
