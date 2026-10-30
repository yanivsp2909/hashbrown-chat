"""
📦 Big files (up to MAX_BIG_FILE) sent in chunks.

    sender -> server:  {"type": "file_start", "id", "to", "filename", "size", "chunks"}
    server -> sender:  {"type": "file_ack", "id", "next": 0}        "send me chunk 0"
    sender -> server:  {"type": "file_chunk", "id", "index": 0, "data": base64}
    server -> sender:  {"type": "file_ack", "id", "next": 1}        ... and so on
    server -> getter:  file_start, then every file_chunk, then {"type": "file_end", "id"}
    either side:       {"type": "file_cancel", "id"}

Only one chunk is on its way at a time (the next one waits for its ack): that's flow control, so a slow
receiver is never flooded. Small files still use the old single {"type": "file"} packet, so old clients work.
"""
import base64
import binascii
import os
import time

from chatserver import config, rooms, state, textutil


def _cancel(transfer, why_sender, why_getter=None):
    """Stop a transfer and tell both sides (if they're still here)."""
    state.transfers.pop(transfer["key"], None)
    for login, why in ((transfer["from"], why_sender), (transfer["to"], why_getter)):
        client = state.online.get(login)
        if client is not None:
            their_id = transfer["sender_id"] if login == transfer["from"] else transfer["key"]
            client.send({"type": "file_cancel", "id": their_id})
            if why:
                client.say(why, "error")


def start(client, msg):
    transfer_id = str(msg.get("id", ""))[:40]
    size, chunks = msg.get("size"), msg.get("chunks")
    if not transfer_id or not isinstance(size, int) or not isinstance(chunks, int) or isinstance(size, bool):
        client.say("📦 That big file request is broken.", "error")
        return
    if not 0 < size <= config.MAX_BIG_FILE or chunks != -(-size // config.CHUNK_SIZE):   # -(-a // b) rounds up
        client.say(f"📦 Big files must be 1 byte to {config.MAX_BIG_FILE // 1048576} MB.", "error")
        return
    if any(t["from"] == client.key for t in state.transfers.values()):
        client.say("📦 You can send one big file at a time. Wait for this one to finish.", "error")
        return
    if time.time() - getattr(client, "last_big_file", 0) < config.BIG_FILE_EVERY:
        client.say("📦 Wait a moment before starting another big file.", "error")
        return
    client.last_big_file = time.time()
    target = rooms.find_online(client, textutil.clean_text(msg.get("to", "")))
    if target is None:
        return
    if target == client.key:
        client.say("🙃 You can't send a file to yourself.", "error")
        return
    if any(t["to"] == target for t in state.transfers.values()):
        client.say(f"📦 {rooms.nick(target)} is already getting a big file. Try again when it's done.", "error")
        return
    if "chunks" not in state.online[target].features:
        client.say(f"📦 {rooms.nick(target)}'s app can't receive big files. Send them up to 2 MB.", "error")
        return
    filename = os.path.basename(textutil.clean_text(msg.get("filename", "")).replace("\\", "/"))[:100] or "file"
    key = f"{client.key}-{transfer_id}"   # what the receiver calls it (two senders could pick the same id)
    state.transfers[key] = {"key": key, "sender_id": transfer_id, "from": client.key, "to": target,
                            "filename": filename, "size": size, "chunks": chunks, "next": 0,
                            "in_flight": False, "active": time.time()}
    state.online[target].send({"type": "file_start", "id": key, "from": rooms.nick(client.key),
                               "filename": filename, "size": size, "chunks": chunks})
    client.send({"type": "file_ack", "id": transfer_id, "next": 0})


def chunk(client, msg):
    transfer = state.transfers.get(f"{client.key}-{str(msg.get('id', ''))[:40]}")
    if transfer is None:
        return  # cancelled already: late chunks are just dropped
    data = msg.get("data")
    # The next chunk only after the ack of this one (flow control): a sender who doesn't wait is cut off,
    # so nobody can fill the server's memory with someone else's chunks.
    if transfer["in_flight"] or msg.get("index") != transfer["next"] or not is_base64(data):
        _cancel(transfer, "📦 The file transfer broke and was cancelled.", "📦 The file transfer was cancelled.")
        return
    getter = state.online.get(transfer["to"])
    if getter is None:
        _cancel(transfer, "📦 They left, so the file transfer was cancelled.")
        return
    transfer["in_flight"], transfer["active"] = True, time.time()
    getter.send({"type": "file_chunk", "id": transfer["key"], "index": transfer["next"], "data": data},
                after=lambda: delivered(transfer))


def is_base64(data):
    if not isinstance(data, str) or len(data) > config.CHUNK_B64 or len(data) % 4:
        return False
    try:
        base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return False
    return True


def delivered(transfer):
    """Runs in the receiver's writer thread once a chunk has really been sent: now ask for the next one."""
    with state.lock:
        if state.transfers.get(transfer["key"]) is not transfer:
            return  # cancelled meanwhile
        transfer["in_flight"] = False
        transfer["next"] += 1
        sender, getter = state.online.get(transfer["from"]), state.online.get(transfer["to"])
        if sender is not None:
            sender.send({"type": "file_ack", "id": transfer["sender_id"], "next": transfer["next"]})
        if transfer["next"] == transfer["chunks"]:
            state.transfers.pop(transfer["key"], None)
            if getter is not None:
                getter.send({"type": "file_end", "id": transfer["key"]})
            size = f"{transfer['size'] // 1024 + 1} KB"
            rooms.tell(transfer["from"], f"📤 Sent {transfer['filename']} ({size}) to {rooms.shown(transfer['to'])}.")


def expire_stalled(now=None):
    """Transfers with no chunk for BIG_FILE_STALL seconds are cancelled (called once a minute)."""
    now = time.time() if now is None else now
    for transfer in list(state.transfers.values()):
        if now - transfer["active"] > config.BIG_FILE_STALL:
            _cancel(transfer, "📦 The file transfer stalled and was cancelled.", "📦 The file transfer was cancelled.")


def cancel(client, msg):
    """Either side gave up."""
    wanted = str(msg.get("id", ""))[:40]
    for transfer in list(state.transfers.values()):
        if (client.key == transfer["from"] and wanted == transfer["sender_id"]) or \
                (client.key == transfer["to"] and wanted == transfer["key"]):
            _cancel(transfer, None, None)
            other = transfer["to"] if client.key == transfer["from"] else transfer["from"]
            rooms.tell(other, "📦 The file transfer was cancelled.", "error")


def drop_all_of(key):
    """Someone left: cancel every transfer they were part of."""
    for transfer in list(state.transfers.values()):
        if key in (transfer["from"], transfer["to"]):
            _cancel(transfer, None, None)
