import os
import re
import json
import sqlite3
import time
from kitty.fast_data_types import add_timer, remove_timer

from kitty.tab_bar import (
    DrawData,
    ExtraData,
    Screen,
    TabBarData,
    draw_tab_with_powerline,
    get_boss,
)

# Nerd Font glyphs & BRUNOMA TYPEFACE icons
ICON_WINDOWS = "\U000f0372"  # 󰍲 nf-md-microsoft_windows
ICON_CLAUDE = "\ue003"       # CLAUDE_LARANJA (U+E003 da BRUNOMA TYPEFACE)
ICON_CODEX = "\ue008"        # codex-light (U+E008 da BRUNOMA TYPEFACE)
ICON_AGY = "\ue001"          # AGY_COLOR (U+E001 da BRUNOMA TYPEFACE)
ICON_OPENAI = "\ue008"       # codex-light (U+E008 da BRUNOMA TYPEFACE)
ICON_TERMINAL = "\ue795"     #  nf-dev-terminal

# Ativação do ícone dinâmico por agente/modelo (False = ícone padrão , True = dinâmico 󰍲/✦/󰚩/󰘐)
USE_DYNAMIC_ICONS = False


AGY_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def clean_agent_topic(topic: str, max_chars: int = 40) -> str:
    if not topic:
        return "Chat"
    t = topic.strip()
    while t and (t[0] in AGY_FRAMES or t.startswith("✳️") or t.startswith("✦") or t.startswith("◈") or ("\ue000" <= t[0] <= "\ue00a")):
        if t.startswith("✳️"):
            t = t[2:].strip()
        else:
            t = t[1:].strip()
    t = re.sub(r'^(Antigravity|Codex|Claude|OpenAI)\s*:\s*', '', t, flags=re.IGNORECASE).strip()
    t = re.sub(r'\s*\|\s*[\w~./-]+$', '', t).strip()
    if len(t) > max_chars:
        return t[:max_chars].rstrip() + "..."
    return t


def animate_agy_titles(timer_id):
    """Atualiza a barra; o título externo agregado é responsabilidade do daemon."""
    boss = get_boss()
    if boss is None:
        return
    state = boss._windoc_agy_title_animation
    state["frame"] = (state["frame"] + 1) % len(AGY_FRAMES)
    now = time.monotonic()
    state["status_cache"] = {
        pid: cached for pid, cached in state["status_cache"].items()
        if now - cached[0] < 5
    }
    for tab_manager in tuple(boss.os_window_map.values()):
        tab_manager.mark_tab_bar_dirty()


def install_agy_title_animation():
    boss = get_boss()
    if boss is None:
        return
    previous = getattr(boss, "_windoc_agy_title_animation", None)
    if previous is not None:
        remove_timer(previous["timer"])
    state = {"frame": 0, "status_cache": {}}
    boss._windoc_agy_title_animation = state
    state["timer"] = add_timer(animate_agy_titles, 0.12, True)


def get_tab_process_info(tab_id: int):
    """Inspeciona o processo, linha de comando e PID da janela ativa da aba."""
    try:
        boss = get_boss()
        if not boss:
            return "", "", 0
        tab = boss.tab_for_id(tab_id)
        if not tab or not tab.active_window:
            return "", "", 0
        exe = tab.get_exe_of_active_window() or ""
        cmdline = ""
        pid = 0
        procs = tab.active_window.child.foreground_processes
        if procs:
            last_p = procs[-1]
            if last_p and last_p.get("cmdline"):
                cmdline = " ".join(last_p["cmdline"])
            pid = last_p.get("pid", 0) if last_p else 0
        return exe, cmdline, pid
    except Exception:
        return "", "", 0


