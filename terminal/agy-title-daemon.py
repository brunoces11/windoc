#!/usr/bin/env python3
"""
Universal AI Tab Sync Daemon para Hyprland / Kitty.
Monitora e sincroniza o status de execução de todos os agentes de IA CLI
(Antigravity, Codex e Claude Code) nas abas do Kitty e do Hyprland.

Comportamento padrão garantido:
- Se QUALQUER aba interna do Kitty (ativa ou em segundo plano) estiver executando um
  processo de IA, a aba correspondente no Hyprland exibe o loader giratório (spinner).
- Se todos os processos daquela janela estiverem ociosos (idle), exibe o título limpo.
- Ao alternar abas no Kitty, a aba do Hyprland reflete o título da aba em foco.
- Consumo de CPU de ultra-baixo impacto (<0.05%) e zero forks desnecessários.
"""

import glob
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import time

# Ícone dos modelos/agentes (personalizável por agente ou glifo vetorial)
AGENT_ICONS = {
    "antigravity": "✳️",
    "codex": "✳️",
    "claude": "✳️",
    "default": "✳️",
}

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
SPINNER_CHARS = set("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏▖▘▝▗◐◓◑◒*◈✦✳️")
AGY_DB_PATH = os.path.expanduser("~/.gemini/antigravity-cli/conversation_summaries.db")


def has_spinner(title: str) -> bool:
    t = title.strip()
    return bool(t and t[0] in SPINNER_CHARS)


def clean_title(title: str) -> str:
    t = title.strip()
    while t and (t[0] in SPINNER_CHARS or t.startswith("✳️") or t.startswith("✦") or t.startswith("◈")):
        if t.startswith("✳️"):
            t = t[2:].strip()
        else:
            t = t[1:].strip()
    t = re.sub(r'^(Antigravity|Codex|Claude)\s*:\s*', '', t, flags=re.IGNORECASE).strip()
    t = re.sub(r'\s*\|\s*[\w~./-]+$', '', t).strip()
    return t


def format_display_title(icon: str, raw_title: str, spinner_frame: str | None = None, max_len: int = 40) -> str:
    clean = clean_title(raw_title)
    if not clean:
        clean = "Chat"
    if len(clean) > max_len:
        clean = clean[:max_len].rstrip() + "..."
    if spinner_frame:
        return f"{icon} {spinner_frame} {clean}"
    return f"{icon} {clean}"


def get_agy_conv_id(pid: int) -> str | None:
    """Busca o conversation_id examinando os descritores abertos do agy."""
    fd_dir = f"/proc/{pid}/fd"
    if not os.path.exists(fd_dir):
        return None
    try:
        for fd in os.listdir(fd_dir):
            try:
                target = os.readlink(os.path.join(fd_dir, fd))
                if "/presence/" in target and target.endswith(".lock"):
                    return os.path.basename(target)[:-5]
                elif "/conversations/" in target and target.endswith(".db"):
                    return os.path.basename(target)[:-3]
            except OSError:
                continue
    except OSError:
        pass
    return None


def get_agy_conv_data(conv_id: str, conn: sqlite3.Connection) -> tuple[str, bool]:
    """Consulta título e status da conversa do Antigravity em modo somente leitura."""
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT title, status, not_fully_idle FROM conversation_summaries WHERE conversation_id = ?",
            (conv_id,),
        )
        row = cur.fetchone()
        if row:
            title = row[0].strip() if row[0] else "Antigravity"
            is_running = (row[1] == "CASCADE_RUN_STATUS_RUNNING") or bool(row[2])
            return title, is_running
    except Exception:
        pass
    return "Antigravity", False


def set_terminal_title(pts_path: str, title: str):
    """Envia a sequência OSC 0 diretamente para o pts do terminal."""
    try:
        with open(pts_path, "w", encoding="utf-8") as f:
            f.write(f"\033]0;{title}\007")
            f.flush()
    except Exception:
        pass


