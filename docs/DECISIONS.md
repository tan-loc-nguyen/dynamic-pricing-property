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

## D2 — Pricing grain is RoomType x StayDate; physical units are inventory only

Luminous defines rates by room category and Blue Jay distributes by room type,
so an individual apartment does not get its own rate. `PhysicalRoom` exists
because the 22 units still drive inventory and occupancy, and so unit-level
overrides remain possible later without reshaping the model.

**Superseded D2 (pre-refactor):** the earlier model used a generic `Room` that
conflated "room type" and "physical unit", with an invented multi-property
portfolio. The client document replaced that guess with fact: one property,
22 apartments, three categories.

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
competitor set validated by the operator first (**ASSUMPTIONS U12**).

---

## D6 — Pricing configuration is a versioned JSON blob

Each save writes a new `PricingConfiguration` row; recommendations store the
`config_version` that produced them.

**Why:** the shape of the rules *will* change after operator interviews. A JSON
payload absorbs that without a migration, and versioning means any past
recommendation stays traceable to the exact rules that produced it. The cost —
no column-level DB validation — is acceptable because `prepare_config()`
(save) and `preview_config()` (unsaved) guarantee a fully-populated, coerced
config reaches the engine even from a partial form submission. See D30's
sibling guard, `test_no_config_reaches_an_engine_without_passing_the_boundary`.

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

Accept/Override writes the final rate onto `StayDateInventory.current_net_rate`.
No OTA or PMS write occurs — `PMSProvider.push_rate()` exists as a visible
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

---

# Refactor decisions — Revenue Intelligence direction

## D16 — The rate book is data, not configuration

Luminous' seasonal MIN/BASE/MAX table lives in its own module
(`pricing/rate_book.py`), its own table (`seasonal_rate_bands`), its own API
namespace (`/api/rate-book`) and its own screen — deliberately **not** inside
the `PricingConfiguration` JSON blob with the experimental settings.

**Why:** the single most important distinction in this product is
validated-fact vs. unvalidated-guess. If both live in one config object, that
distinction survives only as a comment. Separate storage makes it structural:
you cannot accidentally reset the client's rates while resetting demo defaults,
and the UI can honestly label each.

An operator edit flips a band's `source` from `CLIENT_VALIDATED` to
`OPERATOR_EDITED`, so provenance is never silently lost.

## D17 — Season selects a band; it never multiplies one

There is no seasonality factor in the pricing engine. The rate table already
encodes the season, so a seasonality multiplier on top would count it twice.

The legacy engine's `_factor_season` was **removed** rather than left disabled,
so it could not be re-enabled by a config change and reintroduce the
double count. Pinned by `test_seasonality_is_not_applied_twice`.

## D18 — Occupancy and lead time are not independent factors

They are folded into one signal — **pace position** — via the booking curve:

    pace_gap = actual_otb_occupancy − BookingCurve(category, season, days_to_arrival)

**Why:** 30% sold at D-90 and 30% sold at D-2 are opposite situations. Pricing
occupancy directly means the same number pulls the rate the same way in both.
And rewarding occupancy, lead time *and* pace separately would pay three times
for one underlying demand condition.

The engine therefore has no `occupancy`, `lead_time` or `urgency_discount` step at all —
asserted by a test, because it would be easy to "helpfully" add one back.

## D19 — Additive percentages, not stacked multipliers

Each signal contributes percentage points of the BASE rate, summed, bounded,
then applied.

**Why:** four multipliers of 1.15 compound to 1.75 in a way nobody predicts.
Four additive percentages are bounded by construction and an operator can check
the arithmetic by hand — which matters more than mathematical elegance in a
product whose entire value is trust.

When the total exceeds the bound, each contribution is scaled *proportionally*
rather than truncated, so the displayed lines still sum to the applied total.
A breakdown that does not add up destroys the trust the breakdown exists to
build.

## D20 — Market confidence is derived, not asserted

`score_confidence()` computes HIGH/MEDIUM/LOW/UNUSABLE from what is actually
known about an observation: price basis, room category, length of stay, tax and
fee treatment, promotion status.

**Why:** a provider that declares its own data trustworthy is worthless. Because
confidence is derived from metadata completeness, `PublicWebMarketDataProvider`
is *structurally incapable* of producing anything above LOW — a generic web page
does not state those things. Manual entry can reach HIGH because a human can.

