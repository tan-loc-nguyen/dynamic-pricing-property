# Engineering Decisions

Deliberate technical choices made while building this MVP, with the reasoning
and the cost of reversing each one. Business assumptions live in
[`../ASSUMPTIONS.md`](../ASSUMPTIONS.md); this file is about *how the system is
built*, not *what it believes about pricing*.

---

## D1 — Demo data is a PMS provider, not a fixture file

`MockPMSProvider` implements the same `PMSProvider` interface Blue Jay will,
and demo data is loaded through the same `sync_pms()` normalization path.

**Why:** an adapter boundary that is never exercised rots. Because every single
run — including every test — flows through the boundary, the seam is proven
continuously rather than aspirationally. Wiring Blue Jay becomes "implement
four methods", with no changes anywhere downstream.

**Cost to reverse:** none; it *is* the cheap option.

---

## D2 — A `Room` is a room *type* with N units, not a physical unit

Occupancy is only a meaningful pricing signal when a bucket contains more than
one sellable unit. With one unit per room, occupancy is always 0% or 100% and
the whole occupancy factor collapses into a binary.

**Why:** it makes occupancy, booking pace and pickup expressible.

**Risk:** if Luminous prices each apartment individually (plausible for a small
luxury portfolio), this is the wrong grain. Flagged as **S1** in ASSUMPTIONS.md.
Reversing means setting `units_total = 1` and rethinking the occupancy factor —
the data model itself still holds.

---

## D3 — Feature Engine is DB-aware, but contains no pricing policy

`FeatureEngine` reads the database and bulk-loads lookups; it does not know
what any measurement is *worth*.

**Why:** a pure function taking pre-loaded data would be more textbook, but the
ceremony (repository + DTO layers) buys nothing at this size. The important
boundary — measurement vs. policy — is preserved: `FeatureEngine` computes
"occupancy is 78%", `PricingEngine` decides that is worth ×1.08.

The only config it reads is *how to measure* booking pace (window length,
expected pickup), never *how to price* it.

---

## D4 — Every feature is Optional, and absence is recorded

`PricingContext` carries a `missing: tuple[str, ...]`. Engines apply a neutral
factor for a missing signal and say so in the explanation.

**Why:** the alternative — defaulting silently to 1.0 — is indistinguishable
from "this signal was measured and had no effect". An operator must be able to
tell "the market is flat" from "we cannot see the market".

---

## D5 — Market index compares the market to itself

`market_price_index = median competitor price for the date ÷ median competitor
price for that room across the horizon`.

**Why:** dividing by *our* base price would make the market factor partly a
function of our own pricing, which is circular — raise our base price and the
market would appear cheaper. Using the market's own central tendency keeps the
signal independent.

**Trade-off:** it measures *relative* market strength across dates, not whether
we are absolutely cheap or expensive. Both are useful; the second needs a
competitor set validated by the operator first (**A22**).

---

## D6 — Pricing configuration is a versioned JSON blob

Each save writes a new `PricingConfiguration` row; recommendations store the
`config_version` that produced them.

**Why:** the shape of the rules *will* change after operator interviews. A JSON
payload absorbs that without a migration, and versioning means any past
recommendation stays traceable to the exact rules that produced it. The cost —
no column-level DB validation — is acceptable because `merge_config()`
guarantees a fully-populated config reaches the engine even from a partial
form submission.

---

## D7 — Recalculating resets a decision only if the number changed

When recommendations regenerate, a prior Accepted/Overridden status carries
forward **only if the newly recommended price is identical**. If the price
moved, the row returns to Pending.

**Why:** a decision was made about a specific number. If that number changes,
the operator's approval no longer applies and they should look again. Silently
keeping "Accepted" against a different price would misrepresent what they
agreed to.

---

## D8 — Approving a price updates the local record; nothing is pushed anywhere

Accept/Override writes the final price onto `StayDateInventory.current_price`.
No OTA or PMS write occurs — `PMSProvider.push_price()` exists as a visible
seam and deliberately raises.

**Why:** autonomous OTA updates are an explicit non-goal, but the loop needs to
*feel* closed for the demo. After accepting, the current price becomes the new
price and the next recommendation reasons from there.

---

## D9 — Decisions belong to a stay date, not to a recommendation run

`OperatorDecision` rows are never copied when recommendations regenerate. The
detail view looks decisions up by `(room_id, stay_date)`.

**Why:** this was a real bug found during testing — carry-forward used to clone
decision rows, so History gained a duplicate entry on every recalculation and
the audit trail inflated without bound. A decision is a historical fact that
happened once. Pinned by a regression test.

---

## D10 — The frontend holds no pricing logic

Every number the UI renders was computed in Python. React formats and
arranges; it never derives a price, a factor or a threshold. Override reasons
and factor labels are served from the API (`dynamic_pricing/constants.py`).

**Why:** the moment a multiplier appears in a `.tsx` file, there are two
sources of truth and the finance team's engine can no longer be swapped in
cleanly.

---

## D11 — Bands carry explicit inclusive/exclusive semantics

`_band_for(..., inclusive=)`: occupancy and pace bands are exclusive
(`max: 0.30` means "below 30%"), lead-time bands are inclusive
(`max_days: 3` means "3 days or fewer").

**Why:** the two genuinely differ — a continuous ratio versus a whole-day
count. An earlier version fudged this with a `+0.5` offset and produced an
off-by-one that put D-3 in the "4–7 days" band. Naming the semantics made the
bug impossible to reintroduce.

---

## D12 — SQLite with a WAL pragma and FK enforcement

SQLite is right for a localhost MVP. Foreign keys are off by default in SQLite,
so a connect-time `PRAGMA foreign_keys=ON` is set, along with WAL journaling so
the API and a CLI reseed can coexist.

**Cost to reverse:** low — SQLAlchemy means moving to Postgres is a URL change
plus a migration story.

---

## D13 — Startup seeds the database automatically

The FastAPI lifespan handler calls `bootstrap()`, which creates the schema and
demo data if the database is empty, and never blocks startup on failure.

**Why:** it makes `make dev` genuinely one command. A demo that requires
"now run the migrate step" is a demo that fails in front of a client.

---

## D14 — The public-web collector fails loudly and is off by default

`PublicWebMarketDataProvider` checks `robots.txt` before fetching, refuses OTA
hosts outright, does not retry on 401/403/429, and is disabled unless
explicitly enabled.

**Why:** the goal is to prove the pipeline `external source → normalization →
market signal → pricing engine`, not to build a scraper. Failing loudly with a
remediation message is more useful than a fragile extractor that silently
returns junk into a pricing model.

---

## D15 — Python 3.13 rather than the system's 3.14

The bootstrap script prefers the newest Python in 3.10–3.13 and falls back to
`python3`. At build time the machine's default was 3.14, where some binary
wheels were not yet universally available.

**Cost to reverse:** none — remove the preference list once the ecosystem
catches up.
