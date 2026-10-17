#!/usr/bin/env python3
"""Persist workspace 1 using Hyprland IPC and Kitty's native session format.

Runtime snapshots are private and live in ESTADO_LOCAL, which is gitignored.
Agent adapters store immutable session IDs; titles are deliberately ignored.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "ESTADO_LOCAL"
if os.environ.get("WORKSPACE1_STATE_DIR"):
    STATE_DIR = Path(os.environ["WORKSPACE1_STATE_DIR"])
STATE_FILE = STATE_DIR / "WORKSPACE1.json"
CAPTURE_FILE = STATE_DIR / "LATEST_CAPTURE.json"
RESTORE_STATUS_FILE = STATE_DIR / "RESTORE_STATUS.json"
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


def process_start_ticks(pid: int) -> str | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        fields = stat[stat.rfind(")") + 2 :].split()
        return fields[19]
    except (OSError, IndexError):
        return None


def process_start_epoch(pid: int) -> int | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        stat_fields = stat[stat.rfind(")") + 2 :].split()
        start_ticks = int(stat_fields[19])
        boot_time = next(
            int(line.split()[1])
            for line in Path("/proc/stat").read_text().splitlines()
            if line.startswith("btime ")
        )
        return boot_time + start_ticks // os.sysconf("SC_CLK_TCK")
    except (OSError, StopIteration, ValueError, IndexError):
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
        if not isinstance(current, dict):
            current = {}
        record = current.get(str(pid), {})
        if not isinstance(record, dict):
            record = {}
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


def session_id_from_resume_args(agent: str, argv: list[str]) -> str | None:
    """Accept an ID only when it follows that agent's explicit resume option."""
    tokens = list(argv)
    if agent == "codex":
        for index, token in enumerate(tokens[:-1]):
            if token == "resume" and UUID_RE.fullmatch(tokens[index + 1]):
                return tokens[index + 1]
    elif agent == "claude-code":
        for index, token in enumerate(tokens):
            if token == "--resume":
                if index + 1 < len(tokens) and valid_agent_session_id(agent, tokens[index + 1]):
                    return tokens[index + 1]
            if token.startswith("--resume=") and valid_agent_session_id(agent, token.split("=", 1)[1]):
                return token.split("=", 1)[1]
    elif agent == "antigravity":
        for index, token in enumerate(tokens):
            if token == "--conversation" and index + 1 < len(tokens) and UUID_RE.fullmatch(tokens[index + 1]):
                return tokens[index + 1]
            if token.startswith("--conversation=") and UUID_RE.fullmatch(token.split("=", 1)[1]):
                return token.split("=", 1)[1]
    return None


def detect_agent(argv: list[str]) -> str | None:
    if not argv:
        return None
    executable = Path(argv[0]).name.lower()
    args = [token.lower() for token in argv[1:]]
    if executable in {"codex", "codex-tui", "codex-cli"} or any(
        token.endswith("/@openai/codex/bin/codex.js") or token.endswith("/@openai/codex/bin/codex")
        for token in args
    ):
        return "codex"
    if executable in {"claude", "claude-code"}:
        return "claude-code"
    if executable in {"agy", "antigravity"}:
        return "antigravity"
    return None


def pane_registry_record(agent: str, kitty_pid: int, kitty_window_id: int, agent_pid: int) -> dict[str, Any] | None:
    try:
        registry = json.loads(AGENT_IDS_FILE.read_text())
        if not isinstance(registry, dict):
            return None
        record = registry.get(f"kitty:{kitty_pid}:{kitty_window_id}")
        started = process_start_epoch(agent_pid)
        if (record and record.get("agent") == agent
                and record.get("kitty_start_ticks") == process_start_ticks(kitty_pid)
                and started is not None
                and isinstance(record.get("updated_at"), int)
                and record["updated_at"] >= started - 2):
            return record
    except (OSError, ValueError, AttributeError):
        pass
    return None


