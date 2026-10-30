"""
💬 Chat client

Run:   python client.py 192.168.1.20  -> connects to the server at that IP (ask the host for it)
       python client.py               -> looks for a server on this Wi-Fi (UDP broadcast), else asks for the IP
       python client.py IP --web      -> opens the host's website in your browser instead
       python client.py IP --packets  -> also shows every packet and every raw recv() chunk (Packet X-ray)
Files people send you are saved in a folder called received_files.
"""
import base64
import getpass
import json
import os
import select
import socket
import sys
import threading
import time
import unicodedata
import warnings
import webbrowser

PORT = 8820
WEB_PORT = 8080   # where the host's website runs (server.py starts it)
# What this client understands, told to the server at login. "offers": ask me before sending me a file
# (I answer with /accept or /decline). Older copies of this file don't send it and get files straight away.
FEATURES = ["offers"]


DISCOVERY_PORT = 8821   # UDP port where servers answer {"type": "discover"}
MAX_SERVERS = 9         # list at most this many answers


def parse_args(args):
    """python client.py [IP] [--web] [--packets]  ->  (the IP or None, the set of --flags)."""
    flags = {a for a in args if a.startswith("--")}
    others = [a for a in args if not a.startswith("-")]
    return (others[0] if others else None), flags


SERVER_IP, FLAGS = parse_args(sys.argv[1:])
MAX_LINE = 4 * 1024 * 1024
MAX_FILE_SIZE = 2 * 1024 * 1024
DOWNLOAD_DIR = "received_files"

if os.name == "nt":
    os.system("")  # turns on colors in the Windows console
try:
    # A console that can't show an emoji prints "?" instead of crashing the client
    sys.stdout.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass

RESET, DIM, BOLD = "\033[0m", "\033[2m", "\033[1m"
KIND_COLORS = {"system": "\033[93m", "error": "\033[91m", "private": "\033[95m", "money": "\033[92m",
               "event": "\033[96m", "game": "\033[96m", "help": "", "board": ""}
NAME_COLORS = ["\033[91m", "\033[92m", "\033[93m", "\033[94m", "\033[95m", "\033[96m"]
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}

ESC_WAIT = 0.05  # seconds to wait after Esc to see if it is the start of an arrow-key sequence
TIMED_OUT = {"type": "timed_out"}  # made here (never sent by the server) when waiting took too long

quitting = threading.Event()
# 🔁 Reconnect and catch up: the connection we use now, the secret token the server gave at login, and the
# last packet number we got. After a drop we log back in with them and get exactly what we missed.
link = {"sock": None, "server": "", "username": "", "token": "", "seq": 0, "kicked": False}
RECONNECT_WAITS = (1, 2, 4, 8, 15, 30)   # seconds between tries, then we give up


# ---------------------------------------------------------------- the line you type on
# In a real terminal we read your keys one by one, so when a message arrives while
# you're typing, it's printed ABOVE your line and your half-typed text is drawn again
# underneath. Nothing gets cut. PyCharm's Run window only hands over your text after
# Enter, so there this can't work unless you turn on "Emulate terminal in output console"
# (Run > Edit Configurations > Modify options).

PROMPT = "> "
print_lock = threading.Lock()


