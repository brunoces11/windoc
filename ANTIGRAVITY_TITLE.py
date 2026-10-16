"""Formata o título nativo do Antigravity; stdout contém somente o título."""

import json
import fcntl
import os
import re
import shlex
import sqlite3
import stat
import sys
import tempfile
import unicodedata
import time
from contextlib import closing
from pathlib import Path


def clean(value, limit):
    if not isinstance(value, str):
        return ""
    printable = "".join(c if not unicodedata.category(c).startswith("C") else " " for c in value)
    return " ".join(printable.split())[:limit]


def conversation_title(conversation_id):
    if not isinstance(conversation_id, str) or not conversation_id:
        return ""
    database = Path.home() / ".gemini/antigravity-cli/conversation_summaries.db"
    try:
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0.025)) as conn:
            row = conn.execute(
                "SELECT title FROM conversation_summaries WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        return clean(row[0], 105) if row else ""
    except (sqlite3.Error, OSError, ValueError):
        return ""


def record_active_session(conversation_id):
    """Record the exact conversation ID against its owning agy process."""
    if not isinstance(conversation_id, str) or not re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", conversation_id
    ):
        return
    pid = os.getppid()
    agent_pid = None
    agent_start_ticks = None
    for _ in range(8):
        try:
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").lower()
            stat = Path(f"/proc/{pid}/stat").read_text()
            stat_fields = stat[stat.rfind(")") + 2 :].split()
            parent = int(stat_fields[1])
        except (OSError, ValueError, IndexError):
            break
        tokens = cmdline.decode(errors="ignore").split()
        names = {Path(token.strip("'\"")).name.lower() for token in tokens}
        if "agy" in names or "antigravity" in names:
            agent_pid = pid
            agent_start_ticks = stat_fields[19] if len(stat_fields) > 19 else None
            break
        if parent <= 1 or parent == pid:
            break
        pid = parent
    if not agent_pid:
        return

    state_dir = Path(__file__).resolve().parent / "PERSISTIR_WORKSPACE" / "ESTADO_LOCAL"
    registry = state_dir / "AGENT_IDS.json"
    try:
        state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (state_dir / "AGENT_IDS.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            current = json.loads(registry.read_text()) if registry.exists() else {}
            current[str(agent_pid)] = {
                "agent": "antigravity",
                "session_id": conversation_id,
                "start_ticks": agent_start_ticks,
                "id_method": "agent-native-session-callback",
                "updated_at": int(time.time()),
            }
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", dir=state_dir, prefix=".agent-ids-", delete=False) as out:
                    temporary = Path(out.name)
                    os.fchmod(out.fileno(), 0o600)
                    json.dump(current, out, ensure_ascii=False, sort_keys=True)
                    out.write("\n")
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(temporary, registry)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
    except (OSError, ValueError, TypeError):
        return


def format_title(payload):
    if not isinstance(payload, dict):
        return "✦ Antigravity"
    record_active_session(payload.get("conversation_id"))
    topic = conversation_title(payload.get("conversation_id"))
    cwd = payload.get("cwd")
    workspace = payload.get("workspace")
    if isinstance(workspace, dict):
        cwd = workspace.get("current_dir") or cwd
    folder = clean(Path(cwd).name, 32) if isinstance(cwd, str) and cwd else ""
    tasks = payload.get("task_count", 0)
    busy = payload.get("agent_state") in (
        "thinking", "working", "tool_use", "initializing", "authenticating", "running", "busy"
    ) or (isinstance(tasks, int) and tasks > 0)
    marker = "◈" if payload.get("tool_confirmation_pending") is True else "⠋" if busy else "✦"
    title = f"{marker} Antigravity"
    if topic:
        title += f": {topic}"
    if folder:
        title += f" | {folder}"
    return title


def install():
    """Mescla somente title; o app substitui symlinks ao salvar preferências.

    Exceção WINDOC_ADOPT_RULES: settings.json permanece físico e privado.
    Este procedimento e o bloco sanitizado abaixo permitem sua restauração.
    """
    path = Path.home() / ".gemini/antigravity-cli/settings.json"
    if path.is_symlink():
        raise ValueError("settings.json é um symlink; revise o vínculo antes de aplicar")
    path.parent.mkdir(parents=True, exist_ok=True)
    original_stat = path.stat() if path.exists() else None
    settings = json.loads(path.read_text()) if original_stat else {}
    if not isinstance(settings, dict):
        raise ValueError("settings.json deve conter um objeto JSON")
    # Caminho calculado na restauração, sem fixar o nome do usuário.
    wanted = {"type": "command", "command": "python3 " + shlex.quote(str(Path(__file__).resolve())), "enabled": True}
    if settings.get("title") == wanted:
        print("[OK] Título do Antigravity já configurado e validado.")
        return
    updated = dict(settings, title=wanted)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".windoc-title-", delete=False) as out:
            temporary = Path(out.name)
            os.fchmod(out.fileno(), stat.S_IMODE(original_stat.st_mode) if original_stat else 0o600)
            json.dump(updated, out, ensure_ascii=False, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        current_stat = path.stat() if path.exists() else None
        original_version = (original_stat.st_ino, original_stat.st_mtime_ns, original_stat.st_size) if original_stat else None
        current_version = (current_stat.st_ino, current_stat.st_mtime_ns, current_stat.st_size) if current_stat else None
        if current_version != original_version:
            raise ValueError("settings.json mudou durante a aplicação; tente novamente")
        os.replace(temporary, path)
        if json.loads(path.read_text()) != updated or path.is_symlink():
            raise ValueError("a verificação da configuração aplicada falhou")
        print("[OK] Título do Antigravity configurado; demais preferências preservadas.")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    if sys.argv[1:] == ["--install"]:
        try:
            install()
        except (OSError, ValueError) as error:
            print(f"[ERRO] {error}", file=sys.stderr)
            raise SystemExit(1)
        return
    try:
        payload = json.load(sys.stdin)
        title = format_title(payload)
    except (ValueError, TypeError, OSError):
        title = "✦ Antigravity"
    print(title)


if __name__ == "__main__":
    main()