Low-confidence evidence is stored and displayed as an **ignored** line in the
breakdown, not hidden. The operator sees it was considered and why it was
excluded.

## D21 — NET and OTA prices are different quantities

Every rate field is `*_net_rate`. `current_ota_price` is nullable and never
derived — it is populated only if a real guest-facing price is known.

The `NET → channel sell` transformation is a documented seam that is
deliberately **unimplemented**, because inventing commission percentages would
produce plausible, wrong, guest-facing prices. See ASSUMPTIONS U13.

## D22 — Shadow Mode is the product, not a setting

`mode: "shadow"` is the default and the only supported value.
`PMSProvider.push_rate()` exists and deliberately raises.

**Why:** the next real-world experiment is comparing system recommendations
against operator decisions. That experiment is only valid if the system is not
also changing the prices. Automation is a later decision that this data should
justify — not precede.

## D23 — Outcomes are never invented in production

`RecommendationOutcome.is_synthetic` separates demo rows from measurement, and
`outcome_summary()` reports the two counts separately, marking readiness `False`
while only synthetic data exists.

**Why:** this dataset is the evidence base for every future modelling decision.
A single unflagged synthetic row would poison it. Demo outcomes are generated
only for past stay dates and always flagged.

## D24 — Migration by reseed, not by Alembic

The refactor renamed tables and columns wholesale (`rooms` → `room_types`,
`*_price` → `*_net_rate`) and added six entities. SQLite here is a disposable
local demo database, so the migration is a model change plus `make reseed`.

**Cost to reverse:** introducing Alembic later is straightforward; doing it now
would have added ceremony to a database with no production data in it.

## D25 — Demo occupancy is generated *around* the booking curve

`MockPMSProvider` imports the same `DemoBookingCurveProvider` the feature engine
measures against, and disperses occupancy around it.

**Why:** the first version generated occupancy independently, so almost every
date read "well behind pace" and the demo showed systematic discounting — a
convincing-looking artefact of two unrelated generators. Deriving demo
occupancy from the curve makes pace gaps spread realistically either side of
zero. It is a slight layering smell (a provider importing from `features/`)
accepted deliberately: demo data that contradicts the model teaches the wrong
thing.

The curve also carries a `MAX_EXPECTED_OCCUPANCY` ceiling, because a 22-unit
building is not expected to be 100% sold on arrival day — without it, the
season multiplier pushed the D-0 expectation to 100% and every near date looked
behind pace.

## D26 — A cleared Settings field means "use the default", never `null`

`_deep_merge` ignores a `None` override when the default is non-null, and
`generate_recommendations` refuses to commit a run that priced nothing.

**Why:** the Settings number inputs emit `null` when cleared, `ConfigIn.payload`
is deliberately an unvalidated free-form dict (the config shape must evolve
without a schema migration), and `float(None)` raises inside the engine. The
per-row `except Exception` then absorbed every failure, so clearing one field
returned HTTP 200 with "all recommendations were recalculated" while the run
dropped from 273 rows to 6 and the dashboard went blank with no error anywhere.

Two guards, because they fail differently: the merge guard stops the null ever
reaching the engine, and the empty-run guard stops *any* future config error
from silently replacing a good run with an empty one. Keys whose default is
already `None` keep their nullability.

## D27 — Filters belong in SQL, before the LIMIT

History and recommendation filters were applied in Python after
`.limit()`/`.offset()`, so they filtered one already-truncated page rather than
the whole set: filtering History by room category returned nothing for a
category whose activity was older than the 200 most recent decisions.

Column-backed filters (`room_type_id`, `room_category` via a `RoomType`
subquery) now go into the `WHERE` clause. Free-text search spans denormalised
snapshot fields and cannot, so it is applied before paging instead, and the
page is a slice of the matches.

## D28 — Band boundary semantics must be chosen per signal, and mirrored in the UI

Pickup bands are **inclusive**; pace and occupancy bands are **exclusive**.

