#!/usr/bin/env bash
# Local development without Docker: SQLite + uvicorn + next dev
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r backend/requirements-dev.txt
(cd frontend && [ -d node_modules ] || npm install)
(cd backend && ../.venv/bin/uvicorn app.main:app --reload --port 8000) &
(cd frontend && npm run dev) &
wait
