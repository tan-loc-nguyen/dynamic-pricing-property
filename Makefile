# dynamic-pricing-property — explainable pricing copilot MVP
#
#   make setup   first-time install (checks/installs prerequisites)
#   make dev     run backend + frontend together
#   make test    run the pricing engine test suite

SHELL := /bin/bash
ROOT  := $(shell pwd)
API   := $(ROOT)/apps/api
WEB   := $(ROOT)/apps/web
# `=` (not `:=`) so this re-checks on every recipe line rather than once at
# parse time — `make demo` creates the venv via `setup` before `PY` is first
# used, and a Windows venv puts the interpreter under Scripts/, not bin/.
PY    = $(if $(wildcard $(API)/.venv/Scripts/python.exe),$(API)/.venv/Scripts/python.exe,$(API)/.venv/bin/python)

.DEFAULT_GOAL := help
.PHONY: help setup dev api web seed reseed demo test test-watch lint clean check env bundle run-bundle

help:
	@echo ""
	@echo "  Dynamic Pricing Property — explainable pricing copilot"
	@echo ""
	@echo "  make setup     Install everything (Python venv, npm packages, demo DB)"
	@echo "  make dev       Start API (:8000) and web (:3000) together"
	@echo "  make test      Run the pricing + feature engine tests"
	@echo "  make lint      Check for unreachable / dead code"
	@echo "  make bundle    Build the single-file desktop app into dist/"
	@echo ""
	@echo "  make api       Backend only"
	@echo "  make web       Frontend only"
	@echo "  make seed      Create demo data if the database is empty"
	@echo "  make demo      One command for a fresh machine: deps, demo data, run"
	@echo "  make reseed    Rebuild the demo database from scratch"
	@echo "  make check     Verify prerequisites without installing"
	@echo "  make clean     Remove venv, node_modules and the database"
	@echo ""

setup:
	@./scripts/bootstrap.sh

dev:
	@./scripts/dev.sh

api:
	@cd $(API) && $(PY) -m uvicorn dynamic_pricing.main:app --host 127.0.0.1 --port 8000 --reload

web:
	@cd $(WEB) && npm run dev

seed:
	@cd $(API) && $(PY) -m dynamic_pricing.seed

reseed:
	@cd $(API) && $(PY) -m dynamic_pricing.seed --force

# The whole path from a fresh clone to a running demo, in one command. Reseed
# runs FIRST and unconditionally: a database from before a schema change is the
# single thing most likely to stop a teammate, and it fails in a way that reads
# like the app is broken rather than the data being old.
demo: setup reseed
	@$(MAKE) dev

test:
	@cd $(API) && $(PY) -m pytest -q

bundle:
	@echo "  Exporting the web app…"
	@cd $(WEB) && npm run build
	@echo "  Packaging the binary…"
	@cd $(ROOT) && $(PY) -m PyInstaller --clean --noconfirm \
		--distpath $(ROOT)/dist --workpath $(ROOT)/build/pyinstaller \
		packaging/dynamic_pricing.spec
	@echo ""
	@echo "  Built: dist/DynamicPricingProperty"
	@echo "  PyInstaller cannot cross-compile — this binary runs on $$(uname -s) only."
	@echo ""

run-bundle: bundle
	@$(ROOT)/dist/DynamicPricingProperty

lint:
	@cd $(API) && $(PY) -m ruff check dynamic_pricing tests
	@cd $(WEB) && npm run --silent check:messages

test-watch:
	@cd $(API) && $(PY) -m pytest -q --tb=short -x

check:
	@printf "Python: "; command -v python3 >/dev/null && python3 --version || echo "NOT FOUND"
	@printf "Node:   "; command -v node >/dev/null && node --version || echo "NOT FOUND"
	@printf "npm:    "; command -v npm >/dev/null && npm --version || echo "NOT FOUND"
	@printf "venv:   "; test -d $(API)/.venv && echo "present" || echo "missing (run make setup)"
	@printf "web:    "; test -d $(WEB)/node_modules && echo "present" || echo "missing (run make setup)"
	@printf "db:     "; test -f $(ROOT)/data/dynamic_pricing.db && echo "present" || echo "missing (run make seed)"

env:
	@test -f .env || cp .env.example .env
	@echo ".env ready"

clean:
	@rm -rf $(API)/.venv $(WEB)/node_modules $(WEB)/.next $(ROOT)/data/dynamic_pricing.db*
	@find $(API) -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned. Run 'make setup' to start over."
