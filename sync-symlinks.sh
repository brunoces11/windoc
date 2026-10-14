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
mkdir -p "$HOME/.config/omarchy"
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

# 5. Desktop shortcuts
mkdir -p "$HOME/Desktop"
ln -sfn "$PROJECT_DIR" "$HOME/Desktop/WINDOC"
ln -sfn "$PROJECT_DIR" "$HOME/Desktop/WinDoc"
ln -sfn "$PROJECT_DIR/config-sistema.txt" "$HOME/Desktop/config-sistema.txt"
echo "  [OK] Desktop shortcuts (WINDOC, WinDoc, config-sistema.txt)"

echo "==> Todos os symlinks foram validados com sucesso!"
