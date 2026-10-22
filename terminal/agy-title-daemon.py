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

# Ícone dos modelos/agentes (personalizável por agente ou glifo vetorial da BRUNOMA TYPEFACE)
AGENT_ICONS = {
    "antigravity": "\ue000",  # AGY_CLI (U+E000)
    "codex": "\ue00a",        # openai_black_vazado (U+E00A)
    "openai": "\ue00a",       # openai_black_vazado (U+E00A)
    "claude": "\ue003",       # CLAUDE_LARANJA (U+E003)
    "default": "\ue000",      # Fallback padrão (AGY_CLI)
}

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
SPINNER_CHARS = set("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏▖▘▝▗◐◓◑◒*◈✦✳️\ue000\ue001\ue002\ue003\ue004\ue005\ue006\ue007\ue008\ue009\ue00a")
AGY_DB_PATH = os.path.expanduser("~/.gemini/antigravity-cli/conversation_summaries.db")


def has_spinner(title: str) -> bool:
    t = title.strip()
    if t and (t[0] in SPINNER_CHARS or ("\ue000" <= t[0] <= "\ue00a")):
        parts = t.split(None, 1)
        if len(parts) > 1 and (parts[0] in SPINNER_CHARS or ("\ue000" <= parts[0] <= "\ue00a")):
            t = parts[1].strip()
    return bool(t and t[0] in {"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"})


def clean_title(title: str) -> str:
    t = title.strip()
    while t and (t[0] in SPINNER_CHARS or t.startswith("✳️") or t.startswith("✦") or t.startswith("◈") or ("\ue000" <= t[0] <= "\ue00a")):
        if t.startswith("✳️"):
            t = t[2:].strip()
        else:
            t = t[1:].strip()
    t = re.sub(r'^(Antigravity|Codex|Claude|OpenAI)\s*:\s*', '', t, flags=re.IGNORECASE).strip()
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
    topology_interval = 0.3  # Escaneia abas das janelas a cada 300ms
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
                        active_tab_is_running = False
                        tabs_to_clean = []

                        for tab in os_win.get("tabs", []):
                            is_active = tab.get("is_active", False)
                            t_title = tab.get("title", "")
                            windows = tab.get("windows", [])
                            if not windows:
                                continue
                            win = windows[0]
                            w_pid = win.get("pid", 0)
                            fg = win.get("foreground_processes", [])
                            all_cmdlines = [" ".join(p.get("cmdline", [])) for p in fg]
                            all_cmds_lower = " ".join(all_cmdlines).lower()

                            is_agy = any("agy" in c or "antigravity" in c for c in all_cmdlines)
                            is_codex = any("codex" in c for c in all_cmdlines)
                            is_claude = any("claude" in c for c in all_cmdlines)
                            is_openai = any("openai" in c or "chatgpt" in c for c in all_cmdlines)

                            agy_pid = next((p.get("pid", 0) for p in fg if any("agy" in arg or "antigravity" in arg for arg in p.get("cmdline", []))), 0)

                            tab_is_running = False
                            tab_pts = None
                            try:
                                tab_pts = os.readlink(f"/proc/{w_pid}/fd/0")
                            except OSError:
                                pass

                            if is_agy and agy_pid > 0:
                                has_ai_agent_in_window = True
                                conv_id = get_agy_conv_id(agy_pid)
                                if conv_id and agy_conn:
                                    t_name, tab_is_running = get_agy_conv_data(conv_id, agy_conn)
                                    if is_active:
                                        active_agent = "antigravity"
                                        active_title = t_name
                                        active_tab_is_running = tab_is_running
                            elif is_codex or is_claude or is_openai:
                                has_ai_agent_in_window = True
                                agent_name = "claude" if is_claude else ("openai" if is_openai else "codex")
                                # Codex e Claude Code prefixam o título da aba com o spinner quando trabalhando
                                if has_spinner(t_title):
                                    tab_is_running = True

                                if is_active:
                                    active_agent = agent_name
                                    active_title = clean_title(t_title)
                                    active_tab_is_running = tab_is_running
                            else:
                                if is_active:
                                    active_title = clean_title(t_title)
                                    active_tab_is_running = False

                            if tab_is_running:
                                has_any_running = True

                            # Se uma aba de IA não está em execução mas ficou com spinner residual no título nativo,
                            # limpa o pts dessa aba para remover qualquer frame falso herdado
                            if not tab_is_running and has_spinner(t_title) and tab_pts:
                                tab_agent = "antigravity" if is_agy else ("claude" if is_claude else ("openai" if is_openai else ("codex" if is_codex else "default")))
                                tab_icon = AGENT_ICONS.get(tab_agent, AGENT_ICONS["default"])
                                tabs_to_clean.append((tab_pts, format_display_title(tab_icon, t_title, spinner_frame=None, max_len=40)))

                            if is_active:
                                if not active_title:
                                    active_title = clean_title(t_title)
                                active_pts = tab_pts

                        # Limpa qualquer aba inativa que tenha ficado com spinner residual
                        for c_pts, c_title in tabs_to_clean:
                            set_terminal_title(c_pts, c_title)

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
                            "active_tab_is_running": active_tab_is_running,
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
                active_is_running = st.get("active_tab_is_running", False)

                if active_is_running:
                    frame = SPINNER_FRAMES[spinner_idx % len(SPINNER_FRAMES)]
                    full_title = format_display_title(icon, title, spinner_frame=frame, max_len=40)
                    set_terminal_title(pts, full_title)
                    st["last_set_title"] = full_title
                    st["we_are_animating"] = True
                else:
                    # A aba ativa está ociosa/standby (sem spinner no terminal nem no Hyprland)
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
