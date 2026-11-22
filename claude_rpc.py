#!/usr/bin/env python3
"""Discord Rich Presence for Claude Code.

Usage:
  claude_rpc.py hook     # called by Claude Code hooks (reads hook JSON on stdin)
  claude_rpc.py daemon   # background presence updater (auto-spawned by hook)
  claude_rpc.py status   # print current sessions + daemon state
  claude_rpc.py stop     # stop daemon and clear presence
  claude_rpc.py test     # show a test presence for 10s
  claude_rpc.py config [KEY VALUE]   # print / set config (e.g. config client_id 1234...)

Stdlib only. Config: ~/.config/claude-discord-rpc/config.json
"""
import json
import os
import signal
import socket
import struct
import subprocess
import sys
import time
import uuid
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "claude-discord-rpc" / "config.json"
STATE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "claude-discord-rpc"
SESS_DIR = STATE_DIR / "sessions"
PID_FILE = STATE_DIR / "daemon.pid"
LOG_FILE = STATE_DIR / "daemon.log"

DEFAULT_CONFIG = {
    "client_id": "",                # Discord application ID (required)
    "show_project": True,           # show project folder name publicly
    "show_file": True,              # show file names being edited/read
    "large_image": "https://claude.ai/images/claude_app_icon.png",
    "large_text": "Claude Code",
    "button": None,                 # e.g. {"label": "Get Claude Code", "url": "https://claude.com/claude-code"}
    "stale_minutes": 45,            # drop sessions with no hook activity for this long
    "idle_exit_seconds": 60,        # daemon exits after this long with no sessions
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        cfg.update(json.loads(CONFIG_PATH.read_text()))
    except FileNotFoundError:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n")
    except Exception:
        pass
    if os.environ.get("CLAUDE_RPC_CLIENT_ID"):
        cfg["client_id"] = os.environ["CLAUDE_RPC_CLIENT_ID"]
    return cfg


# ---------------------------------------------------------------- hook side

TOOL_VERBS = {
    "Edit": "Editing", "Write": "Writing", "MultiEdit": "Editing", "NotebookEdit": "Editing",
    "Read": "Reading", "Grep": "Searching code", "Glob": "Searching files",
    "Bash": "Running a command", "WebFetch": "Browsing the web", "WebSearch": "Searching the web",
    "Agent": "Delegating to an agent", "Task": "Delegating to an agent",
    "TodoWrite": "Planning", "Skill": "Using a skill",
}


def describe_tool(name, inp, cfg):
    if not name:
        return "Working"
    if name.startswith("mcp__"):
        parts = name.split("__")
        return f"Using {parts[1] if len(parts) > 1 else 'MCP'}"
    verb = TOOL_VERBS.get(name, f"Using {name}")
    if cfg.get("show_file") and isinstance(inp, dict) and name in ("Edit", "Write", "MultiEdit", "Read", "NotebookEdit"):
        p = inp.get("file_path") or inp.get("notebook_path")
        if p:
            return f"{verb} {Path(p).name}"[:120]
    return verb


def daemon_alive():
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return pid
    except Exception:
        return None


def spawn_daemon():
    if daemon_alive():
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as log:
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "daemon"],
            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            start_new_session=True, close_fds=True,
        )


def hook():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    cfg = load_config()
    sid = data.get("session_id") or "unknown"
    event = data.get("hook_event_name", "")
    SESS_DIR.mkdir(parents=True, exist_ok=True)
    f = SESS_DIR / f"{sid}.json"

    if event == "SessionEnd":
        f.unlink(missing_ok=True)
        return

    try:
        sess = json.loads(f.read_text())
    except Exception:
        sess = {"started": int(time.time())}

    cwd = data.get("cwd") or sess.get("cwd") or os.getcwd()
    sess["cwd"] = cwd
    sess["project"] = Path(cwd).name or cwd
    model = data.get("model")
    if isinstance(model, dict):
        model = model.get("display_name") or model.get("id")
    if model:
        sess["model"] = str(model)

    if event == "SessionStart":
        sess["status"] = "Starting up"
    elif event == "UserPromptSubmit":
        sess["status"] = "Thinking"
        sess["prompts"] = sess.get("prompts", 0) + 1
    elif event == "PreToolUse":
        sess["status"] = describe_tool(data.get("tool_name"), data.get("tool_input"), cfg)
    elif event in ("Stop", "SubagentStop"):
        if event == "Stop":
            sess["status"] = "Waiting for input"
    elif event == "Notification":
        sess["status"] = "Waiting for input"
    sess["updated"] = int(time.time())

    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(sess))
    tmp.replace(f)
    spawn_daemon()


