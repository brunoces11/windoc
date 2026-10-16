#!/usr/bin/env python3
"""Merge workspace session capture into existing Codex and Claude hooks."""

from __future__ import annotations

import json
import os
import shlex
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
HOOK = Path(__file__).resolve().parent / "AGENT_SESSION_HOOK.py"


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    mode = path.stat().st_mode & 0o777
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    temporary = Path(name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def add_hook(groups: Any, command: str, *, matcher: str | None = None) -> list[dict[str, Any]]:
    if not isinstance(groups, list):
        raise ValueError("hooks event must be a JSON array")
    for group in groups:
        if not isinstance(group, dict):
            continue
        for hook in group.get("hooks", []):
            if isinstance(hook, dict) and hook.get("command") == command:
                return groups
    group: dict[str, Any] = {"hooks": [{"type": "command", "command": command}]}
    if matcher is not None:
        group["matcher"] = matcher
    return [*groups, group]


def merge(path: Path, agent: str, events: tuple[str, ...], *, claude: bool) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"config must be a regular adopted file: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"config root must be an object: {path}")
    hooks = value.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError(f"hooks must be an object: {path}")
    command = "python3 " + shlex.quote(str(HOOK)) + " " + agent
    for event in events:
        hooks[event] = add_hook(hooks.get(event, []), command, matcher=".*" if claude else None)
    atomic_json(path, value)
    verified = json.loads(path.read_text(encoding="utf-8"))
    for event in events:
        if not any(
            hook.get("command") == command
            for group in verified["hooks"][event]
            for hook in group.get("hooks", [])
            if isinstance(hook, dict)
        ):
            raise RuntimeError(f"hook verification failed for {path}:{event}")
    print(f"[OK] {agent} lifecycle hooks merged and verified ({', '.join(events)}).")


def main() -> int:
    merge(ROOT / "adotados/.codex/hooks.json", "codex", ("SessionStart", "UserPromptSubmit"), claude=False)
    merge(ROOT / "adotados/.claude/settings.json", "claude-code", ("SessionStart", "UserPromptSubmit"), claude=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