def session_id_for(
    agent: str,
    process: dict[str, Any],
    *,
    kitty_pid: int,
    kitty_window_id: int,
    title: str = "",
    cwd: str = "",
) -> tuple[str | None, str, str]:
    pid = int(process.get("pid") or 0)
    start_ticks = process_start_ticks(pid)
    argv = process_command(process)
    direct = session_id_from_resume_args(agent, argv)
    if direct:
        register_session_id(agent, pid, direct, start_ticks, "explicit-resume-arguments")
        return direct, "explicit-resume-arguments", "active"
    pane_record = pane_registry_record(agent, kitty_pid, kitty_window_id, pid)
    if pane_record:
        if pane_record.get("state") == "empty" and not pane_record.get("has_user_turn"):
            return None, str(pane_record.get("id_method") or "agent-session-start"), "empty"
        pane_id = pane_record.get("session_id")
        if valid_agent_session_id(agent, pane_id):
            return str(pane_id), str(pane_record.get("id_method") or "official-agent-hook"), "active"
        if pane_record.get("has_user_turn"):
            return None, str(pane_record.get("id_method") or "agent-session-id-missing"), "unresolved"
    try:
        registered = json.loads(AGENT_IDS_FILE.read_text()).get(str(pid), {})
        registered_id = registered.get("session_id") if registered.get("agent") == agent else None
        if (isinstance(registered_id, str) and UUID_RE.fullmatch(registered_id)
                and start_ticks and registered.get("start_ticks") == start_ticks):
            return registered_id, str(registered.get("id_method") or "process-session-registry"), "active"
    except (OSError, ValueError, AttributeError):
        pass
    targets = process_fd_targets(pid) + process_mapped_files(pid)
    if agent == "antigravity":
        for target in targets:
            normalized = target.removesuffix(" (deleted)")
            match = re.search(r"/(?:presence/([0-9a-f-]{36})\.lock|conversations/([0-9a-f-]{36})\.db(?:-shm|-wal)?)$", normalized)
            if not match:
                match = re.search(
                    r"/brain/([0-9a-f-]{36})/\.system_generated/logs/transcript\.jsonl$",
                    normalized,
                )
            if match:
                session_id = next((group for group in match.groups() if group), "")
                if UUID_RE.fullmatch(session_id):
                    register_session_id(agent, pid, session_id, start_ticks, "process-session-file")
                    return session_id, "process-session-file", "active"
        return None, "antigravity-session-file-unavailable", "unresolved"
    if agent == "claude-code":
        for target in targets:
            match = re.search(r"/projects/.*/([0-9a-f-]{36})\.jsonl(?: \(deleted\))?$", target)
            if match and UUID_RE.fullmatch(match.group(1)):
                register_session_id(agent, pid, match.group(1), start_ticks, "process-open-transcript")
                return match.group(1), "process-open-transcript", "active"
        return None, "claude-transcript-not-open", "unresolved"
    if agent == "codex":
        return None, "codex-session-hook-unavailable", "unresolved"
    return None, "adapter-not-installed", "unresolved"


def valid_agent_session_id(agent: str, session_id: Any) -> bool:
    if not isinstance(session_id, str) or not session_id or len(session_id) > 256:
        return False
    if any(ord(char) < 33 or ord(char) == 127 for char in session_id):
        return False
    if agent in {"codex", "antigravity"}:
        return bool(UUID_RE.fullmatch(session_id))
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", session_id))


