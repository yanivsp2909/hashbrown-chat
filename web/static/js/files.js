// 📁 Sending files (picker or drag-and-drop) and turning received ones into download links.

import { $, str } from "./dom.js";
import { send } from "./api.js";

export const MAX_FILE = 2 * 1024 * 1024;
const MAX_B64 = 2_800_000;
const BASE64 = /^[A-Za-z0-9+/]*={0,2}$/;
const WINDOWS_RESERVED = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i;
// Controls, bidi overrides (they can disguise "exe.txt" as "txt.exe") and zero-width characters
const UNSAFE_CHARS = /[\u0000-\u001f\u007f-\u009f​-‏‪-‮⁦-⁩﻿<>:"/\\|?*]/gu;

const objectUrls = [];

/** Never trust a filename from the network: a plain name, no folders, nothing invisible. */
export function sanitizeFilename(name) {
  let clean = str(name).normalize("NFC").split(/[\\/]/).pop().replace(UNSAFE_CHARS, "_");
  clean = clean.replace(/^[\s.]+|[\s.]+$/g, "");
  const dot = clean.lastIndexOf(".");
  let stem = dot > 0 ? clean.slice(0, dot) : clean;
  let ext = dot > 0 ? clean.slice(dot) : "";
  if (!stem || WINDOWS_RESERVED.test(stem)) stem = `file_${stem}`;
  ext = ext.slice(0, 12);
  return stem.slice(0, 100 - ext.length) + ext;
}

/** A received file message -> {from, filename, size, url}, or an error text. */
export function receive(msg) {
  const data = str(msg.data);
  if (data.length > MAX_B64 || data.length % 4 || !BASE64.test(data)) return { error: "sent a broken file." };
  let bytes;
  try {
    const binary = atob(data);
    bytes = Uint8Array.from(binary, (ch) => ch.charCodeAt(0));
  } catch {
    return { error: "sent a broken file." };
  }
  if (bytes.length > MAX_FILE) return { error: "sent a file that's too big." };
  // octet-stream: the browser downloads it instead of opening HTML or SVG on our page
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
  objectUrls.push(url);
  return { from: str(msg.from, "Someone"), filename: sanitizeFilename(msg.filename || "file"), size: bytes.length, url };
}

export function revokeFiles() {
  while (objectUrls.length) URL.revokeObjectURL(objectUrls.pop());
}

function readAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

// ----- the "send a file" panel above the composer

const panel = $("file-panel");
const toInput = $("file-to");
const fileInput = $("file-input");
const fileName = $("file-name");
const fileError = $("file-error");
const sendButton = $("file-send");
let chosen = null;

function showError(text) {
  fileError.textContent = text;
  fileError.hidden = !text;
}

function choose(file) {
  chosen = file || null;
  fileName.textContent = chosen ? chosen.name : "Choose file…";
  showError(chosen && chosen.size > MAX_FILE ? `That file is ${(chosen.size / 1048576).toFixed(1)} MB. The limit is 2 MB.` : "");
}

export function openFilePanel({ to = "", file = null } = {}) {
  panel.hidden = false;
  if (to) toInput.value = to;
  choose(file);
  (toInput.value ? sendButton : toInput).focus();
}

export function closeFilePanel() {
  panel.hidden = true;
  fileInput.value = "";
  choose(null);
}

export function initFiles({ onSent }) {
  fileInput.addEventListener("change", () => choose(fileInput.files[0]));
  $("file-cancel").addEventListener("click", closeFilePanel);
  $("attach").addEventListener("click", () => (panel.hidden ? openFilePanel() : closeFilePanel()));
  panel.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeFilePanel();
  });
  sendButton.addEventListener("click", async () => {
    const to = toInput.value.trim().replace(/^@/, "");
    if (!to) return showError("Who should get it? Type their name.");
    if (!chosen) return showError("Pick a file first.");
    if (chosen.size > MAX_FILE) return showError("Files must be 2 MB or less.");
    sendButton.disabled = true;
    sendButton.textContent = "Sending…";
    try {
      const error = await send({ type: "file", to, filename: chosen.name, data: await readAsBase64(chosen) });
      if (error) return showError(error);
      onSent(chosen.name, to);
      closeFilePanel();
    } catch {
      showError("Couldn't read that file.");
    } finally {
      sendButton.disabled = false;
      sendButton.textContent = "Send file";
    }
  });

  // Drag a file anywhere onto the chat
  const zone = $("drop-zone");
  const wrap = $("messages-wrap");
  let depth = 0;
  const hasFiles = (event) => [...(event.dataTransfer?.types || [])].includes("Files");
  wrap.addEventListener("dragenter", (event) => {
    if (!hasFiles(event)) return;
    depth += 1;
    zone.hidden = false;
  });
  wrap.addEventListener("dragleave", () => {
    depth = Math.max(0, depth - 1);
    if (!depth) zone.hidden = true;
  });
  wrap.addEventListener("dragover", (event) => {
    if (hasFiles(event)) event.preventDefault();
  });
  wrap.addEventListener("drop", (event) => {
    event.preventDefault();
    depth = 0;
    zone.hidden = true;
    const file = event.dataTransfer?.files?.[0];
    if (file) openFilePanel({ file });
  });
}
