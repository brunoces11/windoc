#!/usr/bin/env python3
"""Persist workspace 1 using Hyprland IPC and Kitty's native session format.

Runtime snapshots are private and live in ESTADO_LOCAL, which is gitignored.
Agent adapters store immutable session IDs; titles are deliberately ignored.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "ESTADO_LOCAL"
STATE_FILE = STATE_DIR / "WORKSPACE1.json"
AGENT_IDS_FILE = STATE_DIR / "AGENT_IDS.json"
LOCK_FILE = STATE_DIR / "WORKSPACE1.lock"
WORKSPACE_ID = 1
POLL_SECONDS = 8
EMPTY_GRACE_SECONDS = 60
UUID_RE = re.compile(r"(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def run(argv: list[str], *, timeout: float = 8, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=check)


def hypr_json(command: str) -> Any:
    return json.loads(run(["hyprctl", command, "-j"]).stdout)


def clients() -> list[dict[str, Any]]:
    return hypr_json("clients")


def workspace_clients() -> list[dict[str, Any]]:
    return [c for c in clients() if c.get("workspace", {}).get("id") == WORKSPACE_ID]


def kitty_socket(pid: int) -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    path = Path(runtime) / f"omarchy-kitty-{pid}"
    if not path.exists():
        raise FileNotFoundError(f"Kitty socket not found for PID {pid}")
    return f"unix:{path}"


def kitty_call(pid: int, *args: str, timeout: float = 8) -> subprocess.CompletedProcess[str]:
    return run(["kitty", "@", "--to", kitty_socket(pid), *args], timeout=timeout)


def foreground_process(window: dict[str, Any]) -> dict[str, Any] | None:
    processes = window.get("foreground_processes") or []
    return processes[-1] if processes else None


def process_command(process: dict[str, Any]) -> list[str]:
    value = process.get("cmdline") or []
    return [str(part) for part in value]


def process_environ(pid: int) -> dict[str, str]:
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    except OSError:
        return {}
    result: dict[str, str] = {}
    for entry in raw:
        if b"=" not in entry:
            continue
        key, value = entry.split(b"=", 1)
        name = key.decode(errors="ignore")
        if name in {"CODEX_HOME", "HOME"}:
            result[name] = value.decode(errors="ignore")
    return result


def process_start_ticks(pid: int) -> str | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        fields = stat[stat.rfind(")") + 2 :].split()
        return fields[19]
    except (OSError, IndexError):
        return None


def register_session_id(agent: str, pid: int, session_id: str, start_ticks: str | None, method: str) -> None:
    if not UUID_RE.fullmatch(session_id) or not start_ticks:
        return
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE_DIR / "AGENT_IDS.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            current = json.loads(AGENT_IDS_FILE.read_text()) if AGENT_IDS_FILE.exists() else {}
        except (OSError, ValueError):
            current = {}
        record = current.get(str(pid), {})
        if (record.get("agent") == agent and record.get("session_id") == session_id
                and record.get("start_ticks") == start_ticks and record.get("id_method") == method):
            return
        current[str(pid)] = {
            "agent": agent,
            "session_id": session_id,
            "start_ticks": start_ticks,
            "id_method": method,
            "updated_at": int(time.time()),
        }
        atomic_write(AGENT_IDS_FILE, (json.dumps(current, sort_keys=True, indent=2) + "\n").encode())


def process_fd_targets(pid: int) -> list[str]:
    targets: list[str] = []
    try:
        fds = Path(f"/proc/{pid}/fd").iterdir()
        for fd in fds:
            try:
                targets.append(os.readlink(fd))
            except OSError:
                continue
    except OSError:
        pass
    return targets


def process_mapped_files(pid: int) -> list[str]:
    try:
        lines = Path(f"/proc/{pid}/maps").read_text().splitlines()
    except OSError:
        return []
    return [line.rsplit(maxsplit=1)[-1] for line in lines if len(line.split()) > 5 and line.rsplit(maxsplit=1)[-1].startswith("/")]


def uuid_from_args(argv: list[str]) -> str | None:
    return next((arg for arg in argv if UUID_RE.fullmatch(arg)), None)


def detect_agent(argv: list[str]) -> str | None:
    text = " ".join(argv).lower()
    if "codex" in text:
        return "codex"
    if "claude" in text:
        return "claude-code"
    if "antigravity" in text or re.search(r"(?:^|[/ ])agy(?:$| )", text):
        return "antigravity"
    return None


def codex_session_id(pid: int) -> tuple[str | None, str]:
    """Map the TUI PID to its thread ID through its startup event and app-server logs.

    Codex currently logs TUI events with a PID-scoped process_uuid and thread
    lifecycle events with thread_id in the shared local SQLite log. The IDs are
    accepted only when one thread event is within 250 ms of this TUI's startup.
    Schema changes or ambiguous matches fail closed.
    """
    env = process_environ(pid)
    codex_home = Path(env.get("CODEX_HOME", str(Path.home() / ".codex")))
    db = codex_home / "logs_2.sqlite"
    if not db.is_file():
        return None, "codex-log-db-unavailable"
    try:
        uri = db.as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=0.05) as conn:
            startup = conn.execute(
                "SELECT ts, ts_nanos FROM logs "
                "WHERE process_uuid LIKE ? AND module_path='codex_tui::app::startup' "
                "ORDER BY ts DESC, ts_nanos DESC LIMIT 1",
                (f"pid:{pid}:%",),
            ).fetchone()
            if not startup:
                return None, "codex-startup-event-unavailable"
            sec, nanos = startup
            center = int(sec) * 1_000_000_000 + int(nanos)
            rows = conn.execute(
                "SELECT thread_id, ts, ts_nanos FROM logs "
                "WHERE thread_id IS NOT NULL AND ts BETWEEN ? AND ?",
                (int(sec) - 1, int(sec) + 1),
            ).fetchall()
        matches: dict[str, int] = {}
        for thread_id, row_sec, row_nanos in rows:
            if not UUID_RE.fullmatch(str(thread_id)):
                continue
            delta = abs(int(row_sec) * 1_000_000_000 + int(row_nanos) - center)
            if delta <= 250_000_000:
                matches[str(thread_id)] = min(delta, matches.get(str(thread_id), delta))
        if not matches:
            return None, "codex-thread-id-not-correlated"
        if len(matches) != 1:
            return None, "codex-thread-id-ambiguous"
        return next(iter(matches)), "codex-process-startup-correlation"
    except (sqlite3.Error, OSError, ValueError):
        return None, "codex-log-schema-unavailable"


def antigravity_bootstrap_id(title: str, cwd: str) -> str | None:
    """Resolve an already-open legacy tab once; only a unique exact DB title is accepted."""
    if "Antigravity:" not in title:
        return None
    topic = title.split("Antigravity:", 1)[1].split("|", 1)[0].strip()
    if not topic:
        return None
    db = Path.home() / ".gemini/antigravity-cli/conversation_summaries.db"
    try:
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=0.05) as conn:
            rows = conn.execute(
                "SELECT conversation_id, workspace_uris FROM conversation_summaries WHERE title=?",
                (topic,),
            ).fetchall()
        matches = [row[0] for row in rows if UUID_RE.fullmatch(str(row[0])) and (not row[1] or cwd in row[1])]
        return matches[0] if len(matches) == 1 else None
    except (sqlite3.Error, OSError, ValueError):
        return None


def session_id_for(agent: str, process: dict[str, Any], *, title: str = "", cwd: str = "") -> tuple[str | None, str]:
    pid = int(process.get("pid") or 0)
    start_ticks = process_start_ticks(pid)
    argv = process_command(process)
    direct = uuid_from_args(argv)
    if direct:
        register_session_id(agent, pid, direct, start_ticks, "process-arguments")
        return direct, "process-arguments"
    try:
        registered = json.loads(AGENT_IDS_FILE.read_text()).get(str(pid), {})
        registered_id = registered.get("session_id") if registered.get("agent") == agent else None
        if (isinstance(registered_id, str) and UUID_RE.fullmatch(registered_id)
                and start_ticks and registered.get("start_ticks") == start_ticks):
            return registered_id, str(registered.get("id_method") or "process-session-registry")
    except (OSError, ValueError, AttributeError):
        pass
    targets = process_fd_targets(pid) + process_mapped_files(pid)
    if agent == "antigravity":
        for target in targets:
            normalized = target.removesuffix(" (deleted)")
            match = re.search(r"/(?:presence/([0-9a-f-]{36})\.lock|conversations/([0-9a-f-]{36})\.db(?:-shm|-wal)?)$", normalized)
            if match:
                session_id = match.group(1) or match.group(2)
                if UUID_RE.fullmatch(session_id):
                    register_session_id(agent, pid, session_id, start_ticks, "process-session-file")
                    return session_id, "process-session-file"
        bootstrap_id = antigravity_bootstrap_id(title, cwd)
        if bootstrap_id:
            register_session_id(agent, pid, bootstrap_id, start_ticks, "unique-bootstrap-match")
            return bootstrap_id, "unique-bootstrap-match"
        return None, "antigravity-session-file-unavailable"
    if agent == "claude-code":
        for target in targets:
            match = re.search(r"/projects/.*/([0-9a-f-]{36})\.jsonl(?: \(deleted\))?$", target)
            if match and UUID_RE.fullmatch(match.group(1)):
                register_session_id(agent, pid, match.group(1), start_ticks, "process-open-transcript")
                return match.group(1), "process-open-transcript"
        return None, "claude-transcript-not-open"
    if agent == "codex":
        session_id, method = codex_session_id(pid)
        if session_id:
            register_session_id(agent, pid, session_id, start_ticks, method)
        return session_id, method
    return None, "adapter-not-installed"


def resume_command(agent: str, session_id: str) -> list[str] | None:
    if not UUID_RE.fullmatch(session_id):
        return None
    commands = {
        "codex": ["codex", "resume", session_id],
        "claude-code": ["claude", "--resume", session_id],
        "antigravity": ["agy", "--conversation", session_id],
    }
    return commands.get(agent)


def agent_records(kitty_pid: int, tree: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    for os_window in tree:
        for tab in os_window.get("tabs", []):
            for window in tab.get("windows", []):
                proc = foreground_process(window)
                if not proc:
                    continue
                agent = detect_agent(process_command(proc))
                if not agent:
                    continue
                session_id, method = session_id_for(
                    agent, proc, title=str(window.get("title") or ""), cwd=str(window.get("cwd") or "")
                )
                records[int(window["id"])] = {
                    "agent": agent,
                    "session_id": session_id,
                    "id_method": method,
                    "pid": int(proc.get("pid") or 0),
                    "start_ticks": process_start_ticks(int(proc.get("pid") or 0)),
                }
    return records


def patch_native_session(text: str, records: dict[int, dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Keep Kitty's generated layout, replacing only known agent launch commands."""
    output: list[str] = []
    summary: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.lstrip().startswith("launch "):
            output.append(line)
            continue
        try:
            parts = shlex.split(line)
        except ValueError:
            output.append(line)
            continue
        token_index = next((i for i, token in enumerate(parts) if token.startswith("kitty-unserialize-data=")), None)
        if token_index is None:
            output.append(line)
            continue
        raw = parts[token_index].split("=", 1)[1]
        try:
            payload = json.loads(raw)
        except ValueError:
            output.append(line)
            continue
        record = records.get(int(payload.get("id", -1)))
        if record:
            command = resume_command(record["agent"], record.get("session_id") or "")
            if command:
                payload["cmd_at_shell_startup"] = shlex.join(command)
            else:
                # An unidentified agent must never silently open an arbitrary/latest chat.
                payload.pop("cmd_at_shell_startup", None)
            parts[token_index] = "kitty-unserialize-data=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            line = "launch " + " ".join(shlex.quote(token) for token in parts[1:])
            summary.append({k: record[k] for k in ("agent", "session_id", "id_method")})
        output.append(line)
    return "\n".join(output) + "\n", summary


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_file() and path.read_bytes() == data:
        return
    fd, temp_name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    temp = Path(temp_name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def save_kitty_session(pid: int, records: dict[int, dict[str, Any]]) -> tuple[str, str]:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".kitty-capture-", suffix=".session", dir=STATE_DIR)
    os.close(fd)
    temp = Path(temp_name)
    try:
        kitty_call(pid, "action", "save_as_session", "--save-only", "--use-foreground-process", str(temp))
        raw = temp.read_text(encoding="utf-8")
        rendered, found = patch_native_session(raw, records)
        name = f"KITTY-{pid}.session"
        destination = STATE_DIR / name
        atomic_write(destination, rendered.encode(), 0o600)
        complete = len(found) == len(records) and all(record.get("session_id") for record in found)
        return name, "ok" if complete else "agent-id-incomplete"
    finally:
        temp.unlink(missing_ok=True)


