#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHUTDOWN_SCRIPT="$SCRIPT_DIR/dog_shutdown.py"
XBINDKEYS_CONFIG="$HOME/.xbindkeysrc"

chmod +x "$SHUTDOWN_SCRIPT"

cat >> "$XBINDKEYS_CONFIG" << EOF
"$SHUTDOWN_SCRIPT"
    F12
EOF

pkill xbindkeys 2>/dev/null || true
xbindkeys