def display_width(text):
    """How many terminal columns text takes (emoji and some letters take 2)."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def terminal_columns():
    try:
        return max(20, os.get_terminal_size().columns)
    except OSError:
        return 80


class InputLine:
    def __init__(self):
        self.smart = sys.stdin.isatty() and sys.stdout.isatty()
        self.typing = False   # True while you're on the "> " line
        self.buffer = ""      # what you've typed so far
        self.rows = 1         # how many screen rows the "> ..." line takes right now
        self.history = []     # lines you sent, for the up/down arrows
        self.history_pos = 0

    # --- drawing (always called while holding print_lock)
    def _clear_line(self):
        if self.rows > 1:
            sys.stdout.write(f"\033[{self.rows - 1}A")
        sys.stdout.write("\r\033[J")

    def _draw_line(self):
        line = PROMPT + self.buffer
        sys.stdout.write(line)
        self.rows = max(1, -(-display_width(line) // terminal_columns()))  # rounded up
        sys.stdout.flush()

    def out(self, text):
        """Print a message without wrecking the line you're in the middle of typing."""
        with print_lock:
            if self.smart and self.typing:
                self._clear_line()
                sys.stdout.write(text + "\n")
                self._draw_line()
            else:
                print(text, flush=True)

    # --- reading
    def read(self):
        """Read one line from you."""
        if not self.smart:
            return input()
        with print_lock:
            self.buffer, self.typing, self.history_pos = "", True, len(self.history)
            self._draw_line()
        keys = self._windows_keys() if os.name == "nt" else self._unix_keys()
        try:
            for key in keys:
                if key == "enter":
                    break
                with print_lock:
                    self._handle(key)
        finally:
            keys.close()  # puts the terminal back to normal
            with print_lock:
                self.typing = False
                text = self.buffer.strip()
                self._clear_line()
                if text.startswith("/"):
                    sys.stdout.write(PROMPT + self.buffer + "\n")  # keep commands on screen
                # chat lines vanish here and come back from the server with the time on them
                sys.stdout.flush()
        if text:
            self.history.append(text)
        return self.buffer

    def _handle(self, key):
        if key == "backspace":
            self.buffer = self.buffer[:-1]
        elif key == "escape":
            self.buffer = ""
        elif key in ("up", "down") and self.history:
            step = -1 if key == "up" else 1
            self.history_pos = min(max(self.history_pos + step, 0), len(self.history))
            self.buffer = self.history[self.history_pos] if self.history_pos < len(self.history) else ""
        elif len(key) == 1 and key.isprintable():
            self.buffer += key
        else:
            return
        self._clear_line()
        self._draw_line()

    def _unix_keys(self):
        """Mac / Linux: switch the terminal to key-by-key mode, and always switch it back."""
        import termios
        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        raw = termios.tcgetattr(fd)
        raw[3] &= ~(termios.ICANON | termios.ECHO)  # no line buffering, we draw the keys ourselves
        termios.tcsetattr(fd, termios.TCSADRAIN, raw)
        try:
            yield from self._read_unix_keys(fd)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)

    def _read_unix_keys(self, fd):
        """Turns the bytes coming from file descriptor fd into keys (split out so tests can feed it a pipe)."""
        import codecs
        decoder = codecs.getincrementaldecoder("utf-8")(errors="ignore")
        extra = b""  # a byte we read too early, to handle on the next round
        while True:
            byte, extra = extra or self._next_byte(fd), b""
            ch = decoder.decode(byte)
            if not ch:
                continue  # middle of a Hebrew letter or emoji
            if ch in ("\r", "\n"):
                yield "enter"
            elif ch in ("\x7f", "\x08"):
                yield "backspace"
            elif ch == "\x04" and not self.buffer:
                raise EOFError
            elif ch == "\x1b":
                key, extra = self._escape_key(fd)
                yield key
            else:
                yield ch

    @staticmethod
    def _next_byte(fd):
        byte = os.read(fd, 1)
        if not byte:
            raise EOFError
        return byte

    def _escape_key(self, fd):
        """Called right after an Esc byte. Returns (key, extra byte we read but didn't use)."""
        if not select.select([fd], [], [], ESC_WAIT)[0]:
            return "escape", b""  # nothing followed, so it really was the Esc key
        first = self._next_byte(fd)
        if first == b"[":  # arrows etc: ESC [ numbers or ; ... one final letter
            code = self._next_byte(fd)
            while 0x20 <= code[0] <= 0x3F:
                code = self._next_byte(fd)
            return {b"A": "up", b"B": "down"}.get(code, "ignore"), b""
        if first == b"O":  # some terminals send ESC O A for the arrows
            return {b"A": "up", b"B": "down"}.get(self._next_byte(fd), "ignore"), b""
        return "escape", first  # Esc and then an ordinary key: don't lose that key

    @staticmethod
    def _windows_keys():
        import msvcrt  # reads single key presses from the Windows console
        while True:
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                yield "enter"
            elif ch == "\x03":
                raise KeyboardInterrupt
            elif ch in ("\x00", "\xe0"):  # arrows and F-keys come as two codes
                yield {"H": "up", "P": "down"}.get(msvcrt.getwch(), "ignore")
            elif ch == "\b":
                yield "backspace"
            elif ch == "\x1b":
                yield "escape"
            elif "\ud800" <= ch <= "\udbff":  # an emoji arrives in two halves
                pair = (ch + msvcrt.getwch()).encode("utf-16", "surrogatepass")
                yield pair.decode("utf-16", errors="ignore")  # a broken pair gives "" which is ignored
            else:
                yield ch