def snapshot() -> dict[str, Any]:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for client in workspace_clients():
        item: dict[str, Any] = {
            "class": str(client.get("class") or ""),
            "initial_class": str(client.get("initialClass") or ""),
            "address": str(client.get("address") or ""),
            "at": client.get("at", [0, 0]),
            "size": client.get("size", [0, 0]),
            "floating": bool(client.get("floating")),
            "fullscreen": int(client.get("fullscreen") or 0),
        }
        if item["class"].lower() == "kitty":
            pid = int(client.get("pid") or 0)
            try:
                tree = json.loads(kitty_call(pid, "ls").stdout)
                records = agent_records(pid, tree)
                filename, result = save_kitty_session(pid, records)
                item.update({"kind": "kitty", "session_file": filename, "agent_sessions": [
                    {k: v for k, v in record.items() if k in ("agent", "session_id", "id_method")}
                    for record in records.values()
                ]})
                if result != "ok":
                    warnings.append(f"kitty {pid}: ao menos uma sessão de agente não foi identificada sem ambiguidade")
            except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
                item.update({"kind": "kitty", "error": type(error).__name__})
                warnings.append(f"kitty {pid}: captura nativa falhou ({type(error).__name__})")
        else:
            item["kind"] = "application"
            item["restore_command"] = application_command(item["class"])
        rows.append(item)
    state = {
        "schema": 1,
        "workspace": WORKSPACE_ID,
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "updated_at": int(time.time()),
        "windows": rows,
        "warnings": warnings,
    }
    previous = load_state()
    if previous:
        old = {key: value for key, value in previous.items() if key != "updated_at"}
        new = {key: value for key, value in state.items() if key != "updated_at"}
        if old == new:
            return previous
    encoded = (json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    if not STATE_FILE.exists() or STATE_FILE.read_bytes() != encoded:
        atomic_write(STATE_FILE, encoded)
    return state


def application_command(app_class: str) -> list[str] | None:
    known = {
        "chromium": ["chromium"],
        "sublime_text": ["sublime_text"],
        "org.gnome.nautilus": ["nautilus"],
    }
    command = known.get(app_class.lower())
    return command if command and shutil.which(command[0]) else None


def restore(state: dict[str, Any]) -> list[str]:
    restored: list[str] = []
    for item in state.get("windows", []):
        if item.get("kind") == "kitty":
            session = STATE_DIR / str(item.get("session_file", ""))
            if not session.is_file() or session.parent != STATE_DIR:
                continue
            command = ["kitty", "--session", str(session)]
        else:
            command = item.get("restore_command")
            if not isinstance(command, list) or not command:
                continue
        dispatch = f"[workspace {WORKSPACE_ID} silent] {shlex.join(command)}"
        result = run(["hyprctl", "dispatch", "exec", dispatch], check=False)
        if result.returncode == 0:
            restored.append(str(item.get("class") or command[0]))
    return restored


def load_state() -> dict[str, Any] | None:
    try:
        state = json.loads(STATE_FILE.read_text())
        if state.get("schema") == 1 and state.get("workspace") == WORKSPACE_ID:
            return state
    except (OSError, ValueError, AttributeError):
        pass
    return None


def status() -> int:
    state = load_state()
    if not state:
        print("Estado local ainda não existe.")
        return 1
    sessions = [a for w in state.get("windows", []) for a in w.get("agent_sessions", [])]
    known = sum(bool(a.get("session_id")) for a in sessions)
    print(f"Workspace {WORKSPACE_ID}: {len(state.get('windows', []))} janelas; {known}/{len(sessions)} IDs de sessão de agente capturados.")
    for agent in sorted({a.get("agent", "desconhecido") for a in sessions}):
        values = [a for a in sessions if a.get("agent") == agent]
        found = sum(bool(a.get("session_id")) for a in values)
        print(f"{agent}: {found}/{len(values)} IDs identificados")
    for warning in state.get("warnings", []):
        print("AVISO:", warning)
    return 0


def login_loop() -> int:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    with LOCK_FILE.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        previous = load_state()
        current_boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        live = workspace_clients()
        if previous and previous.get("boot_id") != current_boot and not live:
            restore(previous)
            time.sleep(12)
        snapshot()
        empty_since: float | None = None
        stopping = False

        def stop(_signum: int, _frame: Any) -> None:
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        while not stopping:
            try:
                current = workspace_clients()
                if current:
                    empty_since = None
                    snapshot()
                else:
                    empty_since = empty_since or time.monotonic()
                    if time.monotonic() - empty_since >= EMPTY_GRACE_SECONDS:
                        snapshot()
            except (OSError, subprocess.SubprocessError, ValueError, KeyError):
                pass
            time.sleep(POLL_SECONDS)
        try:
            if workspace_clients():
                snapshot()
        except Exception:
            pass
    return 0


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "status"
    if command == "snapshot":
        state = snapshot()
        print(f"Salvo: {len(state['windows'])} janelas no Workspace {WORKSPACE_ID}.")
        return status()
    if command == "restore":
        state = load_state()
        if not state:
            print("Estado local válido não encontrado.", file=sys.stderr)
            return 1
        restored = restore(state)
        print(f"Restauradas {len(restored)} janelas: {', '.join(restored) or 'nenhuma'}")
        return 0
    if command == "login":
        return login_loop()
    if command == "status":
        return status()
    print("Uso: WORKSPACE1.py {status|snapshot|restore|login}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
