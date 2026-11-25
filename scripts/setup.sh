#!/usr/bin/env bash
# Create the virtualenv, install dependencies and a starter .env.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

PY="${PYTHON:-python3}"
"$PY" -c 'import sys; sys.exit(sys.version_info < (3, 11))' || {
    echo "Python 3.11+ is required." >&2
    exit 1
}

[[ -d .venv ]] || "$PY" -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

if [[ ! -f .env ]]; then
    cp .env.example .env
    chmod 600 .env
    echo "Created .env from .env.example"
fi
echo "Done. Start with: .venv/bin/python -m xmender"