console = InputLine()


def paint(text, color):
    return f"{color}{text}{RESET}" if color else text


def show_packet(text):
    """--packets: print what goes over the network, dimmed, so you can watch the protocol."""
    console.out(paint(text, DIM))


def send(sock, obj):
    """Every message is one line of JSON, so the other side knows where it ends."""
    line = json.dumps(obj, ensure_ascii=False)
    if "--packets" in FLAGS:
        hidden = {k: "•••" for k in ("password", "token") if k in obj}
        shown = json.dumps({**obj, **hidden}, ensure_ascii=False) if hidden else line
        show_packet(f"⬆ {shown}")
    sock.sendall((line + "\n").encode())


pong_waiting = threading.Event()   # 🏓 set while a ping is waiting for its pong


def send_ping(sock):
    """🏓 Send the time now; the server sends it straight back, so the difference is the round trip."""
    pong_waiting.set()
    send(sock, {"type": "ping", "t": time.time()})

    def no_pong():   # an old server doesn't know ping packets: say so instead of staying silent
        if pong_waiting.is_set():
            pong_waiting.clear()
            console.out(paint("🏓 No pong after 3 seconds. Maybe the server is older and doesn't know /ping.", DIM))
    threading.Timer(3, no_pong).start()


def describe_chunk(chunk):
    """'312 bytes: 2 packets' — TCP doesn't keep messages apart, the newlines do."""
    ends = chunk.count(b"\n")
    packets = f"{ends} packet{'' if ends == 1 else 's'}"
    return f"{len(chunk)} bytes: {packets}" + ("" if chunk.endswith(b"\n") else " + the start of one more ✂️")


def read_messages(sock):
    """Yield each message from the server as a dict."""
    buffer = bytearray()
    while True:
        try:
            chunk = sock.recv(65536)
        except socket.timeout:
            yield TIMED_OUT
            return
        except OSError:
            return
        if not chunk:
            return
        if "--packets" in FLAGS:
            show_packet(f"── recv() {describe_chunk(chunk)}")
        start = len(buffer)
        buffer += chunk
        while True:
            end = buffer.find(b"\n", start)
            if end == -1:
                break
            line = bytes(buffer[:end])
            del buffer[:end + 1]
            start = 0
            if "--packets" in FLAGS:
                show_packet(f"⬇ {line.decode('utf-8', 'replace')}")
            try:
                msg = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, ValueError, RecursionError):
                continue
            if isinstance(msg, dict):
                yield msg
        if len(buffer) > MAX_LINE:
            return


# ---------------------------------------------------------------- showing messages

def printable(text):
    """Text from the network can hold hidden terminal commands (clear the screen, move the cursor...).
    Keep letters, emoji and new lines, drop every control character."""
    text = str(text).replace("\t", " ")
    return "".join(ch for ch in text if ch == "\n" or unicodedata.category(ch) != "Cc")


def format_chat(msg):
    name = printable(msg.get("name", "?"))
    who = paint(name, NAME_COLORS[sum(map(ord, name)) % len(NAME_COLORS)])
    if msg.get("badge"):
        who = f"{printable(msg['badge'])} {who}"
    stamp = paint(f"[{printable(msg.get('time', ''))}]", DIM)
    text = printable(msg.get("text", ""))
    if msg.get("action"):
        return f"{stamp} * {who} {text}"
    return f"{stamp} {who}: {text}"


def show(msg):
    """Print one message from the server. A broken message must never stop the receiving thread."""
    try:
        show_message(msg)
    except Exception as e:
        console.out(paint(f"⚠️ Couldn't show a message from the server ({type(e).__name__}).", KIND_COLORS["error"]))


