#!/usr/bin/env python3
"""Record official agent lifecycle IDs against the exact Kitty pane."""

from __future__ import annotations

import fcntl
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("WORKSPACE1_STATE_DIR", ROOT / "ESTADO_LOCAL"))
REGISTRY = STATE_DIR / "AGENT_IDS.json"
AGENT_ALIASES = {"codex": "codex", "claude-code": "claude-code", "antigravity": "antigravity"}
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")


def valid_session_id(value: Any) -> bool:
    return isinstance(value, str) and bool(SESSION_ID_RE.fullmatch(value))


def process_start_ticks(pid: int) -> str | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[19]
    except (OSError, IndexError):
        return None


def transcript_has_user_message(value: Any) -> bool | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value).expanduser()
    try:
        if not path.is_file():
            return None
        with path.open("rb") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(row, dict):
                    continue
                message = row.get("message")
                if row.get("type") in {"user", "human"}:
                    return True
                if isinstance(message, dict) and message.get("role") in {"user", "human"}:
                    return True
                if row.get("role") in {"user", "human"}:
                    return True
        return False
    except OSError:
        return None


def pane_key(kitty_pid: int, kitty_window_id: int) -> str:
    return f"kitty:{kitty_pid}:{kitty_window_id}"


def record_session(
    agent: str,
    session_id: Any,
    event: str,
    *,
    transcript_path: Any = None,
    user_turn: bool = False,
    empty_event: bool = False,
    source: Any = None,
    method: str = "official-agent-hook",
) -> bool:
    agent = AGENT_ALIASES.get(agent, "")
    try:
        kitty_pid = int(os.environ.get("KITTY_PID", "0"))
        kitty_window_id = int(os.environ.get("KITTY_WINDOW_ID", "0"))
    except ValueError:
        return False
    kitty_start = process_start_ticks(kitty_pid)
    if not agent or kitty_pid <= 1 or kitty_window_id <= 0 or not kitty_start:
        return False

    if agent == "antigravity" and not transcript_path and valid_session_id(session_id):
        transcript_path = str(
            Path.home() / ".gemini/antigravity-cli/brain" / session_id
            / ".system_generated/logs/transcript.jsonl"
        )
    source_name = source if isinstance(source, str) else ""
    # A prompt/tool event is positive evidence already; avoid rescanning a
    # potentially large transcript on every interaction.
    transcript_has_user = (
        None if user_turn or source_name == "clear"
        else transcript_has_user_message(transcript_path)
    )
    key = pane_key(kitty_pid, kitty_window_id)
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE_DIR / "AGENT_IDS.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            registry = json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}
        except (OSError, ValueError):
            registry = {}
        if not isinstance(registry, dict):
            registry = {}
        old = registry.get(key, {})
        if not isinstance(old, dict):
            old = {}
        same = valid_session_id(session_id) and old.get("agent") == agent and old.get("session_id") == session_id
        prior_has_user = same and source_name != "clear" and old.get("has_user_turn") is True
        has_user_turn = bool(
            user_turn or source_name in {"resume", "fork", "compact"}
            or (source_name != "clear" and transcript_has_user is True) or prior_has_user
        )
        if has_user_turn:
            state = "active"
        elif empty_event or source_name in {"startup", "clear"} or transcript_has_user is False:
            state = "empty"
        else:
            state = "unresolved"
        record = {
            "agent": agent,
            "session_id": session_id if valid_session_id(session_id) else None,
            "has_user_turn": has_user_turn,
            "state": state,
            "source_event": event,
            "source": source,
            "id_method": method,
            "transcript_path": str(transcript_path) if transcript_path else None,
            "kitty_pid": kitty_pid,
            "kitty_start_ticks": kitty_start,
            "kitty_window_id": kitty_window_id,
            "updated_at": int(time.time()),
        }
        registry[key] = record
        fd, name = tempfile.mkstemp(prefix=".agent-ids-", dir=STATE_DIR)
        temp = Path(name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(registry, stream, ensure_ascii=False, sort_keys=True, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, REGISTRY)
        finally:
            temp.unlink(missing_ok=True)
    return True


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in AGENT_ALIASES:
        return 2
    agent = argv[1]
    try:
        event_data = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if not isinstance(event_data, dict):
        return 0
    event = str(event_data.get("hook_event_name") or event_data.get("event") or "")
    if agent == "antigravity":
        session_id = event_data.get("conversationId") or event_data.get("conversation_id")
        transcript_path = event_data.get("transcriptPath") or event_data.get("transcript_path")
        active_event = event in {"PreInvocation", "PreToolUse", "PostToolUse", "Stop", "TitleUpdate"}
        empty_event = False
    else:
        session_id = event_data.get("session_id")
        transcript_path = event_data.get("transcript_path")
        active_event = event in {"UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"}
        source = event_data.get("source")
        empty_event = event == "SessionStart" and isinstance(source, str) and source in {"startup", "clear"}
    record_session(
        agent,
        session_id,
        event,
        transcript_path=transcript_path,
        user_turn=active_event,
        empty_event=empty_event,
        source=event_data.get("source"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
