#!/usr/bin/env python3
"""Persist workspace 1 using Hyprland IPC and Kitty's native session format.

Runtime snapshots are private and live in ESTADO_LOCAL, which is gitignored.
Agent adapters store immutable session IDs; titles are deliberately ignored.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from AGENT_SESSION_HOOK import transcript_has_user_message
import WORKSPACE_LAYOUT as layout
import WORKSPACE_GRID_EXPORTER as grid_exporter


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
if os.environ.get("WORKSPACE1_TEST_WORKSPACE") and os.environ.get("WORKSPACE1_STATE_DIR"):
    WORKSPACE_ID = int(os.environ["WORKSPACE1_TEST_WORKSPACE"])
RECONCILE_SECONDS = 60
DEBOUNCE_SECONDS = 30
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
    pane_record = pane_registry_record(agent, kitty_pid, kitty_window_id, pid)
    if pane_record:
        pane_id = pane_record.get("session_id")
        if not pane_record.get("has_user_turn"):
            evidence = transcript_has_user_message(pane_record.get("transcript_path"))
            if evidence is False and pane_record.get("state") == "empty":
                return None, str(pane_record.get("id_method") or "agent-session-start"), "empty"
            # Old 'empty' classifications must be rechecked against native history.
        if valid_agent_session_id(agent, pane_id):
            return str(pane_id), str(pane_record.get("id_method") or "official-agent-hook"), "active"
        if pane_record.get("has_user_turn"):
            return None, str(pane_record.get("id_method") or "agent-session-id-missing"), "unresolved"
    # A process can switch conversations without changing PID/start time. Cached
    # process IDs are diagnostic history, not evidence of the currently open chat.
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
        if direct:
            return direct, "explicit-resume-arguments", "active"
        return None, "antigravity-session-file-unavailable", "unresolved"
    if agent == "claude-code":
        for target in targets:
            match = re.search(r"/projects/.*/([0-9a-f-]{36})\.jsonl(?: \(deleted\))?$", target)
            if match and UUID_RE.fullmatch(match.group(1)):
                register_session_id(agent, pid, match.group(1), start_ticks, "process-open-transcript")
                return match.group(1), "process-open-transcript", "active"
        if direct:
            return direct, "explicit-resume-arguments", "active"
        return None, "claude-transcript-not-open", "unresolved"
    if agent == "codex":
        if direct:
            return direct, "explicit-resume-arguments", "active"
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
            # Native sessions can contain a direct `kitty -e agent` command after
            # the launch options. Always replace it too, including unknown IDs.
            first_command = next((i for i in range(1, len(parts))
                                  if i != token_index and not parts[i].startswith("--")), len(parts))
            parts = parts[:first_command]
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


def stored_session(text: str) -> str:
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    name = f"KITTY-{digest}.session"
    atomic_write(STATE_DIR / name, text.encode())
    return name


def save_kitty_session(pid: int, records: dict[int, dict[str, Any]]) -> tuple[str, str]:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".kitty-capture-", suffix=".session", dir=STATE_DIR)
    os.close(fd)
    temp = Path(temp_name)
    try:
        kitty_call(pid, "action", "save_as_session", "--save-only", "--use-foreground-process", str(temp))
        rendered, found = patch_native_session(temp.read_text(encoding="utf-8"), records)
        if len(found) != len(records):
            raise ValueError("A topologia mudou durante a captura nativa")
        # An unknown agent becomes a shell in its own pane; the other panes survive.
        return stored_session(rendered), "partial" if any(r["state"] == "unresolved" for r in found) else "ok"
    finally:
        temp.unlink(missing_ok=True)


def process_window_identity(pid: int) -> str | None:
    try:
        env = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
        for value in env:
            if value.startswith(b"WINDOC_WORKSPACE_WINDOW_ID="):
                identity = value.split(b"=", 1)[1].decode()
                if re.fullmatch(r"[a-f0-9]{24}", identity):
                    return identity
    except (OSError, UnicodeDecodeError):
        pass
    return None


def boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def window_identity(client: dict[str, Any]) -> str:
    inherited = process_window_identity(int(client.get("pid") or 0))
    if inherited:
        return inherited
    for tag in client.get("tags", []):
        match = re.fullmatch(r"windoc_ws_([a-f0-9]{24})", tag)
        if match:
            return match[1]
    key = f"{boot_id()}:{client.get('pid')}:{client.get('address')}"
    return hashlib.sha256(key.encode()).hexdigest()[:24]


def native_structure(tree: list[dict[str, Any]], records: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    tabs = []
    for os_window in tree:
        for tab in os_window.get("tabs", []):
            panes = []
            for window in tab.get("windows", []):
                proc = foreground_process(window) or {}
                rec = records.get(int(window["id"]), {})
                panes.append({
                    "cwd": str(proc.get("cwd") or window.get("cwd") or Path.home()),
                    "command": process_command(proc),
                    "agent": rec.get("agent"), "session_id": rec.get("session_id"),
                    "state": rec.get("state", "program"), "id_method": rec.get("id_method"),
                    "active": bool(window.get("is_active")),
                })
            tabs.append({"layout": tab.get("layout", "tall"), "panes": panes,
                         "active": bool(tab.get("is_active")), "layout_state": tab.get("layout_state")})
    return tabs


def shell_session(tabs: list[dict[str, Any]]) -> str:
    lines = []
    for tab in tabs or [{"panes": [{"cwd": str(Path.home())}]}]:
        lines.extend(["new_tab", "layout tall"])
        for pane in tab["panes"]:
            cwd = pane.get("cwd") or str(Path.home())
            # Session directives must not be injected via a path with newlines.
            if "\n" in cwd or "\r" in cwd or not Path(cwd).is_dir():
                cwd = str(Path.home())
            startup = resume_command(pane.get("agent", ""), pane.get("session_id") or "")
            payload = {"id": len(lines)}
            if startup and pane.get("state") == "active":
                payload["cmd_at_shell_startup"] = shlex.join(startup)
            lines.append("launch " + shlex.quote("kitty-unserialize-data=" + json.dumps(payload)) + " --cwd=" + shlex.quote(cwd))
    return "\n".join(lines) + "\n"


def application_command(app_class: str) -> list[str] | None:
    known = {"chromium": ["chromium"], "sublime_text": ["subl", "--launch-or-new-window"],
             "org.gnome.nautilus": ["nautilus"], "io.bassi.amberol": ["amberol"]}
    command = known.get(app_class.lower())
    return command if command and shutil.which(command[0]) else None


def scene_signature(state: dict[str, Any]) -> str:
    payload = {k: state.get(k) for k in ("schema", "workspace", "monitors", "groups", "tile_tree", "grid", "complete", "warnings")}
    payload["windows"] = sorted(state.get("windows", []), key=lambda w: w["restore_id"])
    return json.dumps(payload, sort_keys=True)


def promote_state(state: dict[str, Any]) -> None:
    old = load_state()
    state = preserve_unreadable_windows(preserve_restore_target(state), old)
    if old and scene_signature(old) == scene_signature(state):
        return
    if old and scene_signature(old) != scene_signature(state):
        atomic_write(STATE_DIR / "PREVIOUS_WORKSPACE1.json", (json.dumps(old, ensure_ascii=False, indent=2) + "\n").encode())
    data = (json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    atomic_write(STATE_FILE, data)
    if state.get("complete"):
        atomic_write(STATE_DIR / "LAST_COMPLETE.json", data)


def save_restore_guard(desired: dict[str, Any], observed: dict[str, Any], results: list[dict[str, Any]]) -> None:
    pending = {r["restore_id"]: r.get("verified", {}) for r in results if r["status"] != "verificado"}
    record = {"boot_id": boot_id(), "pending": pending, "desired": desired, "observed": observed}
    atomic_write(STATE_DIR / "RESTORE_GUARD.json", (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode())


def valid_native_layout_graph(state: dict[str, Any]) -> bool:
    grid = state.get("grid")
    if not isinstance(grid, dict):
        return False
    if grid.get("source") != "hyprland-native" or grid.get("layout") != "dwindle":
        return False
    groups = state.get("groups", [])
    tiled = {g.get("id") for g in groups if not g.get("floating")}
    members = [member for group in groups for member in group.get("members", [])]
    if len(members) != len(set(members)):
        return False
    leaves = set()
    def walk(node):
        if not isinstance(node, dict):
            return
        if "group" in node:
            leaves.add(node["group"])
            return
        walk(node.get("left"))
        walk(node.get("right"))
    walk(state.get("tile_tree"))
    if not tiled and grid.get("tiled_leaves") == 0:
        return state.get("tile_tree") is None
    return bool(tiled) and leaves == tiled and len(leaves) == grid.get("tiled_leaves")


def preserve_restore_target(state: dict[str, Any]) -> dict[str, Any]:
    try:
        guard = json.loads((STATE_DIR / "RESTORE_GUARD.json").read_text())
    except (OSError, ValueError):
        return state
    if guard.get("boot_id") != boot_id() or not guard.get("pending"):
        return state
    result = copy.deepcopy(state)
    desired_state = guard.get("desired", {})
    desired_grid = desired_state.get("grid") if isinstance(desired_state.get("grid"), dict) else {}
    current_grid = state.get("grid") if isinstance(state.get("grid"), dict) else {}
    desired_graph_valid = (valid_native_layout_graph(desired_state)
                           and desired_grid.get("build_id") == current_grid.get("build_id"))
    desired = {w["restore_id"]: w for w in desired_state.get("windows", [])}
    observed = {w["restore_id"]: w for w in guard["observed"]["windows"]}
    actual = {w["restore_id"]: w for w in result["windows"]}
    for identity, checks in list(guard["pending"].items()):
        target, initial, current = desired.get(identity), observed.get(identity), actual.get(identity)
        if not target:
            continue
        if not current:
            if not initial:
                result["windows"].append(copy.deepcopy(target))
            else:
                del guard["pending"][identity]  # A later real close replaces the old desired state.
                continue
        elif initial:
            geo = ("at", "size", "normal_at", "normal_size", "group_members", "group_active", "group_locked",
                   "floating", "fullscreen", "monitor_name", "monitor_area", "layout_name")
            if desired_graph_valid and (not checks.get("geometry") or not checks.get("group")):
                if all(current.get(k) == initial.get(k) for k in geo):
                    for key in geo:
                        if key in target:
                            current[key] = copy.deepcopy(target[key])
                else:
                    checks["geometry"] = checks["group"] = True
            elif not desired_graph_valid and not checks.get("geometry"):
                # Keep per-window measurements, but never import stale group edges
                # into a freshly captured native tree.
                geometry_only = ("at", "size", "normal_at", "normal_size", "floating", "fullscreen",
                                 "monitor_name", "monitor_area", "layout_name")
                if all(current.get(k) == initial.get(k) for k in geometry_only):
                    for key in geometry_only:
                        if key in target:
                            current[key] = copy.deepcopy(target[key])
                else:
                    checks["geometry"] = True
            if not checks.get("terminal"):
                def signature(window):
                    return [[pane_signature(p, expected=True) for p in t["panes"]] for t in window.get("tabs", [])]
                if signature(current) == signature(initial) and signature(current) != signature(target):
                    for key in ("tabs", "agent_sessions", "session_file", "native_layout", "native_fingerprint"):
                        if key in target:
                            current[key] = copy.deepcopy(target[key])
                else:
                    checks["terminal"] = True
            if checks.get("terminal") and checks.get("geometry") and checks.get("group"):
                del guard["pending"][identity]
                continue
        warning = f"{identity}: restauração pendente; dados desejados anteriores preservados"
        result.setdefault("warnings", []).append(warning)
        result["complete"] = False
    if guard.get("pending"):
        # The guard's desired graph is one internally consistent snapshot. Do
        # not rebuild group membership from a mix of old targets and live rows.
        if desired_graph_valid:
            for key in ("groups", "tile_tree", "grid", "layout_snapshot"):
                if key in desired_state:
                    result[key] = copy.deepcopy(desired_state[key])
    atomic_write(STATE_DIR / "RESTORE_GUARD.json", (json.dumps(guard, ensure_ascii=False, sort_keys=True) + "\n").encode())
    return result


def preserve_unreadable_windows(state: dict[str, Any], old: dict[str, Any] | None) -> dict[str, Any]:
    """Retain explicitly stale last-known data only for the same live Kitty."""
    if not old or state.get("boot_id") != old.get("boot_id"):
        return state
    previous = {w["restore_id"]: w for w in old.get("windows", [])}
    result = copy.deepcopy(state)
    for index, current in enumerate(result.get("windows", [])):
        prior = previous.get(current.get("restore_id"))
        if not (current.get("kind") == "kitty" and current.get("structure_available") is False
                and prior and prior.get("pid") == current.get("pid") and prior.get("native_layout")
                and current.get("pid_start_ticks")
                and prior.get("pid_start_ticks") == current["pid_start_ticks"]):
            continue
        saved = copy.deepcopy(prior)
        # Keep live compositor metadata; retain only the inaccessible terminal data.
        saved.update({k: v for k, v in current.items()
                      if k not in {"tabs", "agent_sessions", "session_file", "native_layout"}})
        saved["capture_stale"] = True
        saved["last_successful_capture_at"] = prior.get("last_successful_capture_at", old["updated_at"])
        warning = "Kitty inacessível: estrutura e chats da última leitura válida preservados; confirmação atual pendente"
        saved["warnings"].append(warning)
        result["windows"][index] = saved
        result.setdefault("warnings", []).append(f"{saved['restore_id']}: {warning}")
        result["complete"] = False
    return result


def terminal_fingerprint(tree: list[dict[str, Any]], records: dict[int, dict[str, Any]]) -> str:
    tabs = []
    for os_window in tree:
        for tab in os_window.get("tabs", []):
            panes = []
            for pane in tab.get("windows", []):
                panes.append({k: pane.get(k) for k in ("id", "cwd", "cmdline", "foreground_processes", "is_active")})
            tabs.append({"layout": tab.get("layout"), "state": tab.get("layout_state"),
                         "active": tab.get("is_active"), "title": tab.get("title") if tab.get("title_overridden") else None,
                         "panes": panes})
    ids = [{k: r.get(k) for k in ("agent", "session_id", "state", "id_method", "kitty_window_id", "pid")}
           for r in records.values()]
    return hashlib.sha256(json.dumps([tabs, ids], sort_keys=True).encode()).hexdigest()


def probe_scene(terminal_pids: set[int] | None = None) -> dict[str, Any]:
    live = workspace_clients()
    monitors = layout.monitor_records(hypr_json("monitors"))
    native = layout.metadata(sys.modules[__name__], live) if live else {}
    grid = grid_exporter.query(WORKSPACE_ID)
    terminals = {}
    for client in live:
        if str(client.get("class", "")).lower() != "kitty":
            continue
        pid = int(client["pid"])
        if terminal_pids is not None and pid not in terminal_pids:
            continue
        try:
            tree = json.loads(kitty_call(pid, "ls").stdout)
            if len(tree) != 1 or sum(c.get("pid") == pid for c in live) != 1:
                raise ValueError("Processo Kitty compartilhado: associação individual pendente")
            records = agent_records(pid, tree)
            terminals[pid] = {"tree": tree, "records": records, "fingerprint": terminal_fingerprint(tree, records)}
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
            terminals[pid] = {"error": str(error)}
    return {"clients": live, "monitors": monitors, "native": native, "grid": grid, "terminals": terminals}


def probe_signature(probe: dict[str, Any], previous: dict[str, Any] | None = None) -> str:
    cached = {int(w["pid"]): w.get("native_fingerprint") for w in (previous or {}).get("windows", []) if w.get("pid")}
    rows = []
    for c in probe["clients"]:
        row = {k: c.get(k) for k in ("address", "pid", "class", "at", "size", "floating", "fullscreen", "monitor", "grouped", "focusHistoryID")}
        t = probe["terminals"].get(int(c.get("pid") or 0), {})
        row["terminal"] = t.get("fingerprint", t.get("error", cached.get(int(c.get("pid") or 0))))
        rows.append(row)
    return json.dumps([sorted(rows, key=lambda r: r["address"]), probe["monitors"], probe["native"], probe.get("grid")], sort_keys=True)


def snapshot(*, allow_empty: bool = False, promote: bool = True, probe: dict[str, Any] | None = None) -> dict[str, Any]:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    previous = load_state(CAPTURE_FILE) or load_state()
    cached = {w["restore_id"]: w for w in (previous or {}).get("windows", [])}
    probe = probe or probe_scene()
    rows, warnings = [], []
    for client in probe["clients"]:
        item = {
            "restore_id": window_identity(client), "class": str(client.get("class") or ""),
            "address": client.get("address"), "pid": client.get("pid"),
            "pid_start_ticks": process_start_ticks(int(client.get("pid") or 0)),
            "at": client.get("at"), "size": client.get("size"),
            "floating": bool(client.get("floating")), "fullscreen": client.get("fullscreen", 0),
            "monitor": client.get("monitor"), "grouped": client.get("grouped", []),
            "focus_order": client.get("focusHistoryID"), "warnings": [],
        }
        old_geometry = cached.get(item["restore_id"], {})
        if item["fullscreen"]:
            item["normal_at"] = old_geometry.get("normal_at") or (old_geometry.get("at") if not old_geometry.get("fullscreen") else None)
            item["normal_size"] = old_geometry.get("normal_size") or (old_geometry.get("size") if not old_geometry.get("fullscreen") else None)
        else:
            item["normal_at"], item["normal_size"] = item["at"], item["size"]
        if item["class"].lower() == "kitty":
            item.update(kind="kitty", tabs=[], agent_sessions=[], structure_available=False)
            pid = int(client["pid"])
            data = probe["terminals"].get(pid)
            old = cached.get(item["restore_id"], {})
            if data is None and not old:
                extra = probe_scene({pid})
                data = extra["terminals"].get(pid)
            reusable = (old.get("pid_start_ticks") == item["pid_start_ticks"] and old.get("session_file")
                        and (STATE_DIR / old["session_file"]).is_file())
            if reusable and (data is None or (data.get("fingerprint") and data["fingerprint"] == old.get("native_fingerprint"))):
                for key in ("tabs", "agent_sessions", "session_file", "native_layout", "native_fingerprint", "structure_available", "warnings"):
                    if key in old:
                        item[key] = copy.deepcopy(old[key])
            else:
                try:
                    if not data or "error" in data:
                        raise ValueError((data or {}).get("error", "Leitura do Kitty pendente"))
                    records = data["records"]
                    item["tabs"] = native_structure(data["tree"], records)
                    item["agent_sessions"] = list(records.values())
                    item["structure_available"] = True
                    item["native_fingerprint"] = data["fingerprint"]
                    filename, result = save_kitty_session(pid, records)
                    item.update(session_file=filename, native_layout=True)
                    if result == "partial":
                        item["warnings"].append("Chat sem ID: sua aba voltará como terminal")
                except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
                    item["warnings"].append(f"Captura nativa indisponível: {error}")
                    item["native_layout"] = False
                    if not item["tabs"]:
                        item["tabs"] = [{"panes": [{"cwd": str(Path.home()), "command": [], "state": "unresolved"}]}]
                    item["session_file"] = stored_session(shell_session(item["tabs"]))
                    for tab in item["tabs"]:
                        for pane in tab["panes"]:
                            pane["restore_as_shell"] = not (pane.get("state") == "active" and valid_agent_session_id(pane.get("agent", ""), pane.get("session_id")))
            item["restorable"] = True
        else:
            item.update(kind="application", restore_command=application_command(item["class"]))
            item["restorable"] = bool(item["restore_command"])
            if not item["restorable"]:
                item["warnings"].append("Aplicativo sem comando de restauração conhecido")
        warnings.extend(f"{item['restore_id']}: {w}" for w in item["warnings"])
        rows.append(item)
    state = {"schema": 4, "workspace": WORKSPACE_ID, "boot_id": boot_id(),
             "updated_at": int(time.time()), "valid": True, "complete": not warnings,
             "windows": rows, "warnings": warnings, "monitors": probe["monitors"]}
    layout.enrich(state, probe["native"], probe.get("grid"))
    state["complete"] = not state["warnings"]
    old_capture = load_state(CAPTURE_FILE)
    if not old_capture or scene_signature(old_capture) != scene_signature(state):
        atomic_write(CAPTURE_FILE, (json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
    if promote and (rows or allow_empty):
        promote_state(state)
    return state


def load_state(path: Path | None = None) -> dict[str, Any] | None:
    if path is None:
        for candidate in (STATE_FILE, STATE_DIR / "PREVIOUS_WORKSPACE1.json", STATE_DIR / "LAST_COMPLETE.json"):
            loaded = load_state(candidate)
            if loaded is not None:
                return loaded
        return None
    try:
        state = json.loads(path.read_text())
        if (not isinstance(state, dict) or state.get("schema") not in {1, 2, 3, 4}
                or state.get("workspace") != WORKSPACE_ID or not isinstance(state.get("windows"), list)):
            return None
        if state["schema"] == 1 and not state.get("complete"):
            return None
        if not isinstance(state.get("updated_at"), int):
            return None
        if not isinstance(state.get("warnings", []), list):
            return None
        valid_items = []
        for index, item in enumerate(state["windows"]):
            if not isinstance(item, dict):
                state["complete"] = False
                continue
            if not re.fullmatch(r"[a-f0-9]{24}", str(item.get("restore_id", ""))):
                key = f"{state.get('boot_id')}:{index}:{item.get('session_file')}"
                item["restore_id"] = hashlib.sha256(key.encode()).hexdigest()[:24]
            if not isinstance(item.get("tabs", []), list) or any(
                not isinstance(t, dict) or not isinstance(t.get("panes"), list)
                or any(not isinstance(p, dict) for p in t["panes"]) for t in item.get("tabs", [])
            ):
                state["complete"] = False
                item["tabs"] = []
            if not isinstance(item.get("agent_sessions", []), list):
                item["agent_sessions"] = []
            valid_items.append(item)
        state["windows"] = valid_items
        return state
    except (OSError, ValueError, TypeError):
        return None


def restore_plan(state: dict[str, Any]) -> list[dict[str, Any]]:
    plan = []
    items = [w for w in state.get("windows", []) if isinstance(w, dict)]
    for item in sorted(items, key=lambda w: tuple(w.get("at") or [0, 0])):
        if not isinstance(item, dict):
            continue
        entry = {"restore_id": item["restore_id"], "class": item.get("class"),
                 "command": None, "warnings": list(item.get("warnings", [])), "item": item}
        if item.get("kind") == "kitty":
            name = item.get("session_file")
            if isinstance(name, str) and Path(name).name == name:
                path = STATE_DIR / name
                try:
                    if path.is_file() and not path.is_symlink():
                        expected = re.search(r"-([0-9a-f]{16})\.session$", name)
                        if expected and hashlib.sha256(path.read_bytes()).hexdigest()[:16] != expected[1]:
                            entry["warnings"].append("Arquivo de sessão não confere com seu hash")
                        else:
                            entry["command"] = ["env", f"WINDOC_WORKSPACE_WINDOW_ID={item['restore_id']}", "kitty", "--session", str(path)]
                except OSError as error:
                    entry["warnings"].append(f"Arquivo de sessão inacessível: {error}")
        elif item.get("kind") == "application":
            cmd = item.get("restore_command")
            if isinstance(cmd, list) and cmd and all(isinstance(s, str) and "\0" not in s for s in cmd):
                entry["command"] = cmd
        if not entry["command"]:
            entry["warnings"].append("Item ignorado: comando ou arquivo válido indisponível")
        plan.append(entry)
    return plan


def dispatch(expression: str) -> None:
    result = run(["hyprctl", "dispatch", expression], check=False)
    output = (result.stdout + result.stderr).strip()
    if result.returncode or re.search(r"(?i)\berror\b|syntax error", output):
        raise RuntimeError(output or "O Hyprland recusou a operação")


def associated_client(item: dict[str, Any], live: list[dict[str, Any]], source_boot: str) -> dict[str, Any] | None:
    for client in live:
        if window_identity(client) == item["restore_id"]:
            return client
        if source_boot == boot_id() and client.get("address") == item.get("address") and client.get("pid") == item.get("pid"):
            return client
    return None


def pane_signature(pane: dict[str, Any], *, expected: bool) -> tuple[Any, ...]:
    agent = pane.get("agent")
    sid = pane.get("session_id")
    if expected and (pane.get("state") in {"empty", "unresolved"} or pane.get("restore_as_shell")):
        agent, sid = None, None
    command = pane.get("command") or []
    program = Path(command[0]).name if command else "shell"
    if program in {"bash", "zsh", "fish", "sh", "dash"} or (expected and (pane.get("state") in {"empty", "unresolved"} or pane.get("restore_as_shell"))):
        program = "shell"
    if agent:
        program = agent
        if not expected and pane.get("id_method") == "explicit-resume-arguments":
            sid = "aguardando-confirmacao-nativa:" + str(sid)
    arguments = tuple(command[1:]) if not agent and program != "shell" else ()
    return (pane.get("cwd"), program, arguments, agent, sid)


def window_matches(expected: dict[str, Any], observed: dict[str, Any]) -> bool:
    if expected.get("class", "").lower() != observed.get("class", "").lower():
        return False
    if expected.get("kind") != "kitty":
        return True
    a, b = expected.get("tabs", []), observed.get("tabs", [])
    if not a or len(a) != len(b):
        return False
    return all(
        (not expected.get("native_layout") or x.get("layout") == y.get("layout"))
        and ("active" not in x or x["active"] == y.get("active"))
        and all("active" not in p or p["active"] == q.get("active") for p, q in zip(x["panes"], y["panes"]))
        and [pane_signature(p, expected=True) for p in x["panes"]]
        == [pane_signature(p, expected=False) for p in y["panes"]]
        for x, y in zip(a, b)
    )


def group_matches(item: dict[str, Any], actual: dict[str, Any], expected: dict[str, Any], observed: dict[str, Any]) -> bool:
    def members(window: dict[str, Any], scene: dict[str, Any]) -> list[str]:
        if "group_members" in window:
            return window["group_members"]
        identities = {w.get("address"): w["restore_id"] for w in scene.get("windows", [])}
        return [identities.get(address, "unknown:" + str(address)) for address in window.get("grouped", [])]
    return (members(item, expected) == members(actual, observed)
            and (not item.get("group_active") or item["group_active"] == actual.get("group_active"))
            and ("group_locked" not in item or item["group_locked"] == actual.get("group_locked")))


def restore_matches(expected: dict[str, Any], observed: dict[str, Any]) -> bool:
    actual = {w["restore_id"]: w for w in observed.get("windows", [])}
    return all(w["restore_id"] in actual and window_matches(w, actual[w["restore_id"]])
               and group_matches(w, actual[w["restore_id"]], expected, observed)
               and layout.matches(w, actual[w["restore_id"]], expected, observed)
               for w in expected.get("windows", []))


def write_restore_status(status: str, message: str, **details: Any) -> None:
    record = {"updated_at": int(time.time()), "boot_id": boot_id(), "status": status, "message": message, **details}
    atomic_write(RESTORE_STATUS_FILE, (json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())


def wait_for_hyprland(timeout: float = 45) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            clients()
            return
        except (OSError, subprocess.SubprocessError, ValueError):
            if time.monotonic() >= deadline:
                raise RuntimeError("Hyprland não ficou disponível dentro do prazo")
            time.sleep(1)


def restore(state: dict[str, Any], *, verify_seconds: float = 30) -> list[dict[str, Any]]:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE_DIR / "RESTORE.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Uma restauração já está em andamento.", file=sys.stderr)
            return []
        return restore_items(state, verify_seconds=verify_seconds)


def restore_items(state: dict[str, Any], *, verify_seconds: float = 30) -> list[dict[str, Any]]:
    wait_for_hyprland()
    plan = restore_plan(state)
    results = []
    recovery = STATE_DIR / "RECOVERY.json"
    recovery_bytes = (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode()
    digest = hashlib.sha256(recovery_bytes).hexdigest()[:16]
    atomic_write(STATE_DIR / f"RECOVERY-{digest}.json", recovery_bytes)
    atomic_write(recovery, recovery_bytes)
    for entry in plan:
        item = entry["item"]
        result = {"restore_id": entry["restore_id"], "class": entry["class"], "status": "pendente", "warnings": entry["warnings"]}
        results.append(result)
        try:
            live = clients()
            existing = associated_client(item, live, str(state.get("boot_id")))
            if existing:
                result.update(status="existente", action="existing", address=existing["address"])
                continue
            if not entry["command"]:
                result["status"] = "ignorado"
                continue
            command = json.dumps(shlex.join(entry["command"]), ensure_ascii=False)
            # Start isolated: groups and geometry are reconstructed only after opening.
            # Launch tiled by default. If exact layout reconstruction is unavailable,
            # Hyprland's native layout still presents the windows instead of stacking floats.
            dispatch(f'hl.dsp.exec_cmd({command}, {{workspace="{WORKSPACE_ID} silent", group="barred"}})')
            result.update(status="iniciado", action="launch")
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                now = clients()
                found = associated_client(item, now, "")
                if not found and item.get("kind") == "application":
                    new = [c for c in now if c["address"] not in {x["address"] for x in live} and c.get("class") == item.get("class")]
                    found = new[0] if len(new) == 1 else None
                if found:
                    selector = json.dumps("address:" + found["address"])
                    dispatch(f'hl.dsp.window.tag({{window={selector},tag="windoc_ws_{item["restore_id"]}"}})')
                    dispatch(f'hl.dsp.window.move({{window={selector},workspace="{WORKSPACE_ID}",follow=false}})')
                    result.update(status="aberto", address=found["address"])
                    break
                time.sleep(0.25)
            else:
                result.update(status="nao_confirmado", error="O comando foi enviado, mas a janela ainda não foi encontrada")
        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError, KeyError) as error:
            result.update(status="falhou", error=str(error))
        write_restore_status("em_andamento", "Restauração independente por janela.", items=results)
    existing_scene = snapshot(promote=False) if results and all(r.get("action") == "existing" for r in results) else None
    existing_by_id = {w["restore_id"]: w for w in (existing_scene or {}).get("windows", [])}
    layout_unchanged = existing_scene is not None and all(
        item["restore_id"] in existing_by_id
        and group_matches(item, existing_by_id[item["restore_id"]], state, existing_scene)
        and layout.matches(item, existing_by_id[item["restore_id"]], state, existing_scene)
        for item in state["windows"])
    layout_report = {"unchanged": True} if layout_unchanged else layout.restore(sys.modules[__name__], state)
    deadline = time.monotonic() + verify_seconds
    observed = None
    while results:
        try:
            observed = snapshot(promote=False)
        except (OSError, subprocess.SubprocessError, ValueError, KeyError) as error:
            write_restore_status("verificacao_pendente", str(error), items=results)
            if time.monotonic() >= deadline:
                break
            time.sleep(0.5)
            continue
        by_id = {w["restore_id"]: w for w in observed["windows"]}
        for entry, result in zip(plan, results):
            if result["status"] in {"falhou", "ignorado"}:
                continue
            actual = by_id.get(entry["restore_id"])
            if actual:
                checks = {"window": True, "terminal": window_matches(entry["item"], actual),
                          "group": group_matches(entry["item"], actual, state, observed),
                          "geometry": layout.matches(entry["item"], actual, state, observed)}
                result["verified"] = checks
                if all(checks.values()):
                    result["status"] = "verificado"
                    result.pop("error", None)
                elif checks["terminal"]:
                    result["status"] = "grupo_pendente"
                    result["error"] = "Grupo ou geometria ainda não coincide com a captura desejada"
        if all(r["status"] in {"verificado", "falhou", "ignorado", "grupo_pendente"} for r in results) or time.monotonic() >= deadline:
            break
        time.sleep(1)
    done = sum(r["status"] == "verificado" for r in results)
    complete = bool(results) and done == len(results) and bool(state.get("complete"))
    launched = sum(r.get("action") == "launch" for r in results)
    label = ("concluida" if launched else "conferida") if complete else "parcial"
    if observed:
        save_restore_guard(state, observed, results)
    write_restore_status(label, f"{done}/{len(results)} janela(s) verificadas; {launched} iniciada(s) nesta execução.", items=results,
                         layout=layout_report, capture_complete=bool(state.get("complete")), previous_boot=state.get("boot_id") != boot_id())
    return results


def scene_counts(state: dict[str, Any]) -> tuple[int, int, int]:
    windows = state.get("windows", [])
    return len(windows), sum(len(w.get("tabs", [])) for w in windows), sum(len(t["panes"]) for w in windows for t in w.get("tabs", []))


def status() -> int:
    capture, state = load_state(CAPTURE_FILE), load_state()
    for label, value in [("Captura atual", capture), ("Estado para restaurar", state)]:
        if not value:
            print(f"{label}: indisponível.")
            continue
        agents = [a for w in value["windows"] for a in w.get("agent_sessions", []) if a.get("state") != "empty"]
        ids = sum(bool(a.get("session_id")) for a in agents)
        windows, tabs, panes = scene_counts(value)
        ready = sum(bool(e["command"]) for e in restore_plan(value))
        age = max(0, int(time.time()) - value["updated_at"])
        print(f"{label}: {windows} janelas, {len(value.get('groups', []))} grupos, {tabs} abas, {panes} painéis; {ids}/{len(agents)} IDs; {ready} janelas restauráveis; última alteração salva há {age}s; detecção {'completa' if value.get('complete') else 'parcial'}.")
        grid = value.get("grid") if isinstance(value.get("grid"), dict) else {}
        print(f"  Grid: {grid.get('source', 'ausente')}, {grid.get('tiled_leaves', 0)} folhas e {grid.get('split_nodes', 0)} cortes; algoritmo {grid.get('layout', 'desconhecido')}.")
        for warning in value.get("warnings", []):
            print("  PENDÊNCIA:", warning)
    try:
        report = json.loads(RESTORE_STATUS_FILE.read_text())
        print(f"Último teste/restauração: {report['status']} — {report['message']}")
    except (OSError, ValueError, KeyError):
        print("Restauração ainda não validada nesta versão.")
    return 0 if state and any(e["command"] for e in restore_plan(state)) else 1


def shutting_down() -> bool:
    try:
        result = run(["busctl", "--system", "get-property", "org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "PreparingForShutdown"], timeout=2, check=False)
        if result.stdout.strip() == "b true":
            return True
        session = os.environ.get("XDG_SESSION_ID")
        if session:
            result = run(["loginctl", "show-session", session, "-p", "State", "--value"], timeout=2, check=False)
            return result.stdout.strip() == "closing"
    except (OSError, subprocess.SubprocessError):
        pass
    return False


def restoration_in_progress() -> bool:
    with (STATE_DIR / "RESTORE.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True


def login_loop() -> int:
    wait_for_hyprland()
    _, exporter_error = grid_exporter.ensure_loaded(STATE_DIR, WORKSPACE_ID)
    if exporter_error:
        write_restore_status("grid_exporter_unavailable", exporter_error)
    from INTERFACE_MONITOR import monitor
    return monitor(sys.modules[__name__])


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "status"
    if command == "snapshot":
        snapshot()
        return status()
    if command in {"restore", "plan"}:
        source = STATE_DIR / "RECOVERY.json" if "--recovery" in argv else None
        state = load_state(source)
        if not state:
            print("Estado local válido não encontrado.", file=sys.stderr)
            return 1
        if command == "plan":
            print(json.dumps([{k:v for k,v in e.items() if k != "item"} for e in restore_plan(state)], ensure_ascii=False, indent=2))
            return 0
        results = restore(state)
        return 0 if any(r["status"] == "verificado" for r in results) else 1
    if command == "login":
        return login_loop()
    if command == "status":
        return status()
    print("Uso: WORKSPACE1.py {status|snapshot|plan|restore [--recovery]|login}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