def main():
    running = True

    def handle_exit(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, handle_exit)
    signal.signal(signal.SIGINT, handle_exit)

    agy_conn = None
    if os.path.exists(AGY_DB_PATH):
        try:
            agy_conn = sqlite3.connect(f"file:{AGY_DB_PATH}?mode=ro", uri=True, timeout=0.1)
        except Exception:
            agy_conn = None

    last_topology_scan = 0.0
    topology_interval = 1.0  # Escaneia abas das janelas a cada 1 segundo
    spinner_idx = 0

    # Estado por socket: {
    #   'active_pts': str,
    #   'active_title': str,
    #   'active_is_natively_spinning': bool,
    #   'has_any_running': bool,
    #   'last_set_title': str,
    #   'we_are_animating': bool
    # }
    window_states = {}

    try:
        while running:
            now = time.time()

            # 1. Escaneamento periódico das janelas Kitty e suas abas
            if now - last_topology_scan >= topology_interval:
                last_topology_scan = now

                if agy_conn is None and os.path.exists(AGY_DB_PATH):
                    try:
                        agy_conn = sqlite3.connect(f"file:{AGY_DB_PATH}?mode=ro", uri=True, timeout=0.1)
                    except Exception:
                        agy_conn = None

                runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000")
                sockets = glob.glob(f"{runtime_dir}/omarchy-kitty-*")
                active_sockets = set()

                for sock in sockets:
                    active_sockets.add(sock)
                    try:
                        raw = subprocess.check_output(
                            ["kitty", "@", "--to", f"unix:{sock}", "ls"],
                            timeout=0.35,
                            stderr=subprocess.DEVNULL,
                        )
                        kdata = json.loads(raw)
                    except Exception:
                        continue

                    for os_win in kdata:
                        has_ai_agent_in_window = False
                        has_any_running = False
                        active_pts = None
                        active_title = ""
                        active_agent = "default"
                        active_is_natively_spinning = False

                        for tab in os_win.get("tabs", []):
                            is_active = tab.get("is_active", False)
                            t_title = tab.get("title", "")
                            windows = tab.get("windows", [])
                            if not windows:
                                continue
                            win = windows[0]
                            w_pid = win.get("pid", 0)
                            fg = win.get("foreground_processes", [])
                            fg_cmd = " ".join(fg[0]["cmdline"]) if fg else ""
                            fg_pid = fg[0].get("pid", 0) if fg else 0

                            cmd_lower = fg_cmd.lower()
                            is_agy = "agy" in cmd_lower or (fg_cmd == "agy")
                            is_codex = "codex" in cmd_lower
                            is_claude = "claude" in cmd_lower

                            tab_is_running = False

                            if is_agy and fg_pid > 0:
                                has_ai_agent_in_window = True
                                conv_id = get_agy_conv_id(fg_pid)
                                if conv_id and agy_conn:
                                    t_name, tab_is_running = get_agy_conv_data(conv_id, agy_conn)
                                    if is_active:
                                        active_agent = "antigravity"
                                        active_title = t_name
                            elif is_codex or is_claude:
                                has_ai_agent_in_window = True
                                agent_name = "codex" if is_codex else "claude"
                                # Codex e Claude Code prefixam o título da aba com o spinner quando trabalhando
                                if has_spinner(t_title):
                                    tab_is_running = True
                                    if is_active:
                                        active_is_natively_spinning = True

                                if is_active:
                                    active_agent = agent_name
                                    active_title = clean_title(t_title)

                            if tab_is_running:
                                has_any_running = True

                            if is_active:
                                if not active_title:
                                    active_title = clean_title(t_title)
                                try:
                                    active_pts = os.readlink(f"/proc/{w_pid}/fd/0")
                                except OSError:
                                    pass

                        # Se esta janela Kitty não possui nenhum agente de IA (ex: terminal bash puro), ignora
                        if not has_ai_agent_in_window:
                            if sock in window_states:
                                del window_states[sock]
                            continue

                        prev = window_states.get(sock, {})
                        window_states[sock] = {
                            "active_pts": active_pts,
                            "active_title": active_title or "Chat",
                            "active_agent": active_agent if active_title else prev.get("active_agent", "default"),
                            "active_is_natively_spinning": active_is_natively_spinning,
                            "has_any_running": has_any_running,
                            "last_set_title": prev.get("last_set_title", ""),
                            "we_are_animating": prev.get("we_are_animating", False),
                        }

                # Limpeza de sockets encerrados
                for dead_sock in list(window_states.keys()):
                    if dead_sock not in active_sockets:
                        del window_states[dead_sock]

            # 2. Atualização suave dos frames do título (a cada 80ms)
            for sock, st in list(window_states.items()):
                pts = st.get("active_pts")
                if not pts or not os.path.exists(pts):
                    continue

                title = st.get("active_title", "Chat")
                agent = st.get("active_agent", "default")
                icon = AGENT_ICONS.get(agent, AGENT_ICONS["default"])
                has_running = st.get("has_any_running", False)

                if has_running:
                    frame = SPINNER_FRAMES[spinner_idx % len(SPINNER_FRAMES)]
                    full_title = format_display_title(icon, title, spinner_frame=frame, max_len=40)
                    set_terminal_title(pts, full_title)
                    st["last_set_title"] = full_title
                    st["we_are_animating"] = True
                else:
                    # Todos os processos da janela estão ociosos
                    idle_title = format_display_title(icon, title, spinner_frame=None, max_len=40)
                    if st.get("we_are_animating") or st.get("last_set_title") != idle_title:
                        set_terminal_title(pts, idle_title)
                        st["last_set_title"] = idle_title
                        st["we_are_animating"] = False

            spinner_idx += 1
            time.sleep(0.08)

    finally:
        for sock, st in window_states.items():
            pts = st.get("active_pts")
            if pts and os.path.exists(pts):
                title = st.get("active_title", "Chat")
                agent = st.get("active_agent", "default")
                icon = AGENT_ICONS.get(agent, AGENT_ICONS["default"])
                idle_title = format_display_title(icon, title, spinner_frame=None, max_len=40)
                set_terminal_title(pts, idle_title)

        if agy_conn:
            try:
                agy_conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
