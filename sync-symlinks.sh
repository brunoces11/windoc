#!/usr/bin/env bash
# ==============================================================================
# sync-symlinks.sh - Restaura e valida os Links Simbólicos do WinDoc
# ==============================================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Verificando e sincronizando symlinks a partir de: $PROJECT_DIR"

# 1. Dock Plugin
mkdir -p "$HOME/.config/omarchy/plugins"
ln -sfn "$PROJECT_DIR/dock" "$HOME/.config/omarchy/plugins/rosakodu.dock"
ln -sfn "$PROJECT_DIR/dock" "$HOME/.config/omarchy/plugins/brunoma.windoc"
echo "  [OK] Dock Plugin (~/.config/omarchy/plugins/{rosakodu.dock, brunoma.windoc})"

# 2. Hyprland
mkdir -p "$HOME/.config/hypr"
for f in bindings.lua looknfeel.lua hyprland.lua input.lua monitors.lua autostart.lua hypridle.conf hyprsunset.conf; do
  if [ -f "$PROJECT_DIR/hyprland/$f" ]; then
    ln -sfn "$PROJECT_DIR/hyprland/$f" "$HOME/.config/hypr/$f"
    echo "  [OK] Hyprland: $f"
  fi
done

# 3. Omarchy Shell
mkdir -p "$HOME/.config/omarchy" "$HOME/.local/state/omarchy/toggles"
touch "$HOME/.local/state/omarchy/toggles/bar-off"
for f in shell.json dock-settings.json dock-pinned.json; do
  if [ -f "$PROJECT_DIR/shell/$f" ]; then
    ln -sfn "$PROJECT_DIR/shell/$f" "$HOME/.config/omarchy/$f"
    echo "  [OK] Shell: $f"
  fi
done

# 4. Terminal (Kitty)
mkdir -p "$HOME/.config/kitty"
for f in kitty.conf open-actions.conf tab_bar.py; do
  if [ -f "$PROJECT_DIR/terminal/$f" ]; then
    ln -sfn "$PROJECT_DIR/terminal/$f" "$HOME/.config/kitty/$f"
    echo "  [OK] Terminal: $f"
  fi
done
if [ -f "$PROJECT_DIR/terminal/bashrc" ]; then
  ln -sfn "$PROJECT_DIR/terminal/bashrc" "$HOME/.bashrc"
  echo "  [OK] Shell RC: ~/.bashrc"
fi

# 5. Desktop (única pasta oficial: windoc)
# Nenhuma pasta ou atalho duplicado é criado no Desktop.

# Links adotados dinamicamente pelo comando `windoc adopt`.
MANIFEST="$PROJECT_DIR/symlinks.tsv"
if [ -f "$MANIFEST" ]; then
  while IFS=$'\t' read -r source_path repo_path; do
    [ -n "${source_path:-}" ] || continue
    [[ "$source_path" == \#* ]] && continue
    source_path="${source_path/#\~/$HOME}"
    target="$PROJECT_DIR/$repo_path"
    if [ ! -e "$target" ]; then
      echo "  [ERRO] Destino ausente no WinDoc: $repo_path" >&2
      exit 1
    fi
    mkdir -p "$(dirname "$source_path")"
    if [ -e "$source_path" ] && [ ! -L "$source_path" ]; then
      echo "  [ERRO] Existe arquivo não gerenciado no destino: $source_path" >&2
      exit 1
    fi
    ln -sfn "$target" "$source_path"
    [ "$(readlink -f "$source_path")" = "$(readlink -f "$target")" ] || exit 1
    echo "  [OK] Adotado: $source_path"
  done < "$MANIFEST"
fi

echo "==> Todos os symlinks foram validados com sucesso!"
