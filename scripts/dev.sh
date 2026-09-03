#!/usr/bin/env bash
# Start backend + frontend together; Ctrl-C stops both cleanly.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$ROOT/apps/api"
WEB_DIR="$ROOT/apps/web"
VENV="$API_DIR/.venv"

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

# A Windows venv (via Git Bash) puts the interpreter under Scripts/, not bin/.
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) VENV_BIN="$VENV/Scripts" ;;
  *)                    VENV_BIN="$VENV/bin" ;;
esac

# Auto-setup on first run so `make dev` alone is enough.
if [ ! -d "$VENV" ] || [ ! -d "$WEB_DIR/node_modules" ]; then
  printf "\033[1mFirst run detected — running setup…\033[0m\n\n"
  "$ROOT/scripts/bootstrap.sh"
  echo
fi

[ -f "$ROOT/.env" ] || cp "$ROOT/.env.example" "$ROOT/.env"

PIDS=()
cleanup() {
  echo
  echo "Shutting down…"
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

printf "\033[1mDynamic Pricing Property\033[0m\n"
echo "  API   http://${API_HOST}:${API_PORT}  (docs at /docs)"
echo "  Web   http://localhost:${WEB_PORT}"
echo

( cd "$API_DIR" && "$VENV_BIN/python" -m uvicorn dynamic_pricing.main:app \
    --host "$API_HOST" --port "$API_PORT" --reload 2>&1 | sed $'s/^/\033[36m[api]\033[0m /' ) &
PIDS+=($!)

( cd "$WEB_DIR" && NEXT_PUBLIC_API_URL="http://${API_HOST}:${API_PORT}" \
    npm run dev -- --port "$WEB_PORT" 2>&1 | sed $'s/^/\033[35m[web]\033[0m /' ) &
PIDS+=($!)

wait
