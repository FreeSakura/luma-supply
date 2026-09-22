#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
(cd web && npm ci && npm run build)
.venv/bin/python -m scripts.seed
exec .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port "${APP_PORT:-8000}"
