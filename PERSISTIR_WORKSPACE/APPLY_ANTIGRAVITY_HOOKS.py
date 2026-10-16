#!/usr/bin/env python3
"""Apply the sanitized Antigravity CLI hook fragment to its private settings."""

from __future__ import annotations

import json
import os
import shlex
import stat
import tempfile
from pathlib import Path
from typing import Any


def hook_command() -> str:
    script = Path(__file__).resolve().parent / "AGENT_SESSION_HOOK.py"
    return "python3 " + shlex.quote(str(script)) + " antigravity"


def install() -> None:
    path = Path.home() / ".gemini/antigravity-cli/settings.json"
    if path.is_symlink():
        raise ValueError("settings.json is a symlink; inspect the private config link before applying")
    original = path.stat() if path.exists() else None
    settings: dict[str, Any] = json.loads(path.read_text()) if original else {}
    if not isinstance(settings, dict):
        raise ValueError("settings.json must contain an object")
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("settings.json hooks must contain an object")
    command = hook_command()
    config_name = "workspace-session-persistence"
    config = hooks.setdefault(config_name, {})
    if not isinstance(config, dict):
        raise ValueError(f"hooks.{config_name} must contain an object")
    for event in ("SessionStart", "PreInvocation"):
        handlers = config.setdefault(event, [])
        if not isinstance(handlers, list):
            raise ValueError(f"hooks.{config_name}.{event} must contain an array")
        if not any(isinstance(item, dict) and item.get("command") == command for item in handlers):
            handlers.append({"type": "command", "command": command})

    # Remove the flat event keys written by the first local prototype, but only
    # when each entry is exclusively that prototype's command.
    for event in ("SessionStart", "PreInvocation"):
        old = hooks.get(event)
        if old is None:
            continue
        if isinstance(old, list) and all(isinstance(item, dict) and item.get("command") == command for item in old):
            del hooks[event]
        else:
            raise ValueError(f"unexpected preexisting hooks.{event}; preserving it for manual merge")

    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".workspace-hooks-", delete=False) as out:
            temporary = Path(out.name)
            os.fchmod(out.fileno(), stat.S_IMODE(original.st_mode) if original else 0o600)
            json.dump(settings, out, ensure_ascii=False, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        current = path.stat() if path.exists() else None
        before = (original.st_ino, original.st_mtime_ns, original.st_size) if original else None
        now = (current.st_ino, current.st_mtime_ns, current.st_size) if current else None
        if now != before:
            raise ValueError("Antigravity settings changed while applying hooks; retry")
        os.replace(temporary, path)
        verified = json.loads(path.read_text())
        if verified != settings or path.is_symlink() or verified.get("title") != settings.get("title"):
            raise ValueError("Antigravity hook verification failed")
        for event in ("SessionStart", "PreInvocation"):
            if not any(item.get("command") == command for item in verified["hooks"][config_name][event]):
                raise ValueError(f"Antigravity {event} hook missing after write")
        print("[OK] Antigravity session hooks installed; existing title and preferences preserved.")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    install()
