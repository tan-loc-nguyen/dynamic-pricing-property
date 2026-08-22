# Dynamic Pricing Property

**`dynamic-pricing-property`** — an explainable pricing copilot for Luminous
Luxury Apartment.

For every apartment and every upcoming night it shows the current price, a
recommended price, and — most importantly — **exactly why**. The operator stays
in charge: review the reasoning, then accept the recommendation or override it
with a reason.

> ### ⚠️ The pricing rules are provisional
> Pricing Engine V1 runs on **unvalidated demo assumptions** invented by the
> engineering team. None of them came from Luminous. They exist so the product
> can be evaluated before the real business rules are known, and they are
> designed to be replaced without touching code.
> See **[ASSUMPTIONS.md](ASSUMPTIONS.md)**.

---

## Quick start

```bash
make setup    # one-time: checks/installs prerequisites, installs deps, seeds the demo DB
make dev      # starts the API and the web app together
```

Then open **<http://localhost:3000>**.

| Service | URL |
|---|---|
| Web app | http://localhost:3000 |
| API | http://127.0.0.1:8000 |
| API docs (Swagger) | http://127.0.0.1:8000/docs |

`make dev` on its own is enough — if setup has not been run it runs it first,
and the database is created and seeded automatically on API startup.

**Prerequisites** are checked (and where possible installed) by `make setup`:
Python 3.10+ and Node.js 18+. If something is missing the script tells you the
exact command for your platform. `AUTO_INSTALL=1 make setup` lets it install
via Homebrew/apt itself. `make check` reports status without installing.

### Other commands

```bash
make test      # pricing + feature engine + API workflow tests (98 tests)
make reseed    # wipe and rebuild the demo data
make api       # backend only
make web       # frontend only
make check     # verify prerequisites
make clean     # remove venv, node_modules and the database
```

---

## Demo mode

**Demo mode is the default and needs no credentials, no integrations and no
network access.** `DATA_PROVIDER=mock` generates a realistic synthetic Luminous
portfolio and the app is immediately usable.

Seeded on first run:

- **3 properties** — Saigon Riverside (D1), Thao Dien Residences (Thu Duc),
  Da Nang Beachfront
- **8 room types**, 2–8 units each
- **61 upcoming stay dates** per room (~490 priced nights), plus 45 days of
  history for historical features
- **~2,700 bookings** with realistic booking timestamps, so booking pace is a
  genuine measurement rather than a fabricated number
- **~2,500 market observations** across three competitors per property

The demo deliberately contains every teaching scenario, so pricing behaviour is
visible rather than theoretical:

| Scenario | Where to see it |
|---|---|
| Normal weekday / Friday / Saturday / Sunday | any week in the table |
| High occupancy (≥85%) and very low occupancy (≤20%) | occupancy column |
| Strong and weak booking pace | booking-pace signal in the drawer |
| Short lead time (D-0…D-3) and long (D-60+) | the `D-` column |
| Close to check-in **and** still empty | urgency discount in the breakdown |
| Event dates | "Event" chip — 16 Sep, 29 Sep |
| Strong / weak market | "Market" column |
| **No market data at all** | rows showing "No data" → neutral factor |
| **Minimum price floor binding** | Thao Dien Duplex Loft, weak dates |
| **Maximum price cap binding** | Riverside Two-Bedroom Suite, strong dates |
| **Compounding guardrail binding** | rare; visible in the breakdown |
| Operator has mispriced a date | 3 Sep (too cheap), 14 Sep (too dear) |

---

## Architecture

```
apps/
├── api/                       FastAPI + Python
│   └── dynamic_pricing/
│       ├── providers/         ← external world lives ONLY here
│       │   ├── pms/           PMSProvider: Mock | BlueJay
│       │   └── market/        MarketDataProvider: Mock | Manual | PublicWeb
│       ├── services/sync.py   normalization: provider DTOs → domain rows
│       ├── features/          FeatureEngine → PricingContext
│       ├── pricing/           PricingEngine interface, registry, V1, defaults
│       ├── services/          recommendations, configuration
│       ├── routers/           HTTP layer (thin)
│       └── models.py          SQLAlchemy domain model
└── web/                       Next.js 15 + TypeScript + Tailwind
```

Data flows in one direction:

```
Data providers → normalization → FeatureEngine → PricingEngine
              → RecommendationService → SQLite → REST API → UI
```

**Frontend** — Next.js 15 (App Router), TypeScript, Tailwind v4. It holds *no*
pricing logic; every number it renders was computed in Python.

**Backend** — FastAPI, SQLAlchemy 2.0, SQLite. No auth (explicit non-goal).