**Why:** `recent_pickup` cannot go below zero, so the smallest possible
`pickup_delta` is exactly `-expected_pickup` — sitting precisely ON the
threshold. With a strict `<` the "Pickup stalled" band was unreachable and a
date with no bookings at all was priced as merely "slowing". This is the same
class of bug as D11's lead-time off-by-one, which is why the semantics are now
a named argument rather than an implicit convention.

`lib/format.ts` mirrors these boundaries exactly. When it did not, the table
row read "On pace" while the drawer showed a +4% "Ahead of pace" line for the
same date — the breakdown contradicting the summary is precisely the failure
this product cannot afford.

## D29 — One engine, no version-numbered names

The legacy multiplicative engine and the `v1`/`v2` naming are gone. There is one
`RateBandPricingEngine`, registered under the neutral key `default`.

**Why:** this is an MVP. Keeping a superseded engine "for comparison" cost more
than it returned — it carried its own config subtree (48 of the 88 numeric
config leaves), its own coercion paths, its own tests, and it produced two of
the review findings entirely on its own (a dead config key, and eleven casts
with no boundary protection). None of that was buying anything a client demo
needs.

Version-numbered class names also age badly: `V2` stops meaning anything the
moment a third exists, and it implies a migration story this product does not
have. The engine is named for what it does — it anchors on a rate band.

**What is deliberately kept:** the registry. The brief requires a finance-
authored engine to be able to replace this one without touching the UI,
database, providers or history, and that seam is `register_engine()`. A registry
holding one engine still proves the seam; a registry holding a dead engine only
proves we kept a dead engine.

`engine_version` is still recorded on every recommendation and decision, so a
past price remains traceable to the logic that produced it.

**Version equivalence, for anyone auditing an older database.** The recorded
value changed with the rename and denotes the same logic on both sides:

| Recorded `engine_version` | Means |
|---|---|
| `v2.0.0` | `PricingEngineV2`, pre-rename |
| `1.0.0` | `RateBandPricingEngine`, post-rename — **identical pricing logic** |
| `v1.0.0` | the deleted legacy multiplicative engine — NOT equivalent |

Nothing migrates old rows, because the demo database is rebuilt by `make
reseed`. This table is the mapping, and it is written down because
`engine_version` IS the traceability mechanism: an auditor holding a `v2.0.0`
row has no other way to connect it to the code.

## D30 — The engine emits message keys and numbers, never sentences

`Adjustment` carries `label_key` + `params`. `PricingResult.explanation` and
`PricingRecommendation.explanation` are gone, and so is `Adjustment.reason`.
The sentence is composed at render time by `next-intl`, from
`apps/web/messages/{en,vi}.json`.

**Why:** the client is Vietnamese, and the explanation *is* the product. The
engine used to compose finished English prose and persist it, so the one thing
the operator most needs to read was the one thing no frontend i18n library
could reach — it arrives at React as an opaque string.

Structuring it turned out to be the *smaller* job than translating on the
backend, because it removed the only thing that would have forced a Python i18n
system at all. Everything else the API returns is either already code-keyed
(override reasons, seasons, confidence levels — the frontend looks the code up
in its own message file) or real-world data that must never be translated
(property names, competitor names, operator notes).

**Configuration problems go the same way.** They were initially left in English
on the grounds that translating them needed a second (Python) i18n toolchain.
That was the wrong constraint: the strings were already structured — a field
path, a reason, a value — so `validate_config` and `coerce_config` now emit
`{code, path, params, message}` and the UI renders them from the same message
files. The English `message` stays, for logs and the 422 body. `PROBLEM_CODES`
is checked against both locales the same way `EMITTABLE_MESSAGE_KEYS` is.

**What is deliberately NOT translated:** provider remediation text, engine
descriptions, and the exception signature recorded on a stay date the engine
could not price. All three are aimed at whoever fixes the problem rather than
at the operator.

**Operator-authored text passes through.** Pace and pickup bands are editable,
so a shipped band carries a stable `key` (`well_behind`, `stalled`) that the
message files translate, while a band an operator renames or invents has
`label_key: null` and its own wording is shown verbatim. Translating it would
put words in their mouth; matching it to a neighbouring band — the bug D26's
`_default_at` already had to fix once — would be worse.

