"""One sleeping event loop: 30 s quiet period, 60 s reconciliation, sparse writes."""
from __future__ import annotations

import ctypes
import fcntl
import json
import os
from pathlib import Path
import selectors
import signal
import socket
import struct
import subprocess
import time


class QuietPeriod:
    def __init__(self, delay=30):
        self.delay = delay
        self.changed_at = None

    def change(self, now):
        self.changed_at = now

    def deadline(self):
        return None if self.changed_at is None else self.changed_at + self.delay

    def ready(self, now):
        return self.changed_at is not None and now >= self.deadline()

    def clear(self):
        self.changed_at = None


class Notifications:
    """Native sockets and inotify; no polling child process, thread or extra service."""
    def __init__(self, api):
        self.api = api
        self.selector = selectors.DefaultSelector()
        self.wakeup, self.writer = socket.socketpair()
        self.wakeup.setblocking(False)
        self.selector.register(self.wakeup, selectors.EVENT_READ, "signal")
        self.ipc = None
        self.inotify = None
        self.buffer = b""
        self.connect()
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
            if fd >= 0:
                watch = libc.inotify_add_watch(fd, os.fsencode(api.STATE_DIR), 0x00000008 | 0x00000080)
                if watch >= 0:
                    self.inotify = fd
                    self.selector.register(fd, selectors.EVENT_READ, "files")
                else:
                    os.close(fd)
        except (AttributeError, OSError):
            pass  # Minute reconciliation also covers unavailable notifications.

    def connect(self):
        if self.ipc:
            return
        runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        path = Path(runtime) / "hypr" / os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "") / ".socket2.sock"
        connection = socket.socket(socket.AF_UNIX)
        connection.settimeout(.5)
        try:
            connection.connect(str(path))
            connection.setblocking(False)
            self.ipc = connection
            self.selector.register(connection, selectors.EVENT_READ, "hypr")
        except OSError:
            connection.close()

    def wait(self, timeout):
        events = []
        for key, _ in self.selector.select(max(0, timeout)):
            if key.data == "signal":
                self.wakeup.recv(4096)
            elif key.data == "files":
                data = os.read(self.inotify, 65536)
                position = 0
                while position + 16 <= len(data):
                    _, _, _, length = struct.unpack_from("iIII", data, position)
                    name = data[position+16:position+16+length].split(b"\0", 1)[0]
                    if name == b"AGENT_IDS.json":
                        events.append(("agent", ""))
                    position += 16 + length
            else:
                data = self.ipc.recv(65536)
                if not data:
                    self.selector.unregister(self.ipc)
                    self.ipc.close()
                    self.ipc = None
                    continue
                self.buffer = (self.buffer + data)[-1048576:]
                while b"\n" in self.buffer:
                    line, self.buffer = self.buffer.split(b"\n", 1)
                    name, _, payload = line.decode(errors="replace").partition(">>")
                    events.append((name, payload))
        return events

    def wake(self):
        try:
            self.writer.send(b"x")
        except OSError:
            pass

    def close(self):
        self.selector.close()
        self.wakeup.close()
        self.writer.close()
        if self.ipc:
            self.ipc.close()
        if self.inotify is not None:
            os.close(self.inotify)


def registry_state(api):
    try:
        registry = json.loads(api.AGENT_IDS_FILE.read_text())
        return {key: {k: row.get(k) for k in ("agent", "session_id", "state", "has_user_turn", "kitty_pid", "kitty_start_ticks")}
                for key, row in registry.items() if key.startswith("kitty:") and isinstance(row, dict)}
    except (OSError, ValueError, AttributeError):
        return {}


def relevant_event(name, payload, addresses, workspace):
    if name in {"monitoradded", "monitorremoved", "configreloaded"}:
        return True
    if name == "openwindow":
        parts = payload.split(",", 3)
        return len(parts) > 1 and parts[1] == str(workspace)
    if name in {"closewindow", "activewindowv2", "changefloatingmode", "movewindowv2", "togglegroup", "moveintogroup", "moveoutofgroup", "pin"}:
        parts = payload.split(",")
        return any((p if p.startswith("0x") else "0x" + p) in addresses for p in parts)
    return name == "fullscreen" and bool(addresses)


def monitor(api):
    api.STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    with api.LOCK_FILE.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        api.wait_for_hyprland()
        previous = api.load_state()
        if previous and previous.get("boot_id") != api.boot_id():
            api.restore(previous)
        notifications = Notifications(api)
        stopping = False
        def stop(_signum, _frame):
            nonlocal stopping
            stopping = True
            notifications.wake()
        old_signals = {s: signal.signal(s, stop) for s in (signal.SIGTERM, signal.SIGINT)}
        quiet = QuietPeriod(api.DEBOUNCE_SECONDS)
        quiet.change(time.monotonic())
        targets = set()
        registry = registry_state(api)
        reference = None
        pending_probe = None
        last_probe = float("-inf")
        next_check = time.monotonic()
        addresses = set()
        signature = None
        try:
            while not stopping:
                now = time.monotonic()
                if now >= next_check or quiet.ready(now):
                    # Coalesce consolidation probes; keep the minute reconciliation due.
                    if now - last_probe < api.DEBOUNCE_SECONDS and now < next_check:
                        wake = last_probe + api.DEBOUNCE_SECONDS
                    else:
                        if api.shutting_down():
                            break
                        if api.restoration_in_progress():
                            quiet.change(now)
                            next_check = now + api.RECONCILE_SECONDS
                            continue
                        full = now >= next_check
                        try:
                            probe = api.probe_scene(None if full else targets)
                        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError, KeyError) as error:
                            api.write_restore_status("monitoramento_com_erro", str(error))
                            quiet.change(time.monotonic())
                            last_probe = time.monotonic()
                            next_check = last_probe + api.RECONCILE_SECONDS
                            continue
                        saved = api.load_state(api.CAPTURE_FILE) or api.load_state()
                        current = api.probe_signature(probe, saved)
                        last_probe = time.monotonic()
                        addresses = {c["address"] for c in probe["clients"]}
                        if full:
                            next_check = last_probe + api.RECONCILE_SECONDS
                            notifications.connect()
                        if quiet.ready(now):
                            if reference is not None and current != reference:
                                quiet.change(last_probe)
                                reference = current
                            else:
                                # Refresh the terminal data from the previous full probe if
                                # this quiet-period probe only checked compositor metadata.
                                if pending_probe:
                                    for pid, data in pending_probe["terminals"].items():
                                        probe["terminals"].setdefault(pid, data)
                                api.snapshot(allow_empty=True, probe=probe)
                                quiet.clear()
                                reference = None
                                targets.clear()
                                pending_probe = None
                                signature = current
                        elif signature is None or current != signature:
                            quiet.change(last_probe)
                            reference = current
                            pending_probe = probe
                            targets.update(probe["terminals"])
                        signature = current
                        wake = min(next_check, quiet.deadline() or next_check)
                else:
                    wake = min(next_check, quiet.deadline() or next_check)
                for name, payload in notifications.wait(wake - time.monotonic()):
                    if name == "agent":
                        updated = registry_state(api)
                        changed = [v for key, v in updated.items() if registry.get(key) != v]
                        if changed:
                            targets.update(int(v["kitty_pid"]) for v in changed if v.get("kitty_pid"))
                            quiet.change(time.monotonic())
                            reference = signature
                        registry = updated
                    elif relevant_event(name, payload, addresses, api.WORKSPACE_ID):
                        quiet.change(time.monotonic())
                        reference = signature
        finally:
            for sig, handler in old_signals.items():
                signal.signal(sig, handler)
            notifications.close()
    return 0
