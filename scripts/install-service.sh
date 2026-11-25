#!/usr/bin/env bash
# Install xMender as a systemd service running as a non-root user.
# Usage: scripts/install-service.sh [user] [group]
#   Defaults to the user who invokes the script (via sudo: $SUDO_USER).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="${1:-${SUDO_USER:-$(id -un)}}"
RUN_GROUP="${2:-$(id -gn "$RUN_USER")}"
UNIT=/etc/systemd/system/xmender.service

if [[ "$RUN_USER" == "root" ]]; then
    echo "Refusing to run xMender as root. Pass a user: $0 <user> [group]" >&2
    exit 1
fi
if [[ ! -x "$DIR/.venv/bin/python" ]]; then
    echo "No virtualenv found. Run scripts/setup.sh first." >&2
    exit 1
fi

mkdir -p "$DIR/data"
chown "$RUN_USER:$RUN_GROUP" "$DIR/data"
chmod 700 "$DIR/data"

TMP="$(mktemp)"
sed -e "s|@USER@|$RUN_USER|g" -e "s|@GROUP@|$RUN_GROUP|g" -e "s|@DIR@|$DIR|g" \
    "$DIR/deploy/xmender.service" > "$TMP"

if [[ $EUID -ne 0 ]]; then
    echo "Re-run with sudo to install $UNIT." >&2
    rm -f "$TMP"
    exit 1
fi

install -m 0644 "$TMP" "$UNIT"
rm -f "$TMP"
systemctl daemon-reload
systemctl enable --now xmender
echo "Installed. Admin setup password (first start): journalctl -u xmender | grep -A1 'Temporary password'"