def get_agy_conversation_title(pid: int) -> str | None:
    """Busca o título real da conversa do Antigravity examinando os fds abertos do processo."""
    if not pid:
        return None
    try:
        fd_dir = f"/proc/{pid}/fd"
        if not os.path.exists(fd_dir):
            return None
        db_path = "/home/brunoma/.gemini/antigravity-cli/conversation_summaries.db"
        if not os.path.exists(db_path):
            return None

        conv_id = None
        for link in os.listdir(fd_dir):
            try:
                target = os.readlink(os.path.join(fd_dir, link))
                if "/presence/" in target and target.endswith(".lock"):
                    conv_id = os.path.basename(target).replace(".lock", "")
                    break
                elif "/conversations/" in target and target.endswith(".db"):
                    conv_id = os.path.basename(target).replace(".db", "")
                    break
            except Exception:
                continue

        if conv_id:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=0.1)
            cur = conn.cursor()
            cur.execute("SELECT title FROM conversation_summaries WHERE conversation_id = ?", (conv_id,))
            row = cur.fetchone()
            conn.close()
            if row and row[0]:
                return row[0].strip()
    except Exception:
        pass
    return None


def is_agy_tab_running(tab: TabBarData) -> bool:
    """Consulta o estado da conversa associada a esta aba específica do Kitty."""
    boss = get_boss()
    if boss is None:
        return False
    try:
        state = boss._windoc_agy_title_animation
        exe, cmdline, pid = get_tab_process_info(tab.tab_id)
        if not pid:
            return False
        identity = f"{exe} {cmdline}".lower()
        if "agy" not in identity and "antigravity" not in identity:
            return False

        now = time.monotonic()
        cached = state["status_cache"].get(pid)
        if cached and now - cached[0] < 0.12:
            return cached[1]

        running = False
        fd_dir = f"/proc/{pid}/fd"
        db_path = "/home/brunoma/.gemini/antigravity-cli/conversation_summaries.db"
        if os.path.exists(fd_dir) and os.path.exists(db_path):
            conv_id = None
            for link in os.listdir(fd_dir):
                try:
                    target = os.readlink(os.path.join(fd_dir, link))
                    if "/presence/" in target and target.endswith(".lock"):
                        conv_id = os.path.basename(target)[:-5]
                        break
                    if "/conversations/" in target and target.endswith(".db"):
                        conv_id = os.path.basename(target)[:-3]
                        break
                except OSError:
                    continue
            if conv_id:
                with sqlite3.connect(
                    f"file:{db_path}?mode=ro", uri=True, timeout=0.1
                ) as conn:
                    row = conn.execute(
                        "SELECT status, not_fully_idle FROM conversation_summaries "
                        "WHERE conversation_id = ?",
                        (conv_id,),
                    ).fetchone()
                running = bool(row and (
                    row[0] == "CASCADE_RUN_STATUS_RUNNING" or row[1]
                ))

        state["status_cache"][pid] = (now, running)
        return running
    except Exception:
        return False


