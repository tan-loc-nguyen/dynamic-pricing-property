# Dynamic Pricing Property

**An explainable Revenue Intelligence Copilot above Blue Jay PMS**, for
Luminous Luxury Apartments.

Blue Jay already does rule-based yield management. This product does not
duplicate that. It sits **above** Blue Jay and answers a different question:
*given how this date is actually booking, what NET rate should we be at — and
why?* Blue Jay remains the system of record and the execution layer.

> ### Two kinds of number live in this system, and they are never mixed
> - **Client-validated** — Luminous' seasonal MIN/BASE/MAX **NET** rate table.
>   Real business data. The engine anchors on it.
> - **Unvalidated** — the dynamic layer on top (pace, pickup, events, market).
>   Invented by the engineering team so the product could be built.
>   See **[ASSUMPTIONS.md](ASSUMPTIONS.md)**.

---

## Quick start

```bash
make setup    # one-time: checks/installs prerequisites, installs deps, seeds the demo DB
make dev      # starts the API and the web app together
```

Open **<http://localhost:3000>**.

| Service | URL |
|---|---|
| Web app | http://localhost:3000 |
| API | http://127.0.0.1:8000 |
| API docs | http://127.0.0.1:8000/docs |

`make dev` alone is enough — it runs setup if needed and seeds the database on
API startup. Prerequisites: Python 3.10+ and Node 18+; `make setup` tells you
the exact install command for your platform, or `AUTO_INSTALL=1 make setup`
installs them for you. `make test` runs 233 tests.

---

## The pipeline

```
Blue Jay / Mock data
   ↓  normalization                (providers → domain rows)
Feature Engine                     (measures: occupancy, pickup, market)
   ↓
Booking / Pace Intelligence        (expected occupancy → pace gap)
   ↓
Seasonal Rate Book                 (CLIENT-VALIDATED MIN/BASE/MAX NET)
   ↓
Pricing Engine                     (bounded dynamic layer, clamped to band)
   ↓
Recommendation                     (with a reproducible snapshot)
   ↓
Human Decision                     (accept / override + reason)
   ↓
Outcome                            (what actually happened)
```

### Why it is built this way

**Why the rate book is validated input, not a model.**
Luminous already has a seasonal rate table proven by real operation. The client
was explicit: *"the base-rate layer does not need modelling… load the rate table
as a lookup table."* So the system loads it, and spends its effort on the layer
that does not exist yet.

**Why seasonality is not applied twice.**
The rate table already encodes the season — a July rate is different from a
September rate because it is in the table. Multiplying a seasonality factor on
top of a seasonal band would count the season twice. Season **selects** the
band; it never scales it. There is no seasonality factor in the engine at all.

**Why NET and OTA prices are separate.**
Luminous' table is NET — what they receive. A guest-facing OTA price is that
plus commission, taxes, fees and promotions. Comparing a NET rate to a scraped
OTA headline is comparing two different quantities. Every field is named
`*_net_rate`, and the NET → channel-sell transformation is a documented seam
that is deliberately **not** implemented, because no real commission rules exist
yet (ASSUMPTIONS U13).

**Why occupancy must be read against lead time.**
30% sold at D-90 is healthy. 30% sold at D-2 is a problem. Occupancy alone is
ambiguous, so the engine never prices it directly. Instead:

```
expected_occupancy = BookingCurve(category, season, days_to_arrival)
pace_gap           = actual_on_the_books − expected_occupancy
```

Pace gap is the primary demand signal. Because occupancy and lead time are
folded into it, no single demand condition gets paid for three times.

**Why generic web prices are low-confidence.**
The same headline number can be a refundable OTA sell price including taxes for
a 3-night stay, or a one-night NET rate. Only one is comparable. Confidence is
*derived* from the metadata available, and only `MEDIUM`+ evidence may move a
rate. Low-confidence observations are still shown — the operator sees they were
considered and why they were excluded.

**Why Shadow Mode comes first.**
Nothing is pushed to Blue Jay or any OTA. Recommendations are recorded, the
operator decides, and the divergence between the two is captured. That
divergence — plus outcomes — is what will justify automation later. Automating
before measuring would be pricing real inventory on unvalidated assumptions.

---

## The pricing engine