**Where the two percentages are shown.** `raw_dynamic_pct` and
`bounded_dynamic_pct` are on every snapshot for reproducibility, but only the
`dynamic_bound` step renders them — so an operator sees "signals totalled X%,
scaled back to Y%" exactly when the ±15% bound binds, and not otherwise. On a
row clamped by the seasonal MIN/MAX instead, no percentage for the signals
total is shown; the clamp step names the unclamped RATE rather than a
percentage, which is the more useful figure and the same information. The
per-signal lines still add up by hand either way, which was the original point.

**The guardrail that makes this safe:** `test_every_emittable_key_has_a_translation`
checks every key `EMITTABLE_MESSAGE_KEYS` declares against BOTH locale files,
and `test_the_locales_describe_exactly_the_same_things` checks the two files
have identical key sets. A missing Vietnamese string is a test failure, not a
blank line discovered in front of a client. `test_vietnamese_is_actually_translated`
additionally fails if the Vietnamese file is mostly a copy of the English one.

**A duplication this removed.** `paceLabel()` and `pickupLabel()` in
`lib/format.ts` re-derived the engine's bands from thresholds in TypeScript —
the D28 bug. The engine now publishes `pace_label_key` / `pickup_label_key` on
the recommendation itself, the table and the drawer both read that same key
through `useAdjustmentText`, and the second derivation is deleted rather than
kept in sync.

**Vietnamese is the default locale.** The operator who uses this daily is
Vietnamese; English is for non-Vietnamese stakeholders. `i18n/routing.ts`,
one line.

**The rate-band sentence gates on provenance, not on having numbers.** When no
band covers a date the feature engine substitutes the ROOM TYPE's fallback
rates, and those columns are NOT NULL — so an "are there numbers" test is
always true, and an early version described a room-type guess in the shape of a
validated band with a dash where the season should be. The select now keys on
`rate_band_source`, because "did this come from the validated book?" is the
question the sentence actually answers.

**ICU has its own grammar, and Python cannot see it.** An apostrophe before a
brace is an ICU *escape*, so `'{event_name}'` rendered the literal text
`{event_name}` on every event row while every Python guard passed — the key
existed, the placeholder was declared, the engine supplied it. `make lint` now
parses every message with the real ICU compiler
(`apps/web/scripts/check-messages.mjs`), and a test rejects `'{` outright.

**Two deliberately unreachable messages.** `pace.no_band` and
`recent_pickup.no_band` need an empty band list, which `validate_config`
rejects, so nothing reaches them in production —
`test_the_scenarios_below_reach_every_emittable_key` only reaches them via a
config passed straight to the engine. They stay. The distinction that matters
is whether unreachability changes *behaviour* or only changes *coverage*: an
unreachable pricing band silently misprices, whereas an unreachable message
whose absence would leave a case with no sentence at all is a fallback. Do not
delete these citing the reachability test.

**A structural guard cannot see English that was never keyed.** The message
tests check that keys exist, are satisfiable, are rendered and are not missing —
all of which are blind to a hardcoded English string with no key at all. Only
looking at the rendered page finds those, and a visual pass turned up eleven of
them after every test was green: the whole Settings advisory block, the Rate
Book statement, three API-served vocabularies (`priceBasis`, `promotion`,
`inclusion`) whose `{code, label}` pairs were being rendered by label, the
season notes, and a hardcoded English month array. Two of those vocabularies had
been deleted as "speculative" by the dead-key test — the key was unused
*because* the UI was showing the server's English instead.

**No middleware.** Locale detection would live in middleware, which does not
exist under `output: "export"`. Since packaging this as a single-process local
app is still open, locale is a `[locale]` route segment with
`generateStaticParams` and an explicit switcher.

## D31 — The shell is one viewport tall; each pane scrolls inside its own box

`body` and the flex shell are `h-screen overflow-hidden`; `main` scrolls, the
sidebar scrolls, and on Rate Review the table gets its own frame with a sticky
header and pinned pagination.

**Why:** the sidebar is a flex sibling of `main`, so a long table grew the
document and dragged the sidebar down with it — 3,200px tall on a 45-row page,
putting its Shadow Mode and unvalidated notices thousands of pixels below the
fold. Those two notices are the standing reminder of what this product is; a
layout that scrolls them away defeats them.

**Two things that do not work here, both tried:**

