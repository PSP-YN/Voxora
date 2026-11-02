#!/usr/bin/env bash
set -euo pipefail
rm -f "$HOME/.local/share/applications/voxora.desktop"
rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/com.pspyn.Voxora.svg"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
echo "Voxora desktop launcher removed. Your models, voice profiles and exports were not deleted."
