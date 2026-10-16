#!/usr/bin/env python3
"""
Monitor dinâmico de título e animação para Antigravity CLI no Hyprland/Kitty.
Atualiza o título da janela Wayland com o tópico da conversa e uma microanimação
de loader (idêntica à do Codex CLI) enquanto o agente estiver processando.
"""

import argparse
import os
import signal
import sqlite3
import sys
import time

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
DB_PATH = os.path.expanduser("~/.gemini/antigravity-cli/conversation_summaries.db")


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def find_agy_child(parent_pid: int) -> int | None:
    """Busca o PID do processo 'agy' filho do shell pai."""
    # 1. Tenta ler via /proc/<parent_pid>/task/<parent_pid>/children
    children_file = f"/proc/{parent_pid}/task/{parent_pid}/children"
    child_pids = []
    if os.path.exists(children_file):
        try:
            with open(children_file, "r") as f:
                child_pids = [int(p) for p in f.read().split() if p.isdigit()]
        except Exception:
            pass

    # 2. Se não encontrou pelo task, busca em /proc iterando os processos
    if not child_pids:
        try:
            for entry in os.listdir("/proc"):
                if not entry.isdigit():
                    continue
                c_pid = int(entry)
                stat_file = f"/proc/{c_pid}/stat"
                if os.path.exists(stat_file):
                    try:
                        with open(stat_file, "r") as sf:
                            parts = sf.read().split()
                            # stat: pid (comm) state ppid ...
                            if len(parts) > 3 and int(parts[3]) == parent_pid:
                                child_pids.append(c_pid)
                    except Exception:
                        continue
        except Exception:
            pass

    for cp in child_pids:
        try:
            cmd_file = f"/proc/{cp}/cmdline"
            if os.path.exists(cmd_file):
                with open(cmd_file, "rb") as cf:
                    cmdline = cf.read().decode("utf-8", errors="ignore")
                    if "agy" in cmdline:
                        return cp
        except Exception:
            continue
    return None


def get_conversation_id(agy_pid: int) -> str | None:
    """Examina os descritores abertos do agy para extrair o ID da conversa."""
    fd_dir = f"/proc/{agy_pid}/fd"
    if not os.path.exists(fd_dir):
        return None
    try:
        for link in os.listdir(fd_dir):
            try:
                target = os.readlink(os.path.join(fd_dir, link))
                if "/presence/" in target and target.endswith(".lock"):
                    return os.path.basename(target)[:-5]
                elif "/conversations/" in target and target.endswith(".db"):
                    return os.path.basename(target)[:-3]
            except Exception:
                continue
    except Exception:
        pass
    return None


def get_conversation_data(conv_id: str) -> tuple[str | None, bool]:
    """Consulta o título e se o estado é RUNNING (ativo) no banco de resumos."""
    if not os.path.exists(DB_PATH):
        return None, False
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=0.1)
        cur = conn.cursor()
        cur.execute(
            "SELECT title, status, not_fully_idle FROM conversation_summaries WHERE conversation_id = ?",
            (conv_id,),
        )
        row = cur.fetchone()
        conn.close()
        if row:
            title = row[0].strip() if row[0] else None
            is_running = (row[1] == "CASCADE_RUN_STATUS_RUNNING") or (bool(row[2]))
            return title, is_running
    except Exception:
        pass
    return None, False


def get_cwd_name(agy_pid: int) -> str:
    """Obtém o nome amigável da pasta atual de trabalho."""
    try:
        cwd = os.readlink(f"/proc/{agy_pid}/cwd")
        home = os.path.expanduser("~")
        if cwd == home:
            return "~"
        return os.path.basename(cwd) or "~"
    except Exception:
        return "Desktop"


def set_terminal_title(tty_out, title: str):
    """Envia a sequência OSC 0 para atualizar o título da janela/aba."""
    try:
        tty_out.write(f"\033]0;{title}\007")
        tty_out.flush()
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shell-pid", type=int, required=True, help="PID do shell bash pai")
    parser.add_argument("--tty", type=str, default="/dev/tty", help="Dispositivo TTY para escape codes")
    args = parser.parse_args()

    # Tratamento gracioso de encerramento
    def handle_exit(signum, frame):
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_exit)
    signal.signal(signal.SIGINT, handle_exit)

    # Abre a TTY para escrita
    try:
        tty_out = open(args.tty, "w", encoding="utf-8")
    except Exception:
        try:
            tty_out = open(f"/proc/{args.shell_pid}/fd/1", "w", encoding="utf-8")
        except Exception:
            sys.exit(1)

    # 1. Aguarda o agy inicializar
    agy_pid = None
    for _ in range(30):  # até 3 segundos
        if not is_process_alive(args.shell_pid):
            sys.exit(0)
        agy_pid = find_agy_child(args.shell_pid)
        if agy_pid:
            break
        time.sleep(0.1)

    if not agy_pid:
        sys.exit(0)

    cwd_name = get_cwd_name(agy_pid)
    conv_id = None
    last_title = "Antigravity"
    is_running = False
    spinner_idx = 0
    last_db_check = 0.0
    last_set_title = ""

    # 2. Loop principal de monitoramento
    while is_process_alive(agy_pid) and is_process_alive(args.shell_pid):
        now = time.time()

        # Busca conv_id se ainda não encontrado
        if not conv_id:
            conv_id = get_conversation_id(agy_pid)

        # Consulta SQLite com taxa controlada (a cada 0.5s)
        if now - last_db_check >= 0.5:
            last_db_check = now
            if conv_id:
                title, running = get_conversation_data(conv_id)
                if title:
                    last_title = title
                is_running = running
            else:
                is_running = False

        if is_running:
            frame = SPINNER_FRAMES[spinner_idx % len(SPINNER_FRAMES)]
            spinner_idx += 1
            full_title = f"{frame} {last_title} | {cwd_name}"
            set_terminal_title(tty_out, full_title)
            last_set_title = full_title
            time.sleep(0.08)
        else:
            full_title = f"{last_title} | {cwd_name}"
            if full_title != last_set_title:
                set_terminal_title(tty_out, full_title)
                last_set_title = full_title
            time.sleep(0.25)

    # Restaura o título padrão ao sair
    set_terminal_title(tty_out, f"brunoma: ~/{cwd_name}")


if __name__ == "__main__":
    main()
