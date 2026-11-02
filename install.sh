#!/usr/bin/env bash
set -eo pipefail
APP_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$APP_DIR"
install_system_deps() {
  if command -v dnf >/dev/null 2>&1; then sudo dnf install -y gtk4 libadwaita python3-gobject python3.12 ffmpeg alsa-utils desktop-file-utils
  elif command -v apt-get >/dev/null 2>&1; then sudo apt-get update && sudo apt-get install -y python3-gi python3-venv gir1.2-gtk-4.0 gir1.2-adw-1 ffmpeg alsa-utils desktop-file-utils
  elif command -v pacman >/dev/null 2>&1; then sudo pacman -S --needed gtk4 libadwaita python-gobject ffmpeg alsa-utils desktop-file-utils
  else echo "Unsupported package manager. Install GTK4, libadwaita, PyGObject, FFmpeg and ALSA utilities manually."; exit 1; fi
}
if [[ $# -eq 0 || "$1" != "--no-system-deps" ]]; then install_system_deps; fi
PYTHON_BIN=""
for candidate in python3.12 python3.11; do if command -v "$candidate" >/dev/null 2>&1; then PYTHON_BIN="$(command -v "$candidate")"; break; fi; done
if [[ -z "$PYTHON_BIN" ]]; then echo "Python 3.11 or 3.12 is required."; exit 1; fi
if [[ ! -d .venv ]]; then "$PYTHON_BIN" -m venv .venv; fi
.venv/bin/python -m pip install --upgrade pip wheel
.venv/bin/python -m pip install -r requirements.txt
mkdir -p "$HOME/.local/share/applications" "$HOME/.local/share/icons/hicolor/scalable/apps"
cp assets/voxora.svg "$HOME/.local/share/icons/hicolor/scalable/apps/com.pspyn.Voxora.svg"
cat > "$HOME/.local/share/applications/voxora.desktop" <<DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=Voxora
GenericName=Private Voice Cloning Studio
Comment=Create speech in your own voice, entirely on your device
Exec=/usr/bin/python3 "$APP_DIR/native_app.py"
Path=$APP_DIR
Icon=com.pspyn.Voxora
Terminal=false
Categories=AudioVideo;Audio;
Keywords=voice;cloning;tts;speech;offline;private;
StartupNotify=true
StartupWMClass=com.pspyn.Voxora
DESKTOP
chmod +x "$APP_DIR/run.sh" "$APP_DIR/download_models.py"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
SKIP_MODEL_DOWNLOAD="${SKIP_MODEL_DOWNLOAD:-0}"
if [[ "$SKIP_MODEL_DOWNLOAD" != "1" ]]; then
  echo "The three language models require several GB of downloads (Kannada is the largest)."
  read -r -p "Download English, Hindi and Kannada models now? [Y/n] " answer
  if [[ ! "$answer" =~ ^[Nn]$ ]]; then .venv/bin/python download_models.py; fi
fi
echo "Voxora installed. Open it from your desktop Applications menu."
