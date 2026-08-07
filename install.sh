#!/usr/bin/env bash
# install.sh — symlink the CLI and wire the presence hook
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$HOME/.local/bin"
chmod +x "$REPO/bin/comms"
ln -sf "$REPO/bin/comms" "$HOME/.local/bin/comms"
echo "✓ comms → $HOME/.local/bin/comms"

chmod +x "$REPO/hooks/comms-hook.py" 2>/dev/null || true

if ! command -v comms >/dev/null 2>&1; then
  echo "⚠ ~/.local/bin não está no PATH desta shell — abra um terminal novo"
fi
echo "Para ligar os hooks de presença: python3 $REPO/hooks/install_hooks.py"