def show_message(msg):
    kind = msg.get("type")
    if kind == "msg":
        console.out(paint(printable(msg.get("text", "")), KIND_COLORS.get(msg.get("kind"), "")))
    elif kind == "chat":
        console.out(format_chat(msg))
    elif kind == "history":
        lines = [paint(f"\n📍 You're in {printable(msg.get('room'))}", BOLD)]
        past = msg.get("messages") or []
        if past:
            lines.append(paint("──── recent messages ────", DIM))
            lines += [format_chat(old) for old in past]
            lines.append(paint("─────────────────────────", DIM))
        console.out("\n".join(lines))
    elif kind == "pong" and isinstance(msg.get("t"), (int, float)):
        pong_waiting.clear()
        ms = round((time.time() - msg["t"]) * 1000)
        console.out(paint(f"🏓 Pong: {ms} ms there and back", KIND_COLORS.get("system", "")))
    elif kind == "file":
        save_file(msg)


# ---------------------------------------------------------------- files

def safe_filename(name):
    """Never trust a filename from the network: keep only the plain name, no folders."""
    name = os.path.basename(str(name).replace("\\", "/"))
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"/\\|?*').strip(" .")
    stem, ext = os.path.splitext(name)
    if not stem or stem.upper() in WINDOWS_RESERVED:
        stem = "file_" + stem
    return stem[:60] + ext[:10]


def save_file(msg):
    sender = printable(msg.get("from", "someone"))
    try:
        data = base64.b64decode(str(msg.get("data", "")), validate=True)
    except ValueError:
        console.out(paint(f"📁 {sender} sent a broken file.", KIND_COLORS["error"]))
        return
    if len(data) > MAX_FILE_SIZE:
        console.out(paint(f"📁 {sender} sent a file that's too big. Ignored.", KIND_COLORS["error"]))
        return
    name = safe_filename(msg.get("filename", "file"))
    stem, ext = os.path.splitext(name)
    path, n = os.path.join(DOWNLOAD_DIR, name), 1
    try:
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        while os.path.exists(path):  # don't overwrite older files
            path = os.path.join(DOWNLOAD_DIR, f"{stem}_{n}{ext}")
            n += 1
        with open(path, "wb") as f:
            f.write(data)
    except OSError as e:
        console.out(paint(f"📁 {sender} sent you a file but I couldn't save it ({e.strerror or e}).",
                          KIND_COLORS["error"]))
        return
    console.out(paint(f"📥 {sender} sent you a file ({len(data) // 1024 + 1} KB), saved to {os.path.abspath(path)}",
                KIND_COLORS["event"]))


def send_file(sock, line):
    parts = line.split(maxsplit=2)
    if len(parts) < 3:
        console.out(paint("Usage: /sendfile name path/to/file", KIND_COLORS["error"]))
        return
    target = parts[1]
    path = os.path.expanduser(parts[2].strip().strip('"').strip("'"))
    if not os.path.isfile(path):
        console.out(paint(f"📁 Can't find {path}", KIND_COLORS["error"]))
        return
    try:
        if os.path.getsize(path) > MAX_FILE_SIZE:
            console.out(paint("📁 Files must be 2 MB or less.", KIND_COLORS["error"]))
            return
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")  # bytes -> text, so it fits in JSON
    except OSError as e:
        console.out(paint(f"📁 Can't read {path} ({e.strerror or e}).", KIND_COLORS["error"]))
        return
    send(sock, {"type": "file", "to": target, "filename": os.path.basename(path), "data": data})
    console.out(paint(f"📤 Sending {os.path.basename(path)} to {target}...", DIM))


# ---------------------------------------------------------------- login

def ask_password(prompt="Password: "):
    # getpass only works in a real terminal. In PyCharm's Run window it freezes on
    # Windows (it waits for keys from a console window that doesn't exist), so
    # there we fall back to a normal input() where the password is visible.
    if not sys.stdin.isatty():
        return input(prompt.replace(":", " (visible):", 1))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return getpass.getpass(prompt)


