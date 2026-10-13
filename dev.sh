#!/usr/bin/env bash
# One command: install what is missing, create the demo data, start the API and the web app.
#
#   ./dev.sh          development servers with hot reload
#   ./dev.sh prod     production build of the web app, then start both
#
# Ports come from API_PORT and WEB_PORT (environment or .env), default 8000 and 3000.
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env ]; then set -a; . ./.env; set +a; fi
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"
MODE="${1:-dev}"

if [ ! -x backend/.venv/bin/uvicorn ]; then
  echo "==> Installing the API (Python virtual environment in backend/.venv)"
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install --quiet -r backend/requirements.txt
fi
if [ ! -d frontend/node_modules ]; then
  echo "==> Installing the web app (npm ci)"
  (cd frontend && npm ci --no-audit --no-fund)
fi

(cd backend && .venv/bin/python -m app.seed)

# Stop both servers when this script ends, however it ends.
trap 'trap - EXIT INT TERM; kill 0' EXIT INT TERM

(cd backend && exec .venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port "$API_PORT") &

export BACKEND_URL="http://127.0.0.1:${API_PORT}"
cd frontend
if [ "$MODE" = "prod" ]; then
  npm run build
  echo "==> Open http://localhost:${WEB_PORT}"
  npx next start --port "$WEB_PORT"
else
  echo "==> Open http://localhost:${WEB_PORT}"
  npx next dev --port "$WEB_PORT"
fi
