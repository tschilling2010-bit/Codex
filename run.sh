#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

export HEFTERPRO_STORAGE="${HEFTERPRO_STORAGE:-$(pwd)/backend/storage}"
mkdir -p "$HEFTERPRO_STORAGE"/{profiles,projects,exports,uploads,templates}

exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