- `min-h-full` on the page with `min-h-[22rem]` on the table card. A minimum
  height lets the CONTENT height win, so the card grows to its full 2,675px and
  the page scrolls again — exactly the state being fixed. The parent needs a
  *definite* height (`h-full`) for `flex-1` to divide.
- `position: sticky` on `<thead>`. Inconsistently supported; the cells are what
  actually stick, so it lives on `<th>` alone rather than in two places.

**The trade-off, stated plainly:** the frame is the viewport minus the chrome
above it — page padding, header, status banner, summary cards and filters come
to ~424px. On a 1080px screen the table gets ~550px (roughly nine rows); on an
806px laptop viewport it gets 280px (four). If that proves too tight in use,
the reclaimable space is the summary cards (116px) and the filter card's own
border and padding (88px) — not the table.


## D32 — One binary that serves its own frontend, not an Electron shell

`make bundle` exports the Next app to static HTML, mounts it on the FastAPI app
at `/`, and PyInstaller packages the result as a single ~11MB executable. The
operator double-clicks it; their own browser opens on the Vietnamese dashboard.

**Why not Electron.** The client already has a browser. Electron would add
80–150MB and ~250MB of RAM for a window, a second toolchain, a second signing
problem, and the sidecar lifecycle bug where the Python child outlives a killed
shell and keeps holding the port. Most of all it is the one option that does
not pay forward: the shell is thrown away the day this becomes a web app,
whereas *this* build is the same FastAPI application that would run on a
server. Going hosted means deleting the `webbrowser.open` call.

**Why this was cheap.** The frontend was already six `"use client"` pages with
no route handlers and no server actions, and `generateStaticParams` +
`setRequestLocale` were already in place. D30's "no middleware" was chosen for
exactly this and had already been paid for.

**Four things that had to change, each of which fails silently:**

- **`app/page.tsx` called `redirect()`.** That is a SERVER redirect and there
  is no server in a static export — Next exports the route as an *error
  document*, so bare `/` rendered blank. It forwards on the client now, which
  `LocaleRedirect` already did for pre-i18n URLs.
- **The API host was baked into the bundle.** `lib/api.ts` fell back to
  `http://127.0.0.1:8000`, which appeared in five chunks. The runner takes
  whatever port is free, so `.env.production` sets `NEXT_PUBLIC_API_URL=/` and
  every call is relative. The empty string is meaningful there ("same origin"),
  which is why the fallback tests for *absence* rather than falsiness.
- **The database would have been deleted on exit.** `--onefile` unpacks into a
  temp directory that PyInstaller removes when the process ends, and
  `REPO_ROOT` resolves inside it. `packaging.user_data_dir()` sends a frozen
  build to `%APPDATA%` / `~/Library/Application Support` instead; a checkout
  still uses `data/`.
- **The entry script cannot be a package module.** A frozen entry runs as
  `__main__` with no package context, so `runner.py`'s relative imports raised
  before anything else. `packaging/entrypoint.py` imports it by absolute name.

**The API banner moved from `/` to `/api`.** Starlette matches routes before
mounts, so a route at `/` would have served JSON to every operator who opened
the address. The mount is registered last for the same reason.

**A console window, deliberately.** It prints the address and the data
directory, and closing it is how the operator stops the app. A windowed build
gives them no feedback and no way to quit short of Task Manager.

**What is NOT solved.** PyInstaller cannot cross-compile — a Windows `.exe`
must be built on Windows — so `.github/workflows/release.yml` runs a
`macos-latest` + `windows-latest` matrix. And the binary is unsigned: macOS
Gatekeeper blocks it until the operator right-clicks → Open, and Windows
SmartScreen shows "Unknown Publisher". EV certificates stopped bypassing
SmartScreen in 2024, so paying does not buy an instant clean launch. For a
demo to one known client, warn them rather than buy a certificate.

**Secrets cannot live in here.** PyInstaller archives extract with
`pyinstxtractor-ng`, encrypted ones included. There is nothing to hide today —
demo mode is credential-free and Blue Jay's key is read from the environment —
and that has to stay true: when Blue Jay access arrives, its key belongs on a
server, not in a binary handed to the client.

**If a real window is ever wanted:** pywebview first (pure Python, no new
toolchain, ~10 lines, same binary), and Tauri rather than Electron if it must
be a properly installed desktop app.