def resume_command(agent: str, session_id: str) -> list[str] | None:
    if not valid_agent_session_id(agent, session_id):
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
        for tab_index, tab in enumerate(os_window.get("tabs", [])):
            for pane_index, window in enumerate(tab.get("windows", [])):
                proc = foreground_process(window)
                if not proc:
                    continue
                agent = detect_agent(process_command(proc))
                if not agent:
                    continue
                window_id = int(window["id"])
                session_id, method, state = session_id_for(
                    agent,
                    proc,
                    kitty_pid=kitty_pid,
                    kitty_window_id=window_id,
                    title=str(window.get("title") or ""),
                    cwd=str(window.get("cwd") or ""),
                )
                records[window_id] = {
                    "agent": agent,
                    "session_id": session_id,
                    "id_method": method,
                    "state": state,
                    "kitty_tab_index": tab_index,
                    "kitty_pane_index": pane_index,
                    "kitty_tab_title": str(tab.get("title") or ""),
                    "kitty_window_id": window_id,
                    "cwd": str(window.get("cwd") or ""),
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
            if command and record.get("state") == "active":
                payload["cmd_at_shell_startup"] = shlex.join(command)
            else:
                # Empty and unresolved agents must never open an arbitrary/latest chat.
                payload.pop("cmd_at_shell_startup", None)
            parts[token_index] = "kitty-unserialize-data=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            line = "launch " + " ".join(shlex.quote(token) for token in parts[1:])
            summary.append({k: record[k] for k in (
                "agent", "session_id", "id_method", "state", "kitty_tab_index",
                "kitty_pane_index", "kitty_tab_title", "kitty_window_id", "cwd",
            )})
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
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
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
        complete = len(found) == len(records) and all(
            record.get("state") == "empty"
            or (record.get("state") == "active" and valid_agent_session_id(record.get("agent", ""), record.get("session_id")))
            for record in found
        )
        if not complete:
            return "", "agent-id-incomplete"
        # Immutable content-addressed sessions keep the previous durable manifest
        # usable until the entire new snapshot has passed validation.
        digest = hashlib.sha256(rendered.encode()).hexdigest()[:16]
        name = f"KITTY-{pid}-{digest}.session"
        destination = STATE_DIR / name
        atomic_write(destination, rendered.encode(), 0o600)
        return name, "ok" if complete else "agent-id-incomplete"
    finally:
        temp.unlink(missing_ok=True)


def snapshot(*, allow_empty: bool = False, promote: bool = True) -> dict[str, Any]:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    live_clients = workspace_clients()
    kitty_pid_counts: dict[int, int] = {}
    for client in live_clients:
        if str(client.get("class") or "").lower() == "kitty":
            pid = int(client.get("pid") or 0)
            kitty_pid_counts[pid] = kitty_pid_counts.get(pid, 0) + 1
    for client in live_clients:
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
            if kitty_pid_counts.get(pid, 0) > 1:
                item.update({"kind": "kitty", "error": "shared-kitty-process"})
                warnings.append(f"kitty {pid}: várias janelas Hyprland compartilham o processo; associação por janela ainda não é segura")
                rows.append(item)
                continue
            try:
                tree = json.loads(kitty_call(pid, "ls").stdout)
                records = agent_records(pid, tree)
                filename, result = save_kitty_session(pid, records)
                item.update({"kind": "kitty", "session_file": filename, "agent_sessions": [
                    {k: v for k, v in record.items() if k in (
                        "agent", "session_id", "id_method", "state", "kitty_tab_index",
                        "kitty_pane_index", "kitty_tab_title", "kitty_window_id", "cwd",
                    )}
                    for record in records.values()
                ]})
                if result != "ok":
                    warnings.append(f"kitty {pid}: sessão Kitty não passou pela validação integral")
            except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
                item.update({"kind": "kitty", "error": type(error).__name__})
                warnings.append(f"kitty {pid}: captura nativa falhou ({type(error).__name__})")
        else:
            item["kind"] = "application"
            item["restore_command"] = application_command(item["class"])
            if not item["restore_command"]:
                warnings.append(f"aplicativo sem adaptador de restauração: {item['class'] or 'classe desconhecida'}")
        rows.append(item)
    state = {
        "schema": 1,
        "workspace": WORKSPACE_ID,
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "updated_at": int(time.time()),
        "windows": rows,
        "warnings": warnings,
        "complete": not warnings,
    }
    encoded = (json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    atomic_write(CAPTURE_FILE, encoded)
    # Keep the last complete state if any active agent ID or Kitty capture is uncertain.
    if promote and state["complete"] and (rows or allow_empty):
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
    # Switch first so Lua exec_cmd launches into the intended workspace.
    focus = run(["hyprctl", "dispatch", "hl.dsp.focus({workspace=1})"], check=False)
    if focus.returncode != 0 or "error" in focus.stdout.lower():
        raise RuntimeError(f"Não foi possível focar o Workspace 1: {focus.stdout.strip()} {focus.stderr.strip()}".strip())
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
        # Hyprland 0.55+ uses Lua dispatchers. The old `[workspace N] command`
        # syntax is parsed as invalid Lua and can report success without a window.
        lua_command = json.dumps(shlex.join(command), ensure_ascii=False)
        dispatcher = f"hl.dsp.exec_cmd({lua_command})"
        result = run(["hyprctl", "dispatch", dispatcher], check=False)
        output = (result.stdout + result.stderr).strip()
        if result.returncode == 0 and not output.lower().startswith("error") and "syntax error" not in output.lower():
            restored.append(str(item.get("class") or command[0]))
        else:
            raise RuntimeError(f"Falha ao iniciar {item.get('class') or command[0]} no Workspace 1: {output}")
    return restored


def restorable_window_count(state: dict[str, Any]) -> int:
    count = 0
    for item in state.get("windows", []):
        if item.get("kind") == "kitty":
            session = STATE_DIR / str(item.get("session_file", ""))
            count += int(session.is_file() and session.parent == STATE_DIR)
        else:
            command = item.get("restore_command")
            count += int(isinstance(command, list) and bool(command))
    return count


def restore_matches(expected: dict[str, Any], observed: dict[str, Any]) -> bool:
    """Require window classes and recorded active chat IDs to match before promotion."""
    expected_windows = expected.get("windows", [])
    observed_windows = observed.get("windows", [])
    if len(expected_windows) != len(observed_windows):
        return False
    expected_classes = sorted(str(item.get("class", "")).casefold() for item in expected_windows)
    observed_classes = sorted(str(item.get("class", "")).casefold() for item in observed_windows)
    if expected_classes != observed_classes:
        return False

    def active_sessions(state: dict[str, Any]) -> list[tuple[str, str, int, int, str]]:
        return sorted(
            (
                str(agent.get("agent", "")),
                str(agent.get("session_id", "")),
                int(agent.get("kitty_tab_index", -1)),
                int(agent.get("kitty_pane_index", -1)),
                str(agent.get("cwd", "")),
            )
            for window in state.get("windows", [])
            for agent in window.get("agent_sessions", [])
            if agent.get("state") == "active"
        )

    return active_sessions(expected) == active_sessions(observed)


def write_restore_status(status: str, message: str, **details: Any) -> None:
    record = {
        "updated_at": int(time.time()),
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "status": status,
        "message": message,
        **details,
    }
    atomic_write(RESTORE_STATUS_FILE, (json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())


def load_state() -> dict[str, Any] | None:
    try:
        state = json.loads(STATE_FILE.read_text())
        if (not isinstance(state, dict) or state.get("schema") != 1
                or state.get("workspace") != WORKSPACE_ID
                or state.get("complete") is not True
                or state.get("warnings") != []
                or not isinstance(state.get("windows"), list)):
            return None
        for item in state["windows"]:
            if not isinstance(item, dict):
                return None
            if item.get("kind") == "kitty":
                name = item.get("session_file")
                if not isinstance(name, str) or Path(name).name != name:
                    return None
                session = STATE_DIR / name
                if not session.is_file() or session.parent != STATE_DIR:
                    return None
                agents = item.get("agent_sessions")
                if not isinstance(agents, list):
                    return None
                for agent in agents:
                    if not isinstance(agent, dict):
                        return None
                    if agent.get("state") == "active" and not valid_agent_session_id(agent.get("agent", ""), agent.get("session_id")):
                        return None
                    if agent.get("state") not in {"active", "empty"}:
                        return None
                    if not isinstance(agent.get("kitty_tab_index"), int) or not isinstance(agent.get("kitty_pane_index"), int):
                        return None
            elif not (isinstance(item.get("restore_command"), list) and item["restore_command"]):
                return None
        return state
    except (OSError, ValueError, AttributeError):
        pass
    return None


def status() -> int:
    try:
        capture = json.loads(CAPTURE_FILE.read_text())
    except (OSError, ValueError):
        capture = None
    state = load_state()
    try:
        restore_status = json.loads(RESTORE_STATUS_FILE.read_text())
    except (OSError, ValueError):
        restore_status = None
    if not state:
        print("Não há snapshot completo e validado para restaurar.")
        if capture:
            print(f"Última tentativa: {len(capture.get('windows', []))} janela(s); completa={capture.get('complete', False)}.")
            for warning in capture.get("warnings", []):
                print("AVISO:", warning)
        if restore_status:
            print(f"Restauração: {restore_status.get('status', 'desconhecida')} — {restore_status.get('message', '')}")
        return 1
    sessions = [a for w in state.get("windows", []) for a in w.get("agent_sessions", [])]
    relevant = [a for a in sessions if a.get("state") != "empty"]
    known = sum(bool(a.get("session_id")) for a in relevant)
    empty = sum(a.get("state") == "empty" for a in sessions)
    label = "completa e validada"
    print(f"Workspace {WORKSPACE_ID}: captura {label}; {len(state.get('windows', []))} janelas; {known}/{len(relevant)} IDs ativos; {empty} aba(s) vazia(s) ignorada(s).")
    for agent in sorted({a.get("agent", "desconhecido") for a in sessions}):
        values = [a for a in sessions if a.get("agent") == agent and a.get("state") != "empty"]
        found = sum(bool(a.get("session_id")) for a in values)
        print(f"{agent}: {found}/{len(values)} IDs identificados")
    for warning in state.get("warnings", []):
        print("AVISO:", warning)
    if restore_status:
        print(f"Última restauração: {restore_status.get('status', 'desconhecida')} — {restore_status.get('message', '')}")
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
        restore_pending = False
        expected_windows = 0
        if previous and previous.get("boot_id") != current_boot and not live:
            expected_windows = restorable_window_count(previous)
            if expected_windows:
                try:
                    write_restore_status("iniciando", "Iniciando a restauração do Workspace 1.", expected_windows=expected_windows)
                    restore_pending = True
                    launched = restore(previous)
                    deadline = time.monotonic() + 90
                    while time.monotonic() < deadline:
                        live = workspace_clients()
                        if len(live) >= expected_windows:
                            candidate = snapshot(promote=False)
                            if candidate.get("complete") and restore_matches(previous, candidate):
                                atomic_write(STATE_FILE, (json.dumps(candidate, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
                                restore_pending = False
                                write_restore_status("concluida", "Janelas, aplicativos e IDs ativos conferidos.", expected_windows=expected_windows, launched=launched)
                                break
                        time.sleep(2)
                    if restore_pending:
                        snapshot(promote=False)
                        write_restore_status("incompleta", "As janelas ou IDs ativos não coincidiram com o snapshot salvo; o último estado válido foi preservado.", expected_windows=expected_windows, observed_windows=len(workspace_clients()), launched=launched)
                except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as error:
                    write_restore_status("falhou", f"{type(error).__name__}: {error}", expected_windows=expected_windows)
        elif live and previous and previous.get("boot_id") != current_boot:
            # Do not mistake a partial/default autostart layout for the restored one.
            snapshot(promote=False)
            write_restore_status("incompleta", "Já havia janelas no Workspace 1 no início; o snapshot anterior foi preservado para evitar duplicação ou perda.", expected_windows=restorable_window_count(previous), observed_windows=len(live))
            restore_pending = True
            expected_windows = restorable_window_count(previous)
        elif live:
            snapshot(promote=True)
        else:
            # An empty startup capture must not erase the previous boot's state.
            snapshot(promote=False)
            if not previous:
                write_restore_status("sem_snapshot_valido", "Nenhum snapshot íntegro disponível para iniciar a restauração.")
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
                    candidate = snapshot(promote=not restore_pending)
                    if restore_pending and len(current) >= expected_windows and candidate.get("complete") and previous and restore_matches(previous, candidate):
                        atomic_write(STATE_FILE, (json.dumps(candidate, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
                        restore_pending = False
                        write_restore_status("concluida", "Janelas, aplicativos e IDs ativos conferidos.", expected_windows=expected_windows, observed_windows=len(current))
                else:
                    empty_since = empty_since or time.monotonic()
                    if time.monotonic() - empty_since >= EMPTY_GRACE_SECONDS and not restore_pending:
                        snapshot(allow_empty=True, promote=not restore_pending)
            except (OSError, subprocess.SubprocessError, ValueError, KeyError) as error:
                write_restore_status("monitoramento_com_erro", f"{type(error).__name__}: {error}")
            time.sleep(POLL_SECONDS)
        try:
            if workspace_clients() and not restore_pending:
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