def login(sock, messages):
    print(paint("💬 Welcome to the chat!", BOLD))
    while True:
        choice = input("1) Log in   2) Create account\n> ").strip()
        if choice not in ("1", "2"):
            continue
        username = input("Username: ").strip()
        password = ask_password()
        if choice == "2" and ask_password("Repeat password: ") != password:
            print(paint("Passwords don't match, try again.", KIND_COLORS["error"]))
            continue
        link["username"] = username
        send(sock, {"type": "auth", "action": "login" if choice == "1" else "register",
                    "username": username, "password": password, "features": FEATURES})
        print(paint("⏳ Checking...", DIM))
        sock.settimeout(15)  # don't wait forever if the server never answers
        for msg in messages:
            if msg.get("type") == "auth_result" or msg is TIMED_OUT:
                break
            show(msg)
        else:
            print(paint("❌ The server closed the connection. Run the client again to retry.",
                        KIND_COLORS["error"]))
            return False
        if msg is TIMED_OUT:
            print(paint("❌ No answer from the server. Make sure it's running the NEW server.py "
                        "(with games.py next to it), then try again.", KIND_COLORS["error"]))
            return False
        sock.settimeout(None)
        print(paint(printable(msg.get("text", "")), KIND_COLORS["money" if msg.get("ok") else "error"]))
        if msg.get("ok"):
            keep(msg)   # 🔁 the resume token
            return True


# ---------------------------------------------------------------- main

def keep(msg):
    """🔁 Remember the token and the packet number. False for a packet we already have."""
    if msg.get("kicked") is True:
        link["kicked"] = True
    if msg.get("type") == "auth_result" and msg.get("ok") and isinstance(msg.get("resume_token"), str):
        link["token"] = msg["resume_token"]
    seq = msg.get("seq")
    if not isinstance(seq, int) or isinstance(seq, bool):
        return True
    if seq <= link["seq"]:
        return False
    link["seq"] = seq
    return True


def receive_loop(messages):
    """Runs in the background so messages show up while you're typing. After a drop it reconnects by itself."""
    while messages is not None:
        for msg in messages:
            if keep(msg):
                show(msg)
        if quitting.is_set():
            return
        messages = reconnect()
    if not quitting.is_set():
        console.out(paint("[CLIENT] Disconnected from the server. Press Enter to exit.", KIND_COLORS["error"]))
        quitting.set()


def reconnect():
    """🔁 The connection dropped: log back in with the token and catch up. The new messages, or None."""
    if not link["token"] or link["kicked"]:
        return None
    console.out(paint("🔁 Lost the connection. Reconnecting…", KIND_COLORS["system"]))
    for wait in RECONNECT_WAITS:
        if quitting.wait(wait):
            return None
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(10)
            sock.connect((link["server"], PORT))
            send(sock, {"type": "auth", "action": "resume", "username": link["username"], "token": link["token"],
                        "seq": link["seq"], "features": FEATURES})
            messages = read_messages(sock)
            for msg in messages:
                if msg.get("type") != "auth_result":
                    continue
                if not msg.get("ok"):
                    console.out(paint(printable(msg.get("text", "")), KIND_COLORS["error"]))
                    sock.close()
                    return None
                keep(msg)
                sock.settimeout(None)
                old, link["sock"] = link["sock"], sock
                old.close()
                console.out(paint("🔁 Reconnected! Here's what you missed:", KIND_COLORS["money"]))
                return messages
            sock.close()   # it closed before answering: try again
        except OSError:
            sock.close()
    return None


def chat_loop(sock):
    while not quitting.is_set():
        text = console.read().strip()
        if quitting.is_set():
            break
        if not text:
            continue
        sock = link["sock"] or sock   # 🔁 after a reconnect: the new connection
        try:
            if text.lower().split()[0] == "/sendfile":
                send_file(sock, text)
            elif text.lower() == "/ping":
                send_ping(sock)
            elif text.lower() == "/quit":
                quitting.set()  # set first, so the receiver doesn't report a "disconnect"
                send(sock, {"type": "line", "text": text})
                break
            else:
                send(sock, {"type": "line", "text": text})
        except OSError:   # dropped: the receiver reconnects (or says goodbye); this line is lost
            console.out(paint("[CLIENT] Not sent: the connection dropped. Try again in a moment.", KIND_COLORS["error"]))


