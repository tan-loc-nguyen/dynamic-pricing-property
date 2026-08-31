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
at `/`, and PyInstaller packages the result as a single ~22MB executable. The
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
  The give-away was the SIZE: that build came out at 11MB rather than 22MB,
  because PyInstaller's static analysis could not resolve the relative import
  and so never followed the graph into `main` — most of the app was simply not
  in there. A frozen build that is suspiciously small is missing code.

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

## D33 — "No data" and "could not get the data" must never render the same

Two failures in different layers turned out to be one bug:

- **The adapter.** An error envelope from Blue Jay — revoked key, quota, a
  shape change — parsed as zero reservations. Zero is not neutral here: it
  means 0% occupancy on every date in the horizon, which is the strongest
  DISCOUNT signal the engine has. So a failed call read as "price everything
  down as far as the bounds allow", and the sync reported success.
- **The UI.** The activity screen caught nothing, so an unreachable API and a
  genuinely empty decision history rendered identically — and one of them means
  "you have not made any decisions yet".

The shape: **absence of data and failure to obtain data collapsing into one
appearance.** It is worse than an ordinary silent failure because the collapsed
value is not neutral — it is a confident claim, and in both cases the claim
biased toward action (discount everything; you have done nothing).

The rule, applied wherever data is fetched:

1. An unreadable or error response RAISES. It is never coerced to an empty
   collection. `_check_envelope` does this for Blue Jay, on the live path and
   the snapshot path both — sanitisation had been erasing the envelope, which
   made a captured failure into a file that asserted an empty hotel every time
   it replayed.
2. A genuinely empty result must still be allowed to be empty. A check that
   rejects errors by also rejecting legitimate emptiness is a worse bug than
   the one it replaces, so both directions get a test.
3. In the UI, a fetch failure gets its own visible state. Rendering nothing is
   not a neutral default; it is a claim that there is nothing.

Related: D30's note that a structural guard cannot see English that was never
keyed. Same family — the check passes because the thing it would have caught
never reached it.

## D34 — Observed behaviour outranks the vendor document, and the document is tracked as wrong

The Blue Jay API document was wrong about the base URL, the auth header name,
the room-type field name, the occupancy field names, what `meta.total` means,
and it omitted a date-range limit and a silently-ignored filter. Its one worked
occupancy sample fails its own arithmetic.

So the rule is not "prefer the API" — it is that **every claim carries its
provenance**, and a claim we have observed beats one we have only read. Both
contract documents now mark each statement VERIFIED or UNVERIFIED, and untested
parameters say "never tested" rather than being omitted, because omission reads
as support.

**Why this needed writing down.** After the first live window, both documents
still asserted things the window had disproved — one said `/reservation` "never
returned data to us" directly beneath the section listing the 122 rows it
returned. A reference that contradicts itself is worse than none: a reader
following the stale half acts on findings we had already overturned. The same
applied to `UNRESOLVED_MAPPINGS`, which is RENDERED to the operator and was
still asking questions we had answered.

**The guard.** `test_the_unresolved_list_does_not_carry_settled_questions`
fails if the operator-facing list mentions something we verified, and its
counterpart fails if trimming drops a real blocker. Staleness in a document is
invisible; staleness in a list a test can read is not.

**The technique worth reusing.** The reservation `status` field returns
Vietnamese prose while the input filter takes integers, and the document maps
neither to the other. Filtering on each integer and reading back the string
produced the whole mapping in seven calls — a question we were about to email a
vendor about. It generalises to any enum an API filters on but documents only
one side of.

**What did NOT change.** The engine, the rate book, Shadow Mode, and the
NET/OTA separation are untouched. Verification changed how we READ Blue Jay,
not what we do with the numbers.

---

## D35 — The unit of pricing work is a DATE RANGE, not a night

The calendar grid is gone. The Rate page takes a from/to range and shows one
tile per room tier: average suggested NET, and how many units still have a free
night. Clicking a tile opens the same drawer, and accepting writes **one price
to every night in the range**.

**Why.** The grid asked the operator to scan ~91 cells and work out which needed
attention. The range asks the opposite question — *"these nights, this tier,
what should I charge?"* — and answers it in one number per tier. A single day is
just a range of length one, so there is one code path rather than two.

**What it cost.** `attention.ts` and the whole "which dates need review" concept
went with the grid. That was the grid's job and nothing inherited it; the
per-night occupancy strip in the drawer (D36) covers the part that mattered.

