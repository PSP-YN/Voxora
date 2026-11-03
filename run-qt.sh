#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$APP_DIR/.venv/bin/python" "$APP_DIR/qt_app/main.py" "$@"
