# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An explainable revenue-management copilot for a short-term rental property (Luminous Luxury Apartments), sitting above the Blue Jay PMS. It recommends a NET room rate per date, explains the recommendation in plain language, and lets an operator accept or override it. It is a decision-support tool, not an autopilot — nothing is ever pushed back to Blue Jay or any OTA (Shadow Mode, D22).

Two kinds of number live in this system and must never be mixed:
- **Client-validated**: Luminous' seasonal MIN/BASE/MAX NET rate table. Real business data the engine anchors on and never scales.
- **Unvalidated**: the dynamic layer on top (pace, pickup, events, market). Invented by the engineering team so the product could be built. See `ASSUMPTIONS.md` before treating any dynamic threshold as fact.

Read `README.md` for the full pipeline narrative and product framing before making architectural changes — it explains *why* the system is shaped this way, which this file does not repeat.

## Monorepo layout

- `apps/api` — Python/FastAPI backend. Owns all pricing logic.
- `apps/web` — Next.js 15 (App Router) frontend. See `apps/web/CLAUDE.md` for frontend-specific conventions (component architecture, design tokens, i18n, testing). Read it before frontend work.
- `docs/` — `DECISIONS.md` (numbered engineering decisions, D1–D38+), `RUNNING.md`, `BLUEJAY*.md`, `MARKET_DATA.md`.
- `ASSUMPTIONS.md` — every unvalidated guess, with the question to ask the client to validate it.

## Commands

```bash
make setup          # first-time install: Python venv, npm packages, demo DB
make demo           # reseed + run — the one command for a fresh machine
make dev            # run API (:8000) and web (:3000) together
make api            # backend only
make web            # frontend only
make test           # backend pytest suite (555 tests) — does NOT run frontend tests
make lint           # ruff on the backend + ICU/message-consistency check on the frontend
make reseed         # rebuild the demo DB from scratch (needed after a schema change)
make check          # verify prerequisites without installing
make bundle         # build the single-file desktop app into dist/
```

Frontend tests are separate from `make test` — run them from `apps/web`:
```bash
cd apps/web && npm test                    # full Vitest suite
cd apps/web && npx vitest run path/to/File.test.tsx   # a single file
cd apps/web && npm run check:messages      # ICU + locale-consistency check on messages/*.json
```

Backend single test:
```bash
cd apps/api && .venv/bin/python -m pytest tests/path/to/test_file.py::test_name -q
```

## Architecture

### Pipeline (backend)

```
Provider (Blue Jay / mock / snapshot)   normalizes external data into domain rows
  -> Feature Engine (dynamic_pricing/features/)   measures: occupancy, pickup, market, booking curve
  -> Seasonal Rate Book (dynamic_pricing/pricing/rate_book.py)   CLIENT-VALIDATED MIN/BASE/MAX lookup
  -> Pricing Engine (dynamic_pricing/pricing/engine.py)   bounded dynamic layer, additive %, clamped to band
  -> Recommendation   persisted with a reproducible snapshot (features, band, engine + config version)
  -> Decision   operator accept/override, never auto-applied
  -> Outcome   what actually happened; real outcomes are never invented (D23)
```

The engine is additive (D19) and pluggable via a registry (`register_engine`, D29) — swapping in a finance-authored engine is one registration, not a rewrite. Season *selects* a band; it never multiplies it (D17) — seasonality already lives in the rate table, so applying a seasonality factor on top would double-count it.

**D10 — the frontend holds no pricing logic.** Every price, factor, and threshold the UI shows was computed in Python and served by the API. If you find yourself writing a multiplier or a threshold comparison in a `.tsx` file, stop — it belongs in `apps/api/dynamic_pricing/pricing/` or `features/`, with the label/reason served from `dynamic_pricing/constants.py`.

### i18n (spans both apps)

The pricing explanation is translated, not just the chrome. The engine never composes a sentence — each adjustment step emits a message *key* plus the numbers it interpolates (`dynamic_pricing/constants.py`), and the sentence is assembled at render time in `apps/web` from `apps/web/messages/{en,vi}.json`. This is why the frontend cannot just add English strings inline for anything the engine can produce — every emittable key needs a translation in both locale files, or backend tests fail (`test_every_emittable_key_has_a_translation` et al.). `make lint` additionally parses every message with the real ICU compiler.

Vietnamese is the default locale (`/vi`); the operator who uses this daily is Vietnamese.

### Config & versioning

Pricing configuration is a versioned JSON blob (D6), not scattered settings — a config version travels with every recommendation snapshot so a past decision stays reproducible even after the config changes. Migrations happen by reseed, not Alembic (D24): there is no live-tenant data to preserve yet.

### Desktop packaging

`make bundle` exports the web app statically and packages both apps into one PyInstaller binary that serves its own frontend (D32) — the same FastAPI app that would run on a server. `apps/web` therefore builds with `output: "export"` in mind; do not add anything that requires a Next.js server runtime (middleware, server actions that need a live Node process) without checking this constraint.