**Deleted, not adapted:** `PricingCalendar.tsx`, `CalendarLegend.tsx`,
`calendarModel.ts`, `attention.ts`, `RecommendationDrawer.tsx`. The bucketing
helpers survived as `lib/buckets.ts` because the market report still offers the
same day/week granularity and must bucket dates identically — two views of one
period that disagreed about where a week starts would be worse than either
being wrong alone.

---

## D36 — A range may not cross a season, and the drawer shows the nights disagreeing

**The rule.** One accepted price cannot sit inside two validated bands. 2BR
Premium is capped at 2,700,000 through October and based at 3,000,000 from
November; a 25 Oct – 5 Nov average of ~2,800,000 is legal in one and above the
ceiling in the other. So the picker stops at the boundary and
`check_one_season()` refuses anyway — a UI guard is a convenience, this is an
invariant.

Compared on **bounds**, not on the season key, so the wrapping Nov–Dec–Jan
season is one continuous stretch: 20 Dec – 5 Jan is legitimate.

**The strip.** Bulk accept can hide a range whose first ten nights are healthy
and whose last four are empty — the average reads "slightly behind" and one
flat price goes to all of them. The drawer draws one bar per night underneath
the averaged curve, so that disagreement is visible *before* the operator
commits. Averaging is linear, so the breakdown still reconciles exactly; the
rounding of the average is folded back into the existing rounding line, because
lines that do not sum to the total above them destroy the only thing that panel
exists to build.

**Bulk accept OVERWRITES existing decisions without prompting** — the
operator's explicit call. `OperatorDecision.group_id` ties one action's rows
together so a fortnight reads as one entry in the activity log while remaining
fourteen per-night records, which is what Shadow Mode measures and what an
outcome attaches to. Protecting a prior manual override stays a small change:
the `decision` field already distinguishes accepted from overridden.

---

## D37 — Seasons are data, and the calendar travels WITH the rate book

Seasons moved from a hardcoded constant to a `seasons` table an operator edits.
The partition rule the constant asserted at import
(`assert len(MONTH_TO_SEASON) == 12`) is now enforced on save: contiguous runs
of whole months, covering the year exactly once, wrap allowed.

**The bug this was really about.** `SeasonalRateBook.lookup()` took its *bands*
from the database and its *month-to-season mapping* from the module global.
Once seasons are editable those are two different answers that disagree
silently — the band table saying September is high season while the mapping
still says low, and a date quoted from the wrong band with nothing failing. The
calendar is now constructor state on the book. Same family as a predicate with
fewer states than the thing it reads.

**MAX became optional** (ASSUMPTIONS U9). An empty ceiling means the season
imposes none — *not* unbounded: the dynamic layer is already capped, so
`base × (1 + bound)` is the real limit. Measured on the client table, MAX binds
before that bound on 13 of 15 bands; on High 2 Regular and Premium the bound
binds first and those MAX values were already unreachable. An absent ceiling
must survive the round trip as absent: `float(None)` raises and `float(v or 0)`
writes a ceiling of ZERO, which would clamp every recommendation for that
season down to nothing.

**Labels lost their months.** `vocab.seasons` read "Low Season 1 (May–Jun)".
The moment a boundary moves, that label asserts something the data contradicts,
so names come from messages and months come from data.

---

## D38 — Market evidence informs the report; it never moves a price

The Market page is one chart: our suggested price against the market band, per
night. Comp-set management moved to Settings (it configures a report, not a
pricing input) and the raw observations table was cut.

**Confidence gate unchanged.** Everything the collector can reach is `LOW` and
the engine's gate is `MEDIUM`, so the market line in the drawer reads
"considered, excluded". Promoting it is a one-line change once there is a
reason — after watching the chart track reality, not before.

**Dated collection.** A source may be a template carrying `{checkin}` and
`{checkout}` into the request; it is then fetched once per night (capped at 30
per run, and the cap is reported) and each price is filed under the night it
was asked about. Without that the collector stamps a price with a stay date it
never asked the site for, and one number stands in for the whole range — a flat
line wearing the costume of a market band.

**The status line replaces the deleted table.** A collector that stopped
extracting prices and a market with nothing to say both leave the band thin. The
run report distinguishes three states — never ran, ran and found nothing, ran
and found prices — because a refused collection reported as "0 prices found"
would send the operator hunting for a broken competitor site when the collector
was simply never switched on. D33, again.
