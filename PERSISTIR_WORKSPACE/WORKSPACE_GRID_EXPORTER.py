"""Build, load, and query the read-only Dwindle exporter for this Hyprland build."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


SOURCE = Path(__file__).with_suffix(".cpp")
PLUGIN_NAME = "windoc-grid-exporter"
COMMAND = "windoc-layout"
PLUGIN_RECORD = "WORKSPACE_GRID_PLUGIN.json"


def run(argv: list[str], *, timeout: float = 20, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=check)


def runtime_identity() -> tuple[str, str]:
    version = run(["hyprctl", "version"]).stdout
    match = re.search(r"commit ([0-9a-f]{40})", version)
    if not match:
        raise RuntimeError("Não foi possível identificar o commit exato do Hyprland")
    commit = match.group(1)
    include = Path("/usr/include/hyprland/src")
    version_header = (include / "version.h").read_text()
    header_commit = re.search(r'^#define GIT_COMMIT_HASH\s+"([0-9a-f]{40})"', version_header, re.MULTILINE)
    if not header_commit or header_commit.group(1) != commit:
        raise RuntimeError("Os headers instalados não correspondem ao commit do compositor")
    pkg = run(["pkg-config", "--modversion", "hyprland"]).stdout.strip()
    compiler = run(["g++", "--version"]).stdout.splitlines()[0]
    flags = run(["pkg-config", "--cflags", "--libs", "hyprland"]).stdout.strip()
    header_names = (
        "plugins/PluginAPI.hpp", "state/WorkspaceState.hpp", "desktop/Workspace.hpp",
        "desktop/view/Window.hpp", "desktop/view/Group.hpp", "layout/space/Space.hpp",
        "layout/target/Target.hpp", "layout/algorithm/Algorithm.hpp",
        "layout/algorithm/TiledAlgorithm.hpp", "layout/algorithm/tiled/dwindle/DwindleAlgorithm.hpp",
        "version.h",
    )
    headers = "\n".join(f"{name}\0{(include / name).read_bytes().hex()}" for name in header_names)
    fingerprint = hashlib.sha256("\n".join((SOURCE.read_text(), version, pkg, compiler, flags, headers)).encode()).hexdigest()[:24]
    return commit, fingerprint


def query(workspace: int = 1) -> dict | None:
    result = run(["hyprctl", COMMAND, str(workspace)], check=False)
    if result.returncode:
        return None
    try:
        value = json.loads(result.stdout)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def ensure_loaded(state_dir: Path, workspace: int = 1) -> tuple[dict | None, str | None]:
    """Compile against installed headers, require exact runtime commit, then load and verify."""
    try:
        commit, build_id = runtime_identity()
        current = query(workspace)
        if current and current.get("build_id") == build_id:
            return (None if current.get("error") else current), None

        state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        output = state_dir / f"WORKSPACE_GRID_{build_id}.so"
        if not output.is_file():
            compiler_flags = shlex.split(run(["pkg-config", "--cflags", "--libs", "hyprland"]).stdout)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(prefix=".workspace-grid-", suffix=".so", dir=state_dir, delete=False) as handle:
                    temporary = Path(handle.name)
                run([
                    "g++", "-std=c++26", "-O2", "-fPIC", "-shared",
                    f"-DWINDOC_HYPRLAND_HASH=\"{commit}\"",
                    f"-DWINDOC_EXPORTER_BUILD_ID=\"{build_id}\"",
                    "-I/usr/include/hyprland", str(SOURCE), "-o", str(temporary), *compiler_flags,
                ], timeout=90)
                os.chmod(temporary, 0o600)
                os.replace(temporary, output)
            finally:
                if temporary and temporary.exists():
                    temporary.unlink()

        # Remove our prior in-process build before registering the same IPC command.
        plugins = json.loads(run(["hyprctl", "plugin", "list", "-j"]).stdout)
        ours = any(row.get("name") == PLUGIN_NAME for row in plugins if isinstance(row, dict))
        if ours:
            try:
                previous = json.loads((state_dir / PLUGIN_RECORD).read_text())
                old_path = previous.get("path")
            except (OSError, ValueError, AttributeError):
                old_path = None
            if not old_path:
                raise RuntimeError("Há uma versão do exportador carregada sem registro local do caminho; não vou duplicar o comando")
            run(["hyprctl", "plugin", "unload", old_path])
        record = json.dumps({"path": str(output), "build_id": build_id}, sort_keys=True, indent=2) + "\n"
        temporary_record = state_dir / f".{PLUGIN_RECORD}.tmp"
        temporary_record.write_text(record)
        os.chmod(temporary_record, 0o600)
        os.replace(temporary_record, state_dir / PLUGIN_RECORD)
        load = run(["hyprctl", "plugin", "load", str(output)], check=False)
        if load.returncode or "could not be loaded" in (load.stdout + load.stderr).lower():
            raise RuntimeError((load.stdout + load.stderr).strip() or "Hyprland recusou carregar o exportador")

        verified = query(workspace)
        if not verified or verified.get("build_id") != build_id:
            raise RuntimeError("O comando nativo do exportador não passou na verificação após o carregamento")
        return (None if verified.get("error") else verified), None
    except subprocess.CalledProcessError as error:
        details = (error.stderr or error.stdout or str(error)).strip()
        return None, details
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as error:
        return None, str(error)