def get_codex_thread_title() -> str | None:
    """Busca o título do tópico ativo do Codex."""
    try:
        idx_file = "/home/brunoma/.codex/session_index.jsonl"
        if os.path.exists(idx_file):
            with open(idx_file, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
                if lines:
                    last_session = json.loads(lines[-1])
                    thread_name = last_session.get("thread_name")
                    if thread_name:
                        return thread_name.strip()
    except Exception:
        pass
    return None


def resolve_smart_session(tab: TabBarData) -> tuple[str, str]:
    """
    Resolve dinamicamente o ícone e o título real do chat ou da sessão.
    Retorna: (ícone, título_resolvido)
    """
    raw_title = tab.title or ""
    exe, cmdline, pid = get_tab_process_info(tab.tab_id)
    identity = f"{exe} {cmdline}".lower()
    is_agy_process = "agy" in identity or "antigravity" in identity
    # O daemon pode colocar o spinner agregado no título do Kitty para o
    # Hyprland; esse estado não deve vazar para a aba interna selecionada.
    if (is_agy_process and len(raw_title) > 2
            and raw_title[0] in AGY_FRAMES and raw_title[1].isspace()):
        raw_title = raw_title[2:].lstrip()

    t_lower = raw_title.lower()
    cmd_lower = cmdline.lower()
    exe_lower = exe.lower()

    # 1. Antigravity (agy)
    is_agy = (
        "agy" in exe_lower
        or any(arg == "agy" or arg.endswith("/agy") for arg in cmdline.split())
        or "antigravity" in cmd_lower
        or raw_title.strip() == "agy"
        or "antigravity" in t_lower
    )
    if is_agy:
        agy_title = get_agy_conversation_title(pid) or raw_title
        return ICON_AGY, clean_agent_topic(agy_title)

    # 2. Claude Code
    is_claude = (
        raw_title.startswith("\ue003")
        or raw_title.startswith("✳")
        or "claude" in exe_lower
        or "claude" in cmd_lower
        or "anthropic" in t_lower
    )
    if is_claude:
        topic = raw_title.lstrip("✳\ue003").strip()
        return ICON_CLAUDE, clean_agent_topic(topic or "Claude Code")

    # 3. Windows SSH / remote session (brunote)
    is_windows = (
        "conhost" in t_lower
        or "c:\\windows" in t_lower
        or "powershell" in t_lower
        or "cmd.exe" in t_lower
        or "brunote" in t_lower
        or "brunote" in cmd_lower
        or ("ssh" in cmd_lower and ("win" in cmd_lower or "10.0.0.128" in cmd_lower))
    )
    if is_windows:
        return ICON_WINDOWS, "Windows: brunote"

    # 4. Codex
    is_codex = (
        raw_title.startswith("\ue008")
        or "codex" in exe_lower
        or "codex" in cmd_lower
        or "codex" in t_lower
        or "| brunoma" in raw_title
    )
    if is_codex:
        clean = raw_title.replace("| brunoma", "").strip()
        codex_title = get_codex_thread_title() or clean
        return ICON_CODEX, clean_agent_topic(codex_title)

    # 5. OpenAI / Whisper
    is_openai = (
        raw_title.startswith("\ue008")
        or "openai" in t_lower
        or "chatgpt" in t_lower
        or "whisper" in t_lower
        or "gpt" in t_lower
    )
    if is_openai:
        clean = raw_title.lstrip("✳\ue008").strip()
        return ICON_OPENAI, clean_agent_topic(clean or "OpenAI")

    # 6. Terminal genérico (bash, zsh, utilitários CLI)
    clean = raw_title.strip()
    exe_base = os.path.basename(exe).lower() if exe else ""
    is_shell = exe_base in ("bash", "zsh", "fish", "sh", "systemd", "kitten", "")

    if not is_shell and exe_base:
        return ICON_TERMINAL, f"Terminal: {exe_base}"
    elif clean in ("~", "brunoma", "bash", "zsh", "fish", ""):
        return ICON_TERMINAL, "Terminal"
    return ICON_TERMINAL, f"Terminal: {clean}"


def draw_tab(
    draw_data: DrawData,
    screen: Screen,
    tab: TabBarData,
    before: int,
    max_tab_length: int,
    index: int,
    is_last: bool,
    extra_data: ExtraData,
) -> int:
    try:
        agent_icon, session_title = resolve_smart_session(tab)
        icon = agent_icon if USE_DYNAMIC_ICONS else ICON_TERMINAL
        if agent_icon == ICON_AGY and is_agy_tab_running(tab):
            state = get_boss()._windoc_agy_title_animation
            spinner = f"{AGY_FRAMES[state['frame']]} "
        else:
            spinner = ""
        if spinner:
            formatted_title = f"{icon} {spinner}{session_title}"
        else:
            formatted_title = f"{icon} {session_title}"

        new_tab = tab._replace(title=formatted_title)
        return draw_tab_with_powerline(
            draw_data, screen, new_tab, before, max_tab_length, index, is_last, extra_data
        )
    except Exception:
        return draw_tab_with_powerline(
            draw_data, screen, tab, before, max_tab_length, index, is_last, extra_data
        )


def draw_title(data: dict) -> str:
    """Fallback se {custom} for referenciado em tab_title_template."""
    try:
        return data.get("title", "")
    except Exception:
        return ""


install_agy_title_animation()