**Feature Engine** (`features/`) — turns raw operational data into signals:
occupancy, days to check-in, booking lead time, booking pace, historical
occupancy and price, day of week, weekend flag, season, event flag, market
reference price and market index. It measures; it never prices. Every signal is
optional, and missing signals are recorded so the pricing engine can apply a
neutral factor **and say so**.

**Pricing Engine** (`pricing/`) — a registry of interchangeable implementations
behind one interface:

```python
PricingEngine.calculate(context: PricingContext, configuration: dict) -> PricingResult
```

`PricingEngineV1` is deterministic and side-effect free. To plug in the finance
team's engine, subclass `PricingEngine`, call `register_engine("finance", …)`,
and change one lookup. **No change is needed to the UI, database, PMS
integration, market integration, recommendation history or feedback flow.**

**PMS providers** — `MockPMSProvider` and `BlueJayPMSProvider` behind
`PMSProvider`. Demo data travels the same normalization path Blue Jay will, so
the boundary is exercised on every run rather than being decorative.

**Market providers** — `MockMarketDataProvider`, `ManualMarketDataProvider`,
`PublicWebMarketDataProvider` behind `MarketDataProvider`.

---

## Pricing Engine V1

```
recommended = base price
              × day-of-week factor
              × occupancy factor
              × booking-pace factor
              × lead-time factor        (+ urgency rule if near AND empty)
              × seasonality factor
              × event factor
              × market factor
            → compounding guardrail  (clamp total to 0.70–1.60)
            → minimum / maximum price bounds
            → rounding                (nearest 10,000 VND)
```

Properties that matter:

- **Deterministic.** Same inputs and configuration always produce the same
  price. No LLM, no ML, no randomness, no wall-clock reads.
- **Explainable.** Every step is persisted as a `PricingAdjustment` with its
  factor, the price before and after, the delta, and a plain-English reason.
  `price_before × factor == price_after` holds to the cent, so an operator can
  re-derive any line by hand.
- **Bounded.** Seven multipliers can compound absurdly, so the total is clamped
  before bounds are applied.
- **Graceful.** A missing signal yields a neutral ×1.00 factor and an
  explanation saying the signal was unavailable — never a crash, and never
  silently indistinguishable from "measured, no effect".

Example breakdown as shown to the operator:

```
Base price                                          1,350,000 ₫
Saturday                        ×1.15               +202,500 ₫
Healthy occupancy (67%)         ×1.00     no effect         —
Very strong booking pace        ×1.10               +155,250 ₫
Last minute (0–3 days out)      ×0.95                −85,387 ₫
Shoulder season                 ×1.00     no effect         —
Market signal                   ×1.014               +22,713 ₫
Rounding                        ×1.003                +4,924 ₫
─────────────────────────────────────────────────────────────
Final recommendation                                1,650,000 ₫
```

> **This formula is a demo scaffold.** It is not claimed to be economically
> optimal, or even correct for Luminous.

---

## Settings — changing the rules without changing code

**Pricing Rules** in the app edits every assumption: base/min/max overrides,
rounding, the compounding guardrail, all seven day-of-week multipliers,
occupancy bands, booking-pace bands and window, lead-time bands, the urgency
rule, monthly seasonality, the event multiplier, and market sensitivity, clamps
and thresholds.

- A **live preview** re-prices a sample stay date against your unsaved edits and
  shows the effect in VND.
- **Save & recalculate** writes a new configuration version and regenerates all
  recommendations.
- **Reset to demo defaults** restores the provisional values.

Configuration is **versioned**: every recommendation records the
`config_version` that produced it, so any past price stays traceable. A saved
change affects new recommendations immediately — no deploy, no code edit.

If a recalculation changes a price the operator had already decided on, that
row returns to **Pending** — their approval was for a specific number.

---

## Human-in-the-loop

Each recommendation is **Pending**, **Accepted** or **Overridden**.

- **Accept** stores the recommendation id, recommended price, final price,
  previous price, timestamp, engine version and configuration version.
- **Override** additionally stores the operator's price, a reason (Occupancy
  strategy · Competitor pricing · Property-specific knowledge · Promotion ·
  Special event · Owner constraint · My judgment · Other) and an optional note.

Approving a price updates the local record. **Nothing is pushed to any PMS or
OTA** — autonomous OTA updates are an explicit non-goal. The seam
(`PMSProvider.push_price`) exists and deliberately raises.

**History** shows every decision with the system's recommendation beside the
operator's price. That divergence is the most valuable data this MVP produces:
it is what will eventually tell us where the engine is wrong.

---

## Blue Jay

**Status: the integration boundary exists; it is not wired to a live API.**

The Blue Jay API documentation and credentials were **not present** in this
repository or anywhere on the build machine. Per the brief, no endpoints,
schemas, field mappings or auth mechanisms have been invented.