def discover(targets=None, timeout=1.5):
    """🔎 Shout {"type": "discover"} over UDP and collect [(server IP, name)] from whoever answers.
    The default target is the broadcast address: every computer on this Wi-Fi gets the packet."""
    targets = targets or [("255.255.255.255", DISCOVERY_PORT)]
    found = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for target in targets:
            try:
                udp.sendto(b'{"type": "discover"}', target)
            except OSError:
                continue  # e.g. no network at all
            if "--packets" in FLAGS:
                show_packet(f'⬆ UDP to {target[0]}:{target[1]}  {{"type": "discover"}}')
        udp.settimeout(timeout)
        while True:
            try:
                data, (ip, _port) = udp.recvfrom(2048)
            except ConnectionResetError:
                continue  # Windows: an earlier "port unreachable" from someone else, keep listening
            except (socket.timeout, OSError):
                return found
            if "--packets" in FLAGS:
                show_packet(f"⬇ UDP from {ip}  {data.decode('utf-8', 'replace')}")
            try:
                reply = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                continue
            if isinstance(reply, dict) and reply.get("type") == "server" and ip not in [f[0] for f in found]:
                found.append((ip, printable(str(reply.get("name", "Hashbrown Chat")))[:40]))
                if len(found) >= MAX_SERVERS:
                    return found


def find_server():
    """No IP given: look for servers on the Wi-Fi, then on this computer, else ask."""
    print("🔎 Looking for a Hashbrown server on this Wi-Fi...")
    servers = discover() or discover(targets=[("127.0.0.1", DISCOVERY_PORT)], timeout=0.3)
    if servers and not sys.stdin.isatty():
        print(f"🔎 Found {servers[0][1]} at {servers[0][0]}")
        return servers[0][0]
    # Anyone on the Wi-Fi can answer a broadcast, so a person checks the address before we send a password
    if len(servers) == 1:
        if input(f"🔎 Found {servers[0][1]} at {servers[0][0]}. Connect? (Enter = yes, n = no) ").strip().lower() != "n":
            return servers[0][0]
        servers = []
    if servers:
        return choose_server(servers)
    return ask_for_ip() if sys.stdin.isatty() else "127.0.0.1"


def choose_server(servers):
    for number, (ip, name) in enumerate(servers, 1):
        print(f"  {number}) {name} at {ip}")
    answer = input("Which one? (Enter = 1)\n> ").strip()
    index = int(answer) - 1 if answer.isdecimal() and 0 < int(answer) <= len(servers) else 0
    return servers[index][0]


def ask_for_ip():
    answer = input("No server found. The host's IP address (Enter = this computer): ").strip()
    return answer or "127.0.0.1"


def ask_terminal_or_web():
    """Ask how to play. Enter means the terminal. Only asks when someone is typing at a keyboard."""
    if not sys.stdin.isatty():
        return "terminal"
    answer = input("1) Play here in the terminal   2) Open the website\n> ").strip()
    return "web" if answer == "2" else "terminal"


def open_website(ip):
    """Open the host's website in the browser. False if it isn't running (then we use the terminal)."""
    url = f"http://{ip}:{WEB_PORT}"
    try:
        socket.create_connection((ip, WEB_PORT), timeout=2).close()
    except OSError:
        print(f"🌐 The website isn't running on {ip}:{WEB_PORT}. Using the terminal instead.")
        return False
    webbrowser.open(url)
    print(f"🌐 Opened {url} in your browser. (If nothing opened, copy that link into it.)")
    return True


def main():
    server_ip = SERVER_IP or find_server()
    mode = "web" if "--web" in FLAGS else ask_terminal_or_web()
    if mode == "web" and open_website(server_ip):
        return
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((server_ip, PORT))
    except OSError as e:
        print(f"[CLIENT] Can't connect to {server_ip}:{PORT} ({e})")
        return
    link["sock"], link["server"] = sock, server_ip
    try:
        messages = read_messages(sock)
        if login(sock, messages):
            threading.Thread(target=receive_loop, args=(messages,), daemon=True).start()
            chat_loop(sock)
    except (KeyboardInterrupt, EOFError):
        pass
    except OSError:
        print("[CLIENT] Lost connection to the server.")
    finally:
        quitting.set()
        (link["sock"] or sock).close()
        print("[CLIENT] Bye 👋")


if __name__ == "__main__":
    main()