```
band          = SeasonalRateBook.lookup(room_category, stay_date)   [VALIDATED]
base_net      = band.base

delta_pct     = pace_position                                        [UNVALIDATED]
              + recent_pickup
              + event
              + qualified_market        (low-confidence excluded)
              + day_of_week             (OFF by default)

delta_pct     = clamp(delta_pct, −15%, +15%)          ← bound on the whole layer
recommended   = clamp(base_net × (1 + delta_pct), band.min, band.max)
              → round to nearest 10,000 VND
```

Properties that matter:

- **Additive, not multiplicative.** Each signal contributes percentage points of
  the BASE rate. Four stacked multipliers compound unpredictably; four additive
  percentages are bounded and an operator can add them up by hand.
- **Deterministic.** Same inputs and config → same rate. No LLM, no ML, no
  randomness, no wall-clock reads.
- **Always inside the validated band.** The dynamic layer can never take a rate
  outside MIN/MAX, and rounding cannot push it out either.
- **Bounded, and the bound is honest.** When signals exceed the limit, every
  contribution is scaled proportionally so the displayed breakdown still sums to
  the applied total.
- **Graceful.** A missing signal contributes 0% and says so, rather than
  crashing or being silently indistinguishable from "measured, no effect".
- **Pluggable.** One engine ships today. Adding a finance-authored one is
  `register_engine("finance", …)` plus one lookup — no change to the UI,
  database, PMS integration, market layer or history. The registry exists for
  that swap, not to keep old engines around.

Example, as the operator sees it:

```
Seasonal base rate — High Season 1 (Jul–Aug)     [Validated]   2,300,000 ₫
  2BR Regular, BASE 2,300,000 NET (band 2,100,000–2,600,000)

Well behind pace                        −8.0%      −184,000 ₫
  70% sold with 0 days to arrival; the curve expects 92% — 22 points behind

Pickup accelerating                     +2.0%       +46,000 ₫
  2 bookings in the last 7 days versus 1.0 expected

Market signal                           +0.4%       +10,235 ₫
  Comparable rate 1% above comp-set baseline (3 × MEDIUM confidence)

Rounding                                            −2,235 ₫
─────────────────────────────────────────────────────────────
Recommended NET rate                              2,170,000 ₫
```

> This formula is not claimed to be optimal. Every dynamic threshold is
> UNVALIDATED.

---

## Screens

| Screen | Purpose |
|---|---|
| **Rate Review** | RoomType × StayDate table: availability, OTB occupancy, D-, pace position, pickup, current vs recommended NET, position in band, market confidence, status |
| **Rate Book** | The client-validated seasonal MIN/BASE/MAX NET table, editable, with provenance per band |
| **Dynamic Rules** | The experimental layer only — pace, pickup, events, market, bounds — with a live preview and a permanent reminder that none of it is validated |
| **Market** | Comp-set management and observations with full basis metadata and derived confidence |
| **Events** | Manually curated demand calendar |
| **History** | Every accept/override with the system's recommendation beside the operator's rate |

---

## Languages

The app ships in **Vietnamese and English**. Vietnamese is the default, because
the operator who uses this daily is Vietnamese; English is one click away in the
sidebar for anyone else.

```
/vi              Vietnamese (default)
/en              English
```

Everything the operator reads is translated, **including the pricing
explanation** — the part that matters most and the part a frontend i18n library
normally cannot reach. The engine does not compose sentences: each step of the
breakdown carries a message key plus the numbers that key interpolates, and the
sentence is assembled at render time in whichever language is being viewed.
Currency and dates follow the locale too (`2.300.000 ₫` vs `2,300,000 ₫`).

Translations live in `apps/web/messages/{en,vi}.json`. Three tests keep them
honest:

| Test | Catches |
|---|---|
| `test_every_emittable_key_has_a_translation` | a key the engine can emit with no string in one of the locales |
| `test_the_locales_describe_exactly_the_same_things` | the two files drifting apart |
| `test_vietnamese_is_actually_translated` | `vi.json` being largely a copy of `en.json` |

A missing Vietnamese string is a **test failure**, not a blank line discovered
during a client demo.

**What is deliberately not translated:** property, competitor and event names,
and operator-written notes — translating real-world data would be a bug. Two
gaps remain in English and are documented rather than hidden: Settings
validation messages and API error details. See **D30** in
[docs/DECISIONS.md](docs/DECISIONS.md).

