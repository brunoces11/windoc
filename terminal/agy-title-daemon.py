#!/usr/bin/env python3
"""
Antigravity Hyprland Tab Sync Daemon (Versão Otimizada).
Sincroniza o título e a animação do loader do Antigravity na barra de abas do Hyprland
para cada janela do Kitty, mesmo com múltiplas abas abertas na mesma janela.
Design de ultra-baixo consumo de CPU (<0.05%) e zero forks desnecessários.
"""

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
DB_PATH = os.path.expanduser("~/.gemini/antigravity-cli/conversation_summaries.db")


def get_conversation_data(conv_id: str, conn: sqlite3.Connection) -> tuple[str, bool]:
    """Consulta título e status da conversa em modo somente leitura."""
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


def get_conv_id_from_pid(pid: int) -> str | None:
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

    sqlite_conn = None
    if os.path.exists(DB_PATH):
        try:
            sqlite_conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=0.1)
        except Exception:
            sqlite_conn = None

    last_proc_scan = 0.0
    last_tab_scan = 0.0
    spinner_idx = 0

    # Estruturas em cache:
    # agy_sessions: {agy_pid: {'shell_pid': int, 'kitty_pid': int, 'tty': str, 'conv_id': str, 'cwd': str, 'title': str, 'is_running': bool}}
    agy_sessions = {}
    # active_pts_by_kitty: {kitty_pid: {'active_pts': str, 'active_title': str, 'cwd': str, 'has_running': bool, 'last_title': str}}
    kitty_window_states = {}

    try:
        while running:
            now = time.time()

            # 1. Escaneamento ultra-rápido do /proc e SQLite (a cada 0.8s) - Zero forks de processos
            if now - last_proc_scan >= 0.8:
                last_proc_scan = now

                if sqlite_conn is None and os.path.exists(DB_PATH):
                    try:
                        sqlite_conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=0.1)
                    except Exception:
                        sqlite_conn = None

                current_pids = set()
                kitty_to_agy = {}  # kitty_pid -> list of session dicts

                try:
                    for entry in os.listdir("/proc"):
                        if not entry.isdigit():
                            continue
                        pid = int(entry)
                        cmd_file = f"/proc/{pid}/cmdline"
                        if not os.path.exists(cmd_file):
                            continue
                        try:
                            with open(cmd_file, "rb") as cf:
                                if b"agy" not in cf.read():
                                    continue
                        except OSError:
                            continue

                        # Descobre PPID (shell)
                        try:
                            with open(f"/proc/{pid}/stat", "r") as sf:
                                ppid = int(sf.read().split()[3])
                        except OSError:
                            continue

                        # Descobre TTY
                        try:
                            tty = os.readlink(f"/proc/{pid}/fd/0")
                        except OSError:
                            continue
                        if not tty.startswith("/dev/pts/"):
                            continue

                        # Descobre Kitty PID (pai do shell)
                        kitty_pid = 0
                        try:
                            with open(f"/proc/{ppid}/stat", "r") as kf:
                                kitty_pid = int(kf.read().split()[3])
                        except OSError:
                            continue

                        # Descobre conversation_id
                        conv_id = get_conv_id_from_pid(pid)
                        title, is_running = ("Antigravity", False)
                        if conv_id and sqlite_conn:
                            title, is_running = get_conversation_data(conv_id, sqlite_conn)

                        # CWD amigável
                        cwd_name = "~"
                        try:
                            cwd = os.readlink(f"/proc/{pid}/cwd")
                            cwd_name = os.path.basename(cwd) or "~"
                        except OSError:
                            pass

                        sess = {
                            "pid": pid,
                            "shell_pid": ppid,
                            "kitty_pid": kitty_pid,
                            "tty": tty,
                            "conv_id": conv_id,
                            "cwd": cwd_name,
                            "title": title,
                            "is_running": is_running,
                        }
                        current_pids.add(pid)
                        agy_sessions[pid] = sess
                        kitty_to_agy.setdefault(kitty_pid, []).append(sess)
                except Exception:
                    pass

                # Remove sessões encerradas
                for dead_pid in list(agy_sessions.keys()):
                    if dead_pid not in current_pids:
                        del agy_sessions[dead_pid]

                # 2. Descobre qual aba está ativa em cada janela Kitty relevante (a cada 1.5s)
                if now - last_tab_scan >= 1.5:
                    last_tab_scan = now
                    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000")

                    for kpid, sessions in kitty_to_agy.items():
                        sock = f"{runtime_dir}/omarchy-kitty-{kpid}"
                        if not os.path.exists(sock):
                            continue

                        active_pts = None
                        active_title = sessions[0]["title"]
                        active_cwd = sessions[0]["cwd"]
                        has_running = any(s["is_running"] for s in sessions)

                        try:
                            raw = subprocess.check_output(
                                ["kitty", "@", "--to", f"unix:{sock}", "ls"],
                                timeout=0.3,
                                stderr=subprocess.DEVNULL,
                            )
                            kdata = json.loads(raw)
                            for os_win in kdata:
                                for tab in os_win.get("tabs", []):
                                    if tab.get("is_active", False):
                                        wins = tab.get("windows", [])
                                        if wins:
                                            w_pid = wins[0].get("pid", 0)
                                            try:
                                                active_pts = os.readlink(f"/proc/{w_pid}/fd/0")
                                            except OSError:
                                                pass
                                            # Encontra se esta aba ativa tem um agy correspondente
                                            for s in sessions:
                                                if s["shell_pid"] == w_pid or s["tty"] == active_pts:
                                                    active_title = s["title"]
                                                    active_cwd = s["cwd"]
                                                    break
                                            break
                        except Exception:
                            # Fallback para o tty da primeira sessão
                            active_pts = sessions[0]["tty"]

                        prev = kitty_window_states.get(kpid, {})
                        kitty_window_states[kpid] = {
                            "active_pts": active_pts or sessions[0]["tty"],
                            "active_title": active_title,
                            "cwd": active_cwd,
                            "has_running": has_running,
                            "last_title": prev.get("last_title", ""),
                        }

                    # Remove janelas kitty que não têm mais agy
                    for kpid in list(kitty_window_states.keys()):
                        if kpid not in kitty_to_agy:
                            del kitty_window_states[kpid]

            # 3. Atualização contínua do frame da animação (a cada 80ms)
            for kpid, state in list(kitty_window_states.items()):
                pts = state.get("active_pts")
                if not pts or not os.path.exists(pts):
                    continue

                title = state.get("active_title", "Antigravity")
                cwd = state.get("cwd", "~")
                has_running = state.get("has_running", False)

                if has_running:
                    frame = SPINNER_FRAMES[spinner_idx % len(SPINNER_FRAMES)]
                    full_title = f"{frame} {title} | {cwd}"
                    set_terminal_title(pts, full_title)
                    state["last_title"] = full_title
                else:
                    full_title = f"{title} | {cwd}"
                    if full_title != state.get("last_title"):
                        set_terminal_title(pts, full_title)
                        state["last_title"] = full_title

            spinner_idx += 1
            time.sleep(0.08)

    finally:
        for kpid, state in kitty_window_states.items():
            pts = state.get("active_pts")
            if pts and os.path.exists(pts):
                title = state.get("active_title", "Antigravity")
                cwd = state.get("cwd", "~")
                set_terminal_title(pts, f"{title} | {cwd}")

        if sqlite_conn:
            try:
                sqlite_conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