# -------------------------------------------------------------- discord IPC

def ipc_candidates():
    bases = []
    for env in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP"):
        if os.environ.get(env):
            bases.append(os.environ[env])
    bases += [f"/run/user/{os.getuid()}", "/tmp"]
    subs = ["", "app/com.discordapp.Discord", "app/com.discordapp.DiscordCanary",
            "app/dev.vencord.Vesktop", "snap.discord", ".flatpak/dev.vencord.Vesktop/xdg-run"]
    seen = set()
    for b in bases:
        for s in subs:
            for i in range(10):
                p = os.path.join(b, s, f"discord-ipc-{i}")
                if p not in seen:
                    seen.add(p)
                    yield p


class DiscordIPC:
    def __init__(self, client_id):
        self.client_id = client_id
        self.sock = None

    def connect(self):
        for path in ipc_candidates():
            if not os.path.exists(path):
                continue
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect(path)
                self.sock = s
                self._send(0, {"v": 1, "client_id": self.client_id})
                op, resp = self._recv()
                if resp.get("evt") == "READY":
                    return True
                log(f"handshake failed on {path}: {resp}")
                self.close()
            except Exception as e:
                log(f"connect {path}: {e}")
                self.close()
        return False

    def _send(self, op, payload):
        body = json.dumps(payload).encode()
        self.sock.sendall(struct.pack("<II", op, len(body)) + body)

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("socket closed")
            buf += chunk
        return buf

    def _recv(self):
        op, length = struct.unpack("<II", self._recv_exact(8))
        return op, json.loads(self._recv_exact(length) or b"{}")

    def set_activity(self, activity):
        self._send(1, {"cmd": "SET_ACTIVITY", "args": {"pid": os.getpid(), "activity": activity},
                       "nonce": str(uuid.uuid4())})
        op, resp = self._recv()
        if resp.get("evt") == "ERROR":
            raise RuntimeError(resp.get("data"))

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None


# ------------------------------------------------------------------- daemon

def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def load_sessions(cfg):
    now = time.time()
    out = []
    for f in SESS_DIR.glob("*.json"):
        try:
            s = json.loads(f.read_text())
        except Exception:
            continue
        if now - s.get("updated", 0) > cfg["stale_minutes"] * 60:
            f.unlink(missing_ok=True)
            continue
        out.append(s)
    out.sort(key=lambda s: s.get("updated", 0), reverse=True)
    return out


def build_activity(sessions, cfg):
    s = sessions[0]
    details = f"Working on {s['project']}" if cfg["show_project"] else "Coding with Claude"
    state = s.get("status", "Idle")
    if len(sessions) > 1:
        state = f"{state} · {len(sessions)} sessions"
    large_text = cfg["large_text"]
    if s.get("model"):
        large_text = f"{large_text} · {s['model']}"
    act = {
        "details": details[:128],
        "state": state[:128],
        "timestamps": {"start": s.get("started", int(time.time()))},
        "assets": {"large_image": cfg["large_image"], "large_text": large_text[:128]},
    }
    if cfg.get("button"):
        act["buttons"] = [cfg["button"]]
    return act