---

## Demo mode

Default, no credentials, no network. Seeded on first run:

- **1 property, 3 room categories, 22 apartments** (the real Luminous shape)
- **91 stay dates** forward, crossing a season boundary, plus 45 days of history
- **~1,600 bookings** with realistic creation timestamps, so pickup is measured
- **15 validated rate bands**, **4 demo events**, **3 comp-set properties**,
  **~1,200 market observations** at mixed confidence

Every teaching scenario is present: ahead of pace, behind pace, stalled and
surging pickup, event dates, strong/weak market, **low-confidence-only market**,
**no market data at all**, MIN clamp, MAX clamp, and the dynamic bound binding.

---

## Blue Jay

**Status: integration boundary only.** The API documentation was not available
(the client document confirms access was requested and is *awaiting
confirmation*), so no endpoints, schemas or field mappings have been invented.

`BlueJayPMSProvider` conforms fully to the `PMSProvider` contract, reads
credentials from environment variables only, and raises `ProviderUnavailable`
with actionable remediation — which the UI surfaces before falling back to demo
data. See **[docs/BLUEJAY.md](docs/BLUEJAY.md)** for the 15 unresolved mappings.

Two are hard blockers, not just mapping work:
- **units per room category** — without it, occupancy and therefore pace break;
- **booking creation timestamps** — without them, pickup goes permanently
  neutral and no historical booking curve can be fitted.

No credentials are committed. `.env` and `private/` are gitignored.

---

## Outcome tracking

Every recommendation persists a reproducible snapshot: features, rate band,
engine version, config version. `RecommendationOutcome` attaches what actually
happened — units booked, realised NET rate, final occupancy, cancellations.

Real outcomes require post-stay data from Blue Jay and **are never invented**.
Demo outcomes exist so the dataset's shape is visible, and every one is flagged
`is_synthetic`; the readiness endpoint reports synthetic and real counts
separately and only counts real ones as ready for evaluation.

---

## Testing

```bash
make test    # 233 tests
```

Covers: every month → season mapping (including the January wrap), all 15
validated bands, no seasonality double-counting, no independent occupancy or
lead-time factor, booking-curve shape and bounds, pace-gap arithmetic, positive
and negative pace adjustments, bounded totals with proportional scaling, MIN and
MAX clamps, rounding that cannot break a clamp, low-confidence market ignored,
high-confidence market applied, missing data neutrality, decision persistence,
snapshot reproducibility, and a regression test for decision-history duplication.

---

## Documentation

| Document | Contents |
|---|---|
| **[ASSUMPTIONS.md](ASSUMPTIONS.md)** | Validated client input vs. unvalidated experiment, with the question to ask for each |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Engineering decisions and trade-offs |
| [docs/BLUEJAY.md](docs/BLUEJAY.md) | Integration status, unresolved mappings, field-mapping worksheet |
| [docs/MARKET_DATA.md](docs/MARKET_DATA.md) | Providers, the confidence model, and honest limitations |

---

## Known limitations

**Pricing**
- The booking curve is demo data, not Luminous history — the weakest link in the
  whole model (ASSUMPTIONS U1).
- Every dynamic threshold is a guess.
- Day-of-week is disabled because nothing justifies a value yet.
- One flat impact per event level; no shoulder-day effect.
- No cost, tax, commission or margin modelling — the engine optimises NET rate,
  not profit.
- No rate plans, length-of-stay pricing or per-channel pricing.
- No elasticity estimation. Outcomes are captured but not yet analysed.

**Integrations**
- Blue Jay is a boundary only.
- The public-web collector fetches URLs verbatim without injecting stay dates,
  so its output is LOW confidence by construction and never moves a rate.
- The demo comp set is invented.

**Product**
- No authentication, users or permissions.
- Single tenant, localhost only.
- Shadow Mode only — no write-back anywhere.
- The 22-unit split across categories is a placeholder.

---

## What to validate next

The ten highest-value questions are at the end of
**[ASSUMPTIONS.md](ASSUMPTIONS.md)**. The two that unlock the most: **how the 22
apartments split across categories**, and **whether booking history with
creation timestamps can be exported from Blue Jay** — the second turns the
guessed booking curve into a measured one.