`BlueJayPMSProvider` conforms fully to the `PMSProvider` contract, reads
credentials from environment variables only, and raises `ProviderUnavailable`
with actionable remediation — which the UI surfaces as a status banner before
falling back to demo data. **Demo mode is unaffected.**

To enable it once the documentation arrives, set `DATA_PROVIDER=bluejay` plus
the `BLUEJAY_*` variables in `.env` and implement the four `TODO(bluejay)`
markers. **See [docs/BLUEJAY.md](docs/BLUEJAY.md)** for the full list of
unresolved mappings, the integration-call question list, and a field-mapping
worksheet.

**No credentials are committed anywhere.** `.env` is gitignored;
`.env.example` holds empty placeholders.

---

## Market data

Three interchangeable providers — see **[docs/MARKET_DATA.md](docs/MARKET_DATA.md)**.

1. **Mock** (default) — deterministic synthetic competitor prices, including
   dates with *no* data so the neutral-factor path is visible.
2. **Manual** — the operator records competitor name, stay date, price, source
   URL and notes on the **Market Data** screen. Always available; the mode to
   trust.
3. **Public web (prototype, off by default)** — fetches operator-supplied public
   URLs, **checking robots.txt first**, identifying itself honestly, and
   refusing OTA hosts (Airbnb, Booking.com, Agoda, Expedia, Trip.com,
   TripAdvisor) outright. No CAPTCHA solving, no login bypass, no anti-bot
   evasion, no identity rotation, no retry storms.

The market factor is computed as
`1 + sensitivity × (market_price_index − 1)`, clamped, and ignored entirely
when there are too few or too stale observations.

---

## Graceful degradation

Optional integrations can fail without breaking the product:

| Failure | Behaviour |
|---|---|
| Blue Jay unreachable or unconfigured | Status banner explains it; sync falls back to mock data |
| Market provider fails | Neutral market factor (×1.00) + explicit explanation |
| Any single signal missing | Neutral factor for that signal, recorded as a "blind spot" |
| One row fails to price | Skipped and counted; the run completes |
| Database empty on startup | Seeded automatically |

---

## Testing

```bash
make test
```

98 tests covering determinism and repeatability, every pricing factor in
isolation, band boundaries, missing-data neutrality, min/max bounds, the
compounding guardrail, rounding (including that rounding never breaks a bound),
configuration sensitivity, breakdown arithmetic, feature measurement, and the
full API workflow — plus a regression test for the decision-history duplication
bug found during development.

---

## Documentation

| Document | Contents |
|---|---|
| **[ASSUMPTIONS.md](ASSUMPTIONS.md)** | Every provisional business assumption, its value, why it was chosen, and **the question to ask the operator**. This is the interview checklist. |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Engineering decisions and their trade-offs |
| [docs/BLUEJAY.md](docs/BLUEJAY.md) | Integration status, unresolved mappings, field-mapping worksheet |
| [docs/MARKET_DATA.md](docs/MARKET_DATA.md) | Market providers, the signal, and honest limitations |

---

## Known limitations

**Pricing model**
- Every multiplier and threshold is a guess. See ASSUMPTIONS.md.
- Expected booking pace is a flat constant (A13) — the weakest assumption in
  the model. It needs a real pickup curve from Luminous' history.
- Seasonality is global, not per property — Da Nang and Ho Chi Minh City almost
  certainly differ. Tet is not modelled and moves every year.
- One flat event multiplier for all events, with no shoulder-day effect.
- Factors are multiplicative and independent; genuine interactions (except the
  explicit urgency rule) are not modelled.
- No cost, tax, commission or margin modelling — the engine optimises headline
  rate, not profit.
- No rate plans, no length-of-stay pricing, no per-channel pricing.
- No price-elasticity estimation and no outcome tracking yet: the system cannot
  currently tell whether a recommendation was *right*.

**Integrations**
- Blue Jay is a boundary only (see above).
- The public-web collector fetches URLs verbatim and does not inject stay dates,
  so its prices are a rough level indicator rather than a true nightly rate.
- Competitor sets in demo mode are invented.

**Product**
- No authentication, users or permissions (explicit non-goals).
- Single-user, single-tenant, localhost only.
- No write-back to any PMS or OTA.
- History is a plain list; no analytics on override patterns yet.

---

## What to validate with the operator next

The ten highest-value questions are listed at the end of
**[ASSUMPTIONS.md](ASSUMPTIONS.md)**. In short: where today's prices come from,
the real floors and ceilings, the weekend premium, the occupancy level that
triggers action, what happens to a date that is close and still empty, what a
normal booking pace looks like, which events actually matter, who the real
competitors are, and how different Da Nang is from Ho Chi Minh City.
