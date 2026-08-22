# dynamic-pricing-property — explainable pricing copilot MVP
#
#   make setup   first-time install (checks/installs prerequisites)
#   make dev     run backend + frontend together
#   make test    run the pricing engine test suite

SHELL := /bin/bash
ROOT  := $(shell pwd)
API   := $(ROOT)/apps/api
WEB   := $(ROOT)/apps/web
PY    := $(API)/.venv/bin/python

.DEFAULT_GOAL := help
.PHONY: help setup dev api web seed reseed test test-watch clean check env

help:
	@echo ""
	@echo "  Dynamic Pricing Property — explainable pricing copilot"
	@echo ""
	@echo "  make setup     Install everything (Python venv, npm packages, demo DB)"
	@echo "  make dev       Start API (:8000) and web (:3000) together"
	@echo "  make test      Run the pricing + feature engine tests"
	@echo ""
	@echo "  make api       Backend only"
	@echo "  make web       Frontend only"
	@echo "  make seed      Create demo data if the database is empty"
	@echo "  make reseed    Wipe and rebuild the demo data"
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

test:
	@cd $(API) && $(PY) -m pytest -q

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
