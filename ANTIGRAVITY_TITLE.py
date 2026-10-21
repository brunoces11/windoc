"""Formata o título nativo do Antigravity; stdout contém somente o título."""

import json
import os
import re
import shlex
import sqlite3
import stat
import sys
import tempfile
import unicodedata
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


def record_active_session(payload):
    """Bind the callback's exact conversation ID to Kitty's window identity."""
    if not isinstance(payload, dict):
        return
    try:
        conversation_id = payload.get("conversation_id")
        transcript = None
        if isinstance(conversation_id, str) and conversation_id:
            transcript = str(
                Path.home() / ".gemini/antigravity-cli/brain" / conversation_id
                / ".system_generated/logs/transcript.jsonl"
            )
        active = payload.get("agent_state") in {
            "thinking", "working", "tool_use", "running", "busy"
        } or (isinstance(payload.get("task_count"), int) and payload.get("task_count", 0) > 0)
        sys.path.insert(0, str(Path(__file__).resolve().parent / "PERSISTIR_WORKSPACE"))
        from AGENT_SESSION_HOOK import record_session

        record_session(
            "antigravity",
            conversation_id,
            "TitleUpdate",
            transcript_path=transcript,
            user_turn=active,
            method="antigravity-native-title-payload",
        )
    except (ImportError, OSError, TypeError, ValueError):
        return


def format_title(payload):
    icon = "\ue001"  # AGY_COLOR (U+E001 da BRUNOMA TYPEFACE)
    if not isinstance(payload, dict):
        return f"{icon} Antigravity"
    record_active_session(payload)
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

    clean_topic = clean(topic, 105) if topic else (folder or "Chat")
    if len(clean_topic) > 40:
        clean_topic = clean_topic[:40].rstrip() + "..."

    marker = "◈" if payload.get("tool_confirmation_pending") is True else "⠋" if busy else ""
    if marker:
        return f"{icon} {marker} {clean_topic}"
    return f"{icon} {clean_topic}"


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
        title = "\ue001 Antigravity"
    print(title)


if __name__ == "__main__":
    main()
