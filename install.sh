#!/usr/bin/env bash
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGES="$REPO_DIR/pacotes-sistema.txt"
if [[ "${1:-}" == "--install-packages" ]]; then
  command -v pacman >/dev/null || { echo "Este instalador requer Arch Linux/Omarchy." >&2; exit 1; }
  mapfile -t packages < <(sed -e 's/#.*//' -e '/^[[:space:]]*$/d' "$PACKAGES")
  if ((${#packages[@]})); then sudo pacman -S --needed "${packages[@]}"; else echo "Inventário de pacotes vazio; nenhum pacote será instalado."; fi
elif [[ $# -gt 0 ]]; then
  echo "Uso: ./install.sh [--install-packages]" >&2; exit 2
fi
"$REPO_DIR/sync-symlinks.sh"
# O Antigravity regrava settings.json por substituição: aplicar somente o bloco
# title em arquivo físico, conforme a exceção documentada do WinDocAdoptRule.
if command -v agy >/dev/null 2>&1; then
  python3 "$REPO_DIR/ANTIGRAVITY_TITLE.py" --install
fi
mkdir -p "$HOME/.local/bin"
ln -sfn "$REPO_DIR/scripts/windoc" "$HOME/.local/bin/windoc"
[ "$(readlink -f "$HOME/.local/bin/windoc")" = "$(readlink -f "$REPO_DIR/scripts/windoc")" ] || { echo "Falha ao validar instalação do comando." >&2; exit 1; }
echo "WinDoc configurado; comando windoc validado em ~/.local/bin/windoc."
