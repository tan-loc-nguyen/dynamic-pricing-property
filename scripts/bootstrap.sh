#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# One-shot setup for dynamic-pricing-property.
#
# Assumes NOTHING is installed. Verifies (and where possible installs) the
# prerequisites, then creates the Python venv, installs both dependency sets
# and seeds the demo database.
#
# Safe to re-run: every step is idempotent.
# ---------------------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$ROOT/apps/api"
WEB_DIR="$ROOT/apps/web"
VENV="$API_DIR/.venv"

MIN_PY_MINOR=10   # needs 3.10+ for modern typing syntax
MIN_NODE_MAJOR=18 # Next.js 15 requirement

bold()  { printf "\033[1m%s\033[0m\n" "$*"; }
info()  { printf "  %s\n" "$*"; }
ok()    { printf "  \033[32m✓\033[0m %s\n" "$*"; }
warn()  { printf "  \033[33m!\033[0m %s\n" "$*"; }
fail()  { printf "  \033[31m✗\033[0m %s\n" "$*" >&2; }

die() {
  fail "$1"
  [ $# -gt 1 ] && printf "\n%s\n" "$2" >&2
  exit 1
}

OS="$(uname -s)"
have() { command -v "$1" >/dev/null 2>&1; }

# --- package-manager helper -------------------------------------------------
install_hint() {
  local tool="$1"
  case "$OS" in
    Darwin)
      if have brew; then echo "brew install $tool"
      else echo "Install Homebrew first (https://brew.sh), then: brew install $tool"; fi ;;
    Linux)
      if have apt-get;  then echo "sudo apt-get update && sudo apt-get install -y $tool"
      elif have dnf;    then echo "sudo dnf install -y $tool"
      elif have pacman; then echo "sudo pacman -S $tool"
      else echo "Install '$tool' with your distribution's package manager."; fi ;;
    *) echo "Install '$tool' for your platform." ;;
  esac
}

try_install() {
  local tool="$1"
  if [ "${AUTO_INSTALL:-0}" != "1" ]; then return 1; fi
  case "$OS" in
    Darwin) have brew && { info "Installing $tool via Homebrew…"; brew install "$tool" && return 0; } ;;
    Linux)
      if have apt-get; then
        info "Installing $tool via apt…"
        sudo apt-get update -qq && sudo apt-get install -y "$tool" && return 0
      fi ;;
  esac
  return 1
}

# --- 1. Python --------------------------------------------------------------
bold "1/5  Python"
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if have "$candidate"; then
    minor="$("$candidate" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo 0)"
    major="$("$candidate" -c 'import sys; print(sys.version_info.major)' 2>/dev/null || echo 0)"
    if [ "$major" = "3" ] && [ "$minor" -ge "$MIN_PY_MINOR" ]; then
      PYTHON="$candidate"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  warn "No Python 3.$MIN_PY_MINOR+ found."
  if try_install python3; then
    PYTHON=python3
  else
    die "Python 3.$MIN_PY_MINOR or newer is required." \
        "Install it with:
    $(install_hint python3)

Then re-run: make setup
(Or re-run with AUTO_INSTALL=1 make setup to let this script install it.)"
  fi
fi
ok "$($PYTHON --version) at $(command -v "$PYTHON")"

$PYTHON -c 'import venv' 2>/dev/null || die "Python 'venv' module is missing." \
  "On Debian/Ubuntu: sudo apt-get install -y python3-venv"

# --- 2. Node ----------------------------------------------------------------
bold "2/5  Node.js"
if ! have node; then
  warn "Node.js not found."
  try_install node || die "Node.js $MIN_NODE_MAJOR+ is required." \
    "Install it with:
    $(install_hint node)

Or use nvm (https://github.com/nvm-sh/nvm):
    nvm install --lts

Then re-run: make setup"
fi

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$NODE_MAJOR" -lt "$MIN_NODE_MAJOR" ]; then
  die "Node.js $MIN_NODE_MAJOR+ is required (found $(node --version))." \
      "Upgrade with: $(install_hint node)"
fi
have npm || die "npm not found." "npm ships with Node.js — reinstall Node: $(install_hint node)"
ok "Node $(node --version), npm $(npm --version)"

# --- 3. Python environment --------------------------------------------------
bold "3/5  Backend dependencies"
if [ ! -d "$VENV" ]; then
  info "Creating virtualenv at apps/api/.venv…"
  "$PYTHON" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$API_DIR/requirements.txt"
ok "Python packages installed"

# --- 4. Frontend ------------------------------------------------------------
bold "4/5  Frontend dependencies"
if [ ! -d "$WEB_DIR/node_modules" ]; then
  ( cd "$WEB_DIR" && npm install --silent )
else
  ( cd "$WEB_DIR" && npm install --silent --prefer-offline --no-audit --no-fund )
fi
ok "npm packages installed"

# --- 5. Environment + database ---------------------------------------------
bold "5/5  Configuration & demo data"
if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  ok "Created .env from .env.example (demo mode, no credentials needed)"
else
  info ".env already exists — leaving it untouched"
fi

mkdir -p "$ROOT/data"
( cd "$API_DIR" && "$VENV/bin/python" -m dynamic_pricing.seed )
ok "Demo database ready at data/dynamic_pricing.db"

echo
bold "Setup complete."
echo "  Start the app with:  make dev"
echo "  Then open:           http://localhost:3000"