def daemon():
    cfg = load_config()
    if not cfg["client_id"]:
        log(f"no client_id set in {CONFIG_PATH}; exiting")
        return
    if daemon_alive() and daemon_alive() != os.getpid():
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))

    ipc = DiscordIPC(cfg["client_id"])
    running = True

    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    last_sent, last_time, empty_since, next_connect = None, 0.0, None, 0.0
    log("daemon started")
    try:
        while running:
            sessions = load_sessions(cfg)
            now = time.time()
            if not sessions:
                empty_since = empty_since or now
                if now - empty_since > cfg["idle_exit_seconds"]:
                    break
            else:
                empty_since = None

            if ipc.sock is None and now >= next_connect:
                if ipc.connect():
                    log("connected to Discord")
                    last_sent = None
                else:
                    next_connect = now + 15

            if ipc.sock is not None:
                act = build_activity(sessions, cfg) if sessions else None
                # Discord rate-limits SET_ACTIVITY (~5 per 20s): send only on change, >=4s apart
                if act != last_sent and now - last_time >= 4:
                    try:
                        ipc.set_activity(act)
                        last_sent, last_time = act, now
                    except Exception as e:
                        log(f"set_activity failed: {e}")
                        ipc.close()
            time.sleep(1)
    finally:
        if ipc.sock is not None:
            try:
                ipc.set_activity(None)
            except Exception:
                pass
            ipc.close()
        try:
            if PID_FILE.read_text().strip() == str(os.getpid()):
                PID_FILE.unlink()
        except Exception:
            pass
        log("daemon stopped")


def status():
    cfg = load_config()
    print("config:", CONFIG_PATH, "(client_id set)" if cfg["client_id"] else "(client_id MISSING)")
    print("daemon pid:", daemon_alive() or "not running")
    for s in load_sessions(cfg):
        print(f"  {s.get('project')}: {s.get('status')} (updated {int(time.time() - s['updated'])}s ago)")


def stop_daemon():
    pid = daemon_alive()
    if pid:
        os.kill(pid, signal.SIGTERM)
        print("stopped", pid)
        for _ in range(20):
            if not daemon_alive():
                break
            time.sleep(0.25)


def test():
    cfg = load_config()
    if not cfg["client_id"]:
        sys.exit(f"client_id missing. Run: {sys.argv[0]} config client_id <DISCORD_APPLICATION_ID>")
    ipc = DiscordIPC(cfg["client_id"])
    if not ipc.connect():
        sys.exit("Could not connect to Discord. Is the desktop app running? (see log lines above)")
    ipc.set_activity({"details": "Testing Claude Discord RPC", "state": "It works!",
                      "timestamps": {"start": int(time.time())},
                      "assets": {"large_image": cfg["large_image"], "large_text": cfg["large_text"]}})
    print("Connected. Test presence visible on your profile for 10s...")
    time.sleep(10)
    ipc.set_activity(None)
    ipc.close()
    print("OK")


def config_cmd():
    """config                -> print config
       config KEY VALUE      -> set key (VALUE parsed as JSON if possible)"""
    cfg = load_config()
    args = sys.argv[2:]
    if len(args) >= 2:
        key, raw = args[0], " ".join(args[1:])
        if key not in DEFAULT_CONFIG:
            sys.exit(f"unknown key {key!r}; valid: {', '.join(DEFAULT_CONFIG)}")
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            val = raw
        if key == "client_id":
            val = str(val)
        try:
            stored = json.loads(CONFIG_PATH.read_text())
        except Exception:
            stored = dict(DEFAULT_CONFIG)
        stored[key] = val
        CONFIG_PATH.write_text(json.dumps(stored, indent=2) + "\n")
        cfg = load_config()
    print(json.dumps(cfg, indent=2))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "hook"
    cmds = {"hook": hook, "daemon": daemon, "status": status, "stop": stop_daemon,
            "test": test, "config": config_cmd}
    if cmd not in cmds:
        sys.exit(__doc__)
    try:
        cmds[cmd]()
    except Exception as e:
        if cmd != "hook":
            raise
        # never break Claude Code because of presence
        print(f"claude-discord-rpc: {e}", file=sys.stderr)
    sys.exit(0)
