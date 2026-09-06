# Rate Drawer Night Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Rate page drawer two scopes over one payload — the existing range view, and a per-night view that can be inspected and priced individually — and fix the averaged "why the price changed" breakdown so it stops printing impossible numbers and unlabelled rows.

**Architecture:** No new API endpoint. `/api/rate/range` already loads everything night mode needs and throws most of it away at serialization; the fix is to widen that serialization so one fetch powers both modes. Accepting a single night reuses `apply_to_range` with `start == end`, which is the identity case of the existing range aggregation. The breakdown fix is a night-count field plus ICU plural branches in the message files — the averaging code itself is not changed.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy / pytest on the backend; Next.js 15 App Router / React / TypeScript / Tailwind v4 / Radix / next-intl / Vitest + React Testing Library on the frontend. SQLite with migration-by-reseed.

**Spec:** `docs/superpowers/specs/2026-09-06-rate-drawer-night-mode-design.md`

---

## PHASE 0 — Orientation (read this before writing any code)

**This section is not a task. It is the context handoff.** If you are a fresh
session with no history of this project, do everything in Phase 0 before
starting Phase 1. If you are a subagent handed a single phase, still do Phase 0
steps 1–4; they take a few minutes and they are the difference between a change
that fits this codebase and one that gets reverted.

### 0.1 What this product is

An explainable revenue-management copilot for one short-term rental property
(Luminous Luxury Apartments), sitting above the Blue Jay PMS. It recommends a
NET room rate per date, explains the recommendation in plain language, and lets
an operator accept or override it. **It is decision-support, not an autopilot** —
nothing is ever pushed back to Blue Jay or any OTA (Shadow Mode, D22).

Two kinds of number live here and must never be mixed:

- **Client-validated** — the seasonal MIN/BASE/MAX NET rate table. Real business
  data. The engine anchors on it and never scales it.
- **Unvalidated** — the dynamic layer on top (pace, pickup, events, market).
  Invented by the engineering team so the product could exist. Every one of
  these is catalogued in `ASSUMPTIONS.md`.

The operator who uses this daily is Vietnamese. **Vietnamese (`/vi`) is the
default locale**, not an afterthought.

### 0.2 Required reading, in this order

- [ ] **Step 1: Read the spec this plan implements**

`docs/superpowers/specs/2026-09-06-rate-drawer-night-mode-design.md`

It contains the investigation evidence (including real data proving the
original bug report was partly a false positive) and the reasoning behind every
decision below. **The plan argues from the spec — if they disagree, the spec
wins and you should stop and say so.**

- [ ] **Step 2: Read the two CLAUDE.md files**

```bash
cat CLAUDE.md
cat apps/web/CLAUDE.md
```

Non-negotiable rules from these that this plan touches:

| Rule | Consequence for this work |
|---|---|
| **D10 — the frontend holds no pricing logic** | Any percentage, multiplier or threshold the UI shows is computed in Python. Do NOT compute the per-night delta in a `.tsx` file. |
| **Engine emits message keys + numbers, never sentences (D30)** | You will edit `messages/{en,vi}.json`. You will never build a sentence in Python or TypeScript. |
| **Every emittable key needs en AND vi** | Backend tests fail otherwise. |
| **Never ALL-CAPS labels via CSS or copy** | `uppercase tracking-wide` is banned outside `<th>` in dense grids. |
| **Tailwind colour scales are redefined** | `amber-*` is clay/ochre, `violet-*` is muted plum and is reserved for "overridden" ONLY, `emerald-*` is forest green. Do not reason from the class name — check `app/globals.css`. |
| **Karla for functional text; Fraunces only for identity moments** | The night date heading is functional. Use the default sans. |
| **No decorative icons** | Do not add icons that aren't carrying information. |
| **`output: "export"`** | Nothing may require a Next.js server runtime. No middleware, no server actions. |

- [ ] **Step 3: Read the decisions this work amends**

```bash
grep -n "## D10\|## D17\|## D19\|## D22\|## D30\|## D33\|## D35\|## D36" docs/DECISIONS.md
```

Then read **D35** (the unit of pricing work is a DATE RANGE) and **D36** (a
range may not cross a season, and the drawer shows the nights disagreeing) in
full. This plan deliberately amends D36 and deliberately preserves D35.

- [ ] **Step 4: Read the code you are about to change**

```bash
# backend — the whole pipeline for this feature, ~600 lines total
cat apps/api/dynamic_pricing/services/rate_range.py       # pure aggregation math
cat apps/api/dynamic_pricing/services/rate_page.py        # DB loading
cat apps/api/dynamic_pricing/services/rate_decisions.py   # writing decisions
cat apps/api/dynamic_pricing/routers/rate.py              # the HTTP surface

# frontend
cat apps/web/components/RangeDrawer.tsx                   # 465 lines, about to be split
cat apps/web/components/viz.tsx                           # RateBand, PaceChart, OccupancyStrip, PriceContribution
cat apps/web/lib/adjustments.ts                           # ICU rendering + its failure mode
cat apps/web/app/\[locale\]/customisation/page.tsx        # THE Tabs pattern to copy
```

### 0.3 Environment setup and verification

- [ ] **Step 5: Verify the toolchain works before changing anything**

```bash
make check                       # prerequisites without installing
make test                        # backend pytest — MUST be green before you start
cd apps/web && npm test          # frontend Vitest — MUST be green before you start
cd apps/web && npm run check:messages
```

If `make setup` has never been run on this machine, run it first. If the demo
database is missing or stale, `make reseed`.

**Record the passing backend test count.** It is 535 at the time of writing.
Every phase below adds tests; none may remove or break an existing one.

- [ ] **Step 6: Reproduce the bug yourself, with real data**

This is the single most useful five minutes available to you. It proves the
environment works and shows you exactly what you are fixing.

```bash
cd apps/api && .venv/bin/python -c "
from dynamic_pricing.db import SessionLocal
from dynamic_pricing.services.rate_page import load_range
from dynamic_pricing.services.configuration import get_active_configuration
from datetime import date
s = SessionLocal()
inc = int(((get_active_configuration(s).payload or {}).get('rounding') or {}).get('increment') or 0)
agg, nights, avail, rt = load_range(s, room_type_id=2, start=date(2026,9,6), end=date(2026,9,12), rounding_increment=inc)
print('=== PER NIGHT ===')
for n in nights:
    print(f'{n.stay_date}  {n.recommended_net_rate:>11,.0f}')
print(f'AVERAGE: {agg.average_recommended_net_rate:,.0f}')
print('=== AGGREGATED ROWS (note pace appears 5x) ===')
for c in agg.adjustments:
    print(f'   {c.code:<16} {str(c.label_key):<36} {c.delta:>+12,.0f}')
print('=== the impossible numbers ===')
for c in agg.adjustments:
    if 'days_to_arrival' in c.params: print('  days_to_arrival =', c.params['days_to_arrival'])
    if 'recent_pickup' in c.params:   print('  recent_pickup   =', c.params['recent_pickup'])
"
```

Expected output includes `days_to_arrival = 4.5` and `recent_pickup = 2.3333`.
Those are two of the three defects Phase 4 fixes.

> **Note on dates:** the demo DB is seeded relative to today. If today is past
> 2026-12-05 the range above will be empty — run `make reseed` and use a range
> starting today.

### 0.4 How each phase runs

Every phase is one TDD cycle, handed to one subagent:

1. **Read** the phase in this plan, and the spec sections it names.
2. **Investigate** — open every file listed under **Files**, read the
   surrounding code, and confirm the line numbers still match. Line numbers in
   this plan are from 2026-09-06 and drift as earlier phases land.
3. **Red** — write the tests, run them, confirm they fail *for the stated
   reason*. A test that fails with `ImportError` when you expected an assertion
   failure means you wrote the wrong test.
4. **Green** — write the minimum implementation, run the tests, confirm pass.
5. **Regress** — run the FULL suite, not just your new tests.
6. **Review** — reread your own diff against the phase's "Review focus" list.
7. **Commit** with the message given.

### 0.5 Rules that apply to every phase

- **Surgical changes.** Touch only what the phase asks for. Do not reformat
  adjacent code, do not "improve" comments you did not write, do not refactor
  something that is not broken. Every changed line must trace to this plan.
- **Match the surrounding style.** This codebase writes substantial explanatory
  comments on non-obvious decisions, in prose, explaining *why* rather than
  *what*. Match that density. Do not add comments that restate the code.
- **Never invent a pricing number.** If a value is not served by the API, it
  does not get displayed.
- **Do not delete pre-existing dead code.** Mention it; leave it.
- **Frontend tests are not in `make test`.** Run them separately from
  `apps/web`.

---

## Global Constraints

- **Python 3.13** (not the system 3.14 — D15). Always `apps/api/.venv/bin/python`.
- **Node/Next.js 15** with `output: "export"` and `trailingSlash: true`. No
  server runtime may be introduced.
- **Locales:** `en` and `vi`, both required for every key. Vietnamese is default.
- **Currency:** VND, NET rates. `formatVND` renders `2.300.000 ₫`.
- **Colour tokens:** unpriced → `amber-*`; hand-tuned/overridden → `violet-*`
  (reserved for this state alone); positive/accepted → `emerald-*`; accent →
  `brand-*` (antique brass); neutral text → `ink-*` (warm charcoal).
- **No ALL-CAPS labels.** Sentence case everywhere.
- **No motion** on mode or night switching.
- **`tnum`** class on every numeric column.
- Test commands, verbatim:
  - backend all: `make test`
  - backend one: `cd apps/api && .venv/bin/python -m pytest tests/path::name -q`
  - frontend all: `cd apps/web && npm test`
  - frontend one: `cd apps/web && npx vitest run path/to/File.test.tsx`
  - lint: `make lint`
  - messages: `cd apps/web && npm run check:messages`

---

## File Structure

| File | Responsibility | Phases |
|---|---|---|
| `apps/api/dynamic_pricing/services/rate_range.py` | pure aggregation math; gains `nights_covered` and `clamped` | 1, 2 |
| `apps/api/dynamic_pricing/services/rate_page.py` | DB → domain objects; carries decision status and clamp through | 2 |
| `apps/api/dynamic_pricing/services/rate_decisions.py` | writes decisions; gains override preservation | 3 |
| `apps/api/dynamic_pricing/routers/rate.py` | HTTP surface; widened `nightly` serialization | 1, 2, 3 |
| `apps/web/messages/{en,vi}.json` | every rendered sentence and label | 4, 7, 8 |
| `apps/web/lib/types.ts` | payload contract | 5 |
| `apps/web/lib/api.ts` | client calls | 5 |
| `apps/web/components/viz.tsx` | `OccupancyStrip` becomes the picker; `PriceContribution` gains badges | 6 |
| `apps/web/components/rangeDrawer/RangeDrawerShell.tsx` **(new)** | header, tabs, footer, data fetching | 7 |
| `apps/web/components/rangeDrawer/RangeScopeBody.tsx` **(new)** | range-mode sections | 7 |
| `apps/web/components/rangeDrawer/NightScopeBody.tsx` **(new)** | night-mode sections | 7 |
| `apps/web/components/RangeDrawer.tsx` | thin re-export preserving the import path | 7 |
| `docs/DECISIONS.md` | D40 | 9 |

---

## PHASE 1 — `nights_covered` on every contribution

**Spec sections:** "Night badges", "The breakdown fix".

**Why this is first:** it is pure arithmetic on an existing structure, it has
the strictest existing invariant to protect, and every later phase depends on
the field existing.

**Files:**
- Modify: `apps/api/dynamic_pricing/services/rate_range.py` (`Contribution` dataclass ~line 26-43; `aggregate_range` grouping loop ~line 167-193; rounding fallback ~line 218-224)
- Modify: `apps/api/dynamic_pricing/routers/rate.py` (adjustment serialization ~line 193-208)
- Test: `apps/api/tests/test_rate_range.py`

**Interfaces:**
- Produces: `Contribution.nights_covered: int` (default `1`). Every
  `Contribution` returned by `aggregate_range` carries the number of priced
  nights that contributed to it. Serialized as `"nights_covered"` on each item
  of the `adjustments` array in `GET /api/rate/range`.

### Context you need

`aggregate_range` groups per-night contributions by `(code, label_key)` — NOT by
`code` alone. The comment at `rate_range.py:163-166` explains why, and that
reasoning still stands: `pace` carries eight different label keys and
collapsing them would state one night's story as the whole range's.

The grouping loop already builds `members: dict[key, list[Contribution]]`, so
the night count for a group is exactly `len(rows)`.

**The invariant you must not break:** `base + sum(every averaged delta) ==
average_recommended_net_rate`, exactly. It is enforced by
`test_the_averaged_breakdown_sums_to_the_averaged_price`. Run that test
constantly.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/test_rate_range.py`:

```python
def test_each_averaged_row_reports_how_many_nights_it_covers():
    """A row that describes 2 of 7 nights must say so.

    Grouping is by (code, label_key), so one factor can produce several rows.
    Without a night count the operator reads any one of them as describing the
    whole range -- which is the defect this field exists to fix.
    """
    nights = [
        night(1, recommended=2_000_000, contributions=(("pace", 0),)),
        night(2, recommended=2_000_000, contributions=(("pace", 0),)),
        night(3, recommended=2_000_000, contributions=(("pace", 0),)),
    ]
    # Give night 3 a different label_key for the same code, so the group splits.
    nights[2] = replace(
        nights[2],
        adjustments=(
            Contribution(
                code="pace",
                label_key="adjustments.pace.well_behind",
                label="pace",
                delta=0.0,
            ),
        ),
    )
    result = aggregate_range(nights, rounding_increment=0)
    covered = {c.label_key: c.nights_covered for c in result.adjustments}
    assert covered["adjustments.pace"] == 2
    assert covered["adjustments.pace.well_behind"] == 1


def test_an_unpriced_night_is_not_counted_in_any_row():
    """Unpriced nights are excluded from every average, so they cannot be
    counted as covered by a row they never contributed to."""
    nights = [
        night(1, recommended=2_000_000, contributions=(("pace", 0),)),
        night(2, recommended=0, contributions=(), priced=False),
    ]
    result = aggregate_range(nights, rounding_increment=0)
    pace = next(c for c in result.adjustments if c.code == "pace")
    assert pace.nights_covered == 1
    assert result.unpriced_nights == 1


def test_a_single_night_row_covers_one_night():
    """The identity case. Night mode accepts one night as a range of length
    one, so this must not report the whole range."""
    result = aggregate_range(
        [night(1, recommended=2_000_000, contributions=(("pace", 0),))],
        rounding_increment=0,
    )
    assert all(c.nights_covered == 1 for c in result.adjustments)


def test_a_synthesised_rounding_row_reports_the_whole_range():
    """When no night carried a rounding line, aggregate_range invents one to
    absorb the drift from rounding the average. That row describes every
    priced night, not one of them -- a default of 1 would be a lie."""
    nights = [
        night(1, recommended=2_000_000, contributions=(("pace", 33_333),)),
        night(2, recommended=2_000_000, contributions=(("pace", 33_333),)),
        night(3, recommended=2_000_000, contributions=(("pace", 33_333),)),
    ]
    result = aggregate_range(nights, rounding_increment=10_000)
    rounding = next(c for c in result.adjustments if c.code == "rounding")
    assert rounding.nights_covered == 3
```

Add `replace` to the imports at the top of the test file:

```python
from dataclasses import replace
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_rate_range.py -q -k "nights_covered or covers_one_night or not_counted_in_any_row or synthesised_rounding"
```

Expected: FAIL with `AttributeError: 'Contribution' object has no attribute 'nights_covered'`.

If instead you get a `NameError` on `replace`, you missed the import.

- [ ] **Step 3: Add the field to the dataclass**

In `apps/api/dynamic_pricing/services/rate_range.py`, in the `Contribution`
dataclass, after `params`:

```python
    #: How many PRICED nights this row was averaged from. Grouping is by
    #: (code, label_key), so one factor can produce several rows -- and a row
    #: that covers two of seven nights reads as though it described the whole
    #: range unless it says otherwise. Defaults to 1 so a per-night row, which
    #: is built straight from the database and never averaged, is correct
    #: without being touched.
    nights_covered: int = 1
```

- [ ] **Step 4: Set it in the grouping loop**

In `aggregate_range`, in the `for key in groups:` loop, add to the
`Contribution(...)` construction:

```python
                nights_covered=len(rows),
```

- [ ] **Step 5: Set it on the synthesised rounding row**

In the `else:` branch of the `for i, c in enumerate(averaged):` loop:

```python
            averaged.append(
                Contribution(
                    code=ROUNDING_CODE,
                    label="Rounding",
                    label_key="adjustments.rounding",
                    delta=drift,
                    nights_covered=len(priced),
                )
            )
```

Note the `replace(c, delta=c.delta + drift)` branch above it needs **no**
change — `replace` preserves `nights_covered`, which is exactly why the comment
there warns against rebuilding the row field by field.

- [ ] **Step 6: Run the new tests**

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_rate_range.py -q
```

Expected: all PASS, including `test_the_averaged_breakdown_sums_to_the_averaged_price`.

- [ ] **Step 7: Serialize it**

In `apps/api/dynamic_pricing/routers/rate.py`, in `rate_range`, inside the
`"adjustments"` list comprehension, after `"params": a.params,`:

```python
                # How many nights this row was averaged from. A row covering
                # two of seven nights is indistinguishable from one covering
                # all seven without it, which is exactly how the averaged
                # breakdown came to read as though every line described the
                # whole range.
                "nights_covered": a.nights_covered,
```

- [ ] **Step 8: Add an API-level test**

Append to `apps/api/tests/test_api_workflow.py`:

```python
def test_range_adjustments_report_their_night_coverage(client):
    """The drawer badges a row with the nights it covers, so the payload has
    to carry the count -- and it can never exceed the priced nights."""
    tiles = client.get(
        "/api/rate/tiles", params={"start_date": _today(), "nights": 7}
    ).json()
    tile = tiles["tiles"][0]
    detail = client.get(
        "/api/rate/range",
        params={
            "room_type_id": tile["room_type_id"],
            "start_date": tiles["start_date"],
            "end_date": tiles["end_date"],
        },
    ).json()
    priced = detail["nights"] - detail["unpriced_nights"]
    assert detail["adjustments"], "a priced range always explains itself"
    for row in detail["adjustments"]:
        assert 1 <= row["nights_covered"] <= priced
```

If `_today()` does not already exist in that module, add it near the top:

```python
from datetime import date as _date


def _today() -> str:
    return _date.today().isoformat()
```

- [ ] **Step 9: Run the full backend suite**

```bash
make test
```

Expected: all pass, count = previous + 5.

- [ ] **Step 10: Review focus**

- Did `test_the_averaged_breakdown_sums_to_the_averaged_price` stay green?
- Is `nights_covered` defaulted to `1` (not `0`), so per-night rows are right?
- Did you leave the `(code, label_key)` grouping alone? Collapsing it is
  explicitly rejected in the spec.
- Did you avoid touching `_average_params`? Phase 4 handles that differently.

- [ ] **Step 11: Commit**

```bash
git add apps/api/dynamic_pricing/services/rate_range.py apps/api/dynamic_pricing/routers/rate.py apps/api/tests/test_rate_range.py apps/api/tests/test_api_workflow.py
git commit -m "$(cat <<'EOF'
feat(rate): report how many nights each averaged breakdown row covers

Grouping is by (code, label_key), so one factor can render as several
rows -- pace alone has eight label variants. Without a night count any
one of those rows reads as describing the whole range, which is what
made the averaged breakdown look broken.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N2Zqrn8wX2qG52w9qytSw9
EOF
)"
```

---

## PHASE 2 — Widen the per-night payload

**Spec sections:** "Architecture" (items 1 and 3).

**Why:** night mode renders from `nightly[]`. Today that array carries 7 fields
and drops the adjustments, band, current rate, provenance, clamp and decision
state that `load_range` already loaded.

**Files:**
- Modify: `apps/api/dynamic_pricing/services/rate_range.py` (`NightlyPrice` dataclass ~line 46-64)
- Modify: `apps/api/dynamic_pricing/services/rate_page.py` (`_nightly_prices` ~line 71-105)
- Modify: `apps/api/dynamic_pricing/routers/rate.py` (`nightly` serialization ~line 209-221)
- Test: `apps/api/tests/test_rate_range.py`, `apps/api/tests/test_api_workflow.py`

**Interfaces:**
- Consumes: `Contribution.nights_covered` from Phase 1.
- Produces: each item of `nightly[]` in `GET /api/rate/range` gains
  `current_net_rate: float`, `base_net_rate: float`,
  `band: {min, base, max}`, `rate_provenance: str`,
  `decision: "accepted" | "overridden" | null`,
  `clamped: "min" | "max" | null`,
  `delta_vs_average_pct: float`,
  `adjustments: [...]` (same shape as the range-level array, each with
  `nights_covered: 1`).

### Context you need

`PricingRecommendation` (see `apps/api/dynamic_pricing/models.py`) carries
`net_rate_before_clamp`, `status`, `band_min_net_rate`, `band_max_net_rate`.
Statuses come from `constants.py`: `STATUS_PENDING = "pending"`,
`STATUS_ACCEPTED = "accepted"`, `STATUS_OVERRIDDEN = "overridden"`,
`STATUS_ERROR = "error"`.

**Clamp derivation.** A night is clamped when the engine's pre-clamp price fell
outside the band. Compare `net_rate_before_clamp` against the band bounds, not
against the recommended rate — rounding moves the recommended rate by up to one
increment and would produce false positives.

**D10.** `delta_vs_average_pct` is computed in Python. Do not be tempted to do
it in the browser; `RangeDrawer.tsx:223-230` already does that class of
arithmetic inline for a different figure, but the spec is explicit that new
displayed percentages are served.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/test_rate_range.py`:

```python
def test_a_night_is_clamped_when_the_pre_clamp_price_left_the_band():
    """Compared against the BAND, not against the recommended rate: rounding
    moves the recommended rate by up to one increment, which would report a
    clamp that never happened."""
    from dynamic_pricing.services.rate_range import clamp_side

    assert clamp_side(before=2_500_000, band_min=1_800_000, band_max=2_300_000) == "max"
    assert clamp_side(before=1_500_000, band_min=1_800_000, band_max=2_300_000) == "min"
    assert clamp_side(before=2_000_000, band_min=1_800_000, band_max=2_300_000) is None


def test_an_open_ceiling_can_never_clamp_at_the_top():
    """MAX is optional (ASSUMPTIONS U9). An empty ceiling means the only bound
    is the dynamic one, so there is no band edge to hit."""
    from dynamic_pricing.services.rate_range import clamp_side

    assert clamp_side(before=9_000_000, band_min=1_800_000, band_max=None) is None
    assert clamp_side(before=1_000_000, band_min=1_800_000, band_max=None) == "min"
```

Append to `apps/api/tests/test_api_workflow.py`:

```python
def test_each_night_carries_everything_the_drawer_needs(client):
    """Night mode renders from nightly[] and issues no second request, so the
    array has to be self-sufficient."""
    tiles = client.get(
        "/api/rate/tiles", params={"start_date": _today(), "nights": 7}
    ).json()
    tile = tiles["tiles"][0]
    detail = client.get(
        "/api/rate/range",
        params={
            "room_type_id": tile["room_type_id"],
            "start_date": tiles["start_date"],
            "end_date": tiles["end_date"],
        },
    ).json()
    for n in detail["nightly"]:
        assert {
            "stay_date", "units_sold", "units_total", "recommended_net_rate",
            "priced", "days_to_arrival", "expected_occupancy", "occupancy",
            "current_net_rate", "base_net_rate", "band", "rate_provenance",
            "decision", "clamped", "delta_vs_average_pct", "adjustments",
        } <= set(n)
        assert set(n["band"]) == {"min", "base", "max"}
        assert n["clamped"] in {"min", "max", None}
        assert n["decision"] in {"accepted", "overridden", None}


def test_a_priced_night_explains_itself_the_same_way_the_range_does(client):
    """Night mode reuses PriceContribution, so a night's adjustments have the
    same shape as the range's -- and each covers exactly one night."""
    tiles = client.get(
        "/api/rate/tiles", params={"start_date": _today(), "nights": 7}
    ).json()
    tile = tiles["tiles"][0]
    detail = client.get(
        "/api/rate/range",
        params={
            "room_type_id": tile["room_type_id"],
            "start_date": tiles["start_date"],
            "end_date": tiles["end_date"],
        },
    ).json()
    priced = [n for n in detail["nightly"] if n["priced"]]
    assert priced, "the demo range always has at least one priced night"
    for row in priced[0]["adjustments"]:
        assert {"code", "label", "label_key", "delta", "params",
                "is_neutral", "is_ignored", "nights_covered"} <= set(row)
        assert row["nights_covered"] == 1


def test_the_night_delta_is_measured_against_the_range_average(client):
    """The strip's percentage answers 'does accepting the average over- or
    under-price this night?', so it is relative to the average -- and an
    unpriced night, which is in no average, reports zero rather than a
    fabricated gap."""
    tiles = client.get(
        "/api/rate/tiles", params={"start_date": _today(), "nights": 7}
    ).json()
    tile = tiles["tiles"][0]
    detail = client.get(
        "/api/rate/range",
        params={
            "room_type_id": tile["room_type_id"],
            "start_date": tiles["start_date"],
            "end_date": tiles["end_date"],
        },
    ).json()
    avg = detail["average_recommended_net_rate"]
    for n in detail["nightly"]:
        if not n["priced"]:
            assert n["delta_vs_average_pct"] == 0.0
            continue
        expected = round((n["recommended_net_rate"] - avg) / avg * 100, 2)
        assert n["delta_vs_average_pct"] == expected
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_rate_range.py -q -k "clamp"
cd apps/api && .venv/bin/python -m pytest tests/test_api_workflow.py -q -k "drawer_needs or explains_itself or night_delta"
```

Expected: `ImportError: cannot import name 'clamp_side'` for the first,
`KeyError`/assertion failures on the missing fields for the second.

- [ ] **Step 3: Add `clamp_side` and the new `NightlyPrice` fields**

In `apps/api/dynamic_pricing/services/rate_range.py`, add after
`count_units_with_a_free_night`:

```python
def clamp_side(
    *, before: float, band_min: float, band_max: float | None
) -> str | None:
    """Which band edge the engine's price was pulled back to, if any.

    Measured on the PRE-CLAMP price against the band, not on the recommended
    rate: rounding moves the recommended rate by up to one increment, so a
    night rounded down to exactly MAX would otherwise report a clamp that
    never happened.

    An empty MAX (ASSUMPTIONS U9) means the only ceiling is the dynamic bound,
    so there is no top edge to hit.
    """
    if band_max is not None and before > band_max:
        return "max"
    if before < band_min:
        return "min"
    return None
```

Then add to the `NightlyPrice` dataclass, after `rate_provenance`:

```python
    #: The engine's price before the band clamped it, used to report which
    #: edge a night was pulled back to. An AVERAGE is never clamped -- the
    #: individual nights were -- so this is per-night only.
    net_rate_before_clamp: float = 0.0
    #: "accepted" / "overridden" from the recommendation's status, or None
    #: while it is still pending. A hand-tuned night is what a bulk accept
    #: must not silently replace.
    decision: str | None = None
```

- [ ] **Step 4: Carry them through `_nightly_prices`**

In `apps/api/dynamic_pricing/services/rate_page.py`, add to the `NightlyPrice(...)`
construction inside `_nightly_prices`:

```python
            net_rate_before_clamp=r.net_rate_before_clamp,
            decision=(
                r.status if r.status in (STATUS_ACCEPTED, STATUS_OVERRIDDEN) else None
            ),
```

and extend the import at the top of that file:

```python
from ..constants import STATUS_ACCEPTED, STATUS_ERROR, STATUS_OVERRIDDEN
```

- [ ] **Step 5: Widen the router serialization**

In `apps/api/dynamic_pricing/routers/rate.py`, first add a helper above
`rate_range` (next to `_uniform_provenance`):

```python
def _adjustment_payload(a) -> dict:
    """One explainable step, in the shape both scopes of the drawer render.

    D30: a message KEY plus the figures it interpolates, never a finished
    sentence. `nights_covered` travels with every row -- including a per-night
    row, where it is 1 -- because the ICU message branches on it, and a row
    that arrives without it loses its whole sentence rather than one word.
    """
    return {
        "code": a.code,
        "label": a.label,
        "label_key": a.label_key,
        "delta": a.delta,
        "is_neutral": a.is_neutral,
        "is_ignored": a.is_ignored,
        "params": {**a.params, "nights_covered": a.nights_covered},
        "nights_covered": a.nights_covered,
    }
```

Replace the existing `"adjustments"` list comprehension in `rate_range` with:

```python
        "adjustments": [_adjustment_payload(a) for a in aggregate.adjustments],
```

Replace the `"nightly"` list comprehension with:

```python
        "nightly": [
            {
                "stay_date": n.stay_date,
                "units_sold": n.units_sold,
                "units_total": n.units_total,
                "recommended_net_rate": n.recommended_net_rate,
                "current_net_rate": n.current_net_rate,
                "base_net_rate": n.base_net_rate,
                "priced": n.priced,
                "days_to_arrival": n.days_to_arrival,
                "expected_occupancy": n.expected_occupancy,
                "occupancy": n.occupancy,
                # One band per night. The range check guarantees they agree,
                # but night mode reads its own rather than inheriting the
                # range's, so a future multi-season range cannot mislabel it.
                "band": {
                    "min": n.band_min,
                    "base": n.band_base,
                    "max": n.band_max,
                },
                "rate_provenance": n.rate_provenance,
                "decision": n.decision,
                "clamped": (
                    clamp_side(
                        before=n.net_rate_before_clamp,
                        band_min=n.band_min,
                        band_max=n.band_max,
                    )
                    if n.priced
                    else None
                ),
                # How far accepting the range average would move THIS night.
                # Served rather than derived in the browser (D10), and zero for
                # an unpriced night, which is in no average at all.
                "delta_vs_average_pct": (
                    round(
                        (n.recommended_net_rate - aggregate.average_recommended_net_rate)
                        / aggregate.average_recommended_net_rate
                        * 100,
                        2,
                    )
                    if n.priced and aggregate.average_recommended_net_rate
                    else 0.0
                ),
                "adjustments": [_adjustment_payload(a) for a in n.adjustments],
            }
            for n in nights
        ],
```

Extend the import from `rate_page`/`rate_range` at the top of the router:

```python
from ..services.rate_range import clamp_side
```

- [ ] **Step 6: Run the tests**

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_rate_range.py tests/test_api_workflow.py -q
```

Expected: PASS.

- [ ] **Step 7: Run the full suite**

```bash
make test && make lint
```

- [ ] **Step 8: Review focus**

- Is `clamp_side` measured on `net_rate_before_clamp`, never on
  `recommended_net_rate`?
- Does `band_max is None` return `None` for the top edge rather than crashing?
- Does `delta_vs_average_pct` return `0.0` (not `None`) for an unpriced night,
  and guard against a zero average?
- Does `_adjustment_payload` inject `nights_covered` into `params` **as well as**
  the top level? Phase 4's ICU branch reads it from `params`.
- Did you leave `_average_params` alone?

- [ ] **Step 9: Commit**

```bash
git add apps/api/dynamic_pricing/services/rate_range.py apps/api/dynamic_pricing/services/rate_page.py apps/api/dynamic_pricing/routers/rate.py apps/api/tests/
git commit -m "$(cat <<'EOF'
feat(rate): serve everything a single night needs from the range payload

load_range already loaded each night's adjustments, band, provenance and
pre-clamp price; the router dropped all of it. Widening the nightly array
lets the drawer render a per-night scope from the same fetch, with no
second request and no loading state between nights.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N2Zqrn8wX2qG52w9qytSw9
EOF
)"
```

---

## PHASE 3 — Preserve hand-tuned nights on a bulk accept

**Spec sections:** decision D-b, "Documentation".

**Why:** once an operator can price one night, they will accept the range and
then fine-tune a night. Today D36 says a bulk accept replaces every decision
without prompting, which would silently destroy exactly the judgment night mode
exists to capture.

**Files:**
- Modify: `apps/api/dynamic_pricing/services/rate_decisions.py`
- Modify: `apps/api/dynamic_pricing/routers/rate.py` (`RangeDecisionIn`, `accept_range`, `override_range`, `_result_payload`)
- Test: `apps/api/tests/test_api_workflow.py`

**Interfaces:**
- Produces:
  - `apply_to_range(..., preserve_overrides: bool = False) -> BulkResult`
  - `BulkResult.skipped_overridden: int`
  - `RangeDecisionIn.preserve_overrides: bool = True` on `POST /api/rate/accept`
  - `"skipped_overridden": int` in both accept and override responses

### Context you need

`apply_to_range` writes one `OperatorDecision` per night and ties them with a
`group_id`, which is what lets the activity log show a fortnight as one entry.
It already skips `STATUS_ERROR` nights and reports them as `skipped_unpriced` —
follow that pattern exactly rather than inventing a second one.

**Default asymmetry, and it is deliberate:** the *service* defaults to
`preserve_overrides=False` so existing callers keep today's behaviour; the *API
request model* defaults to `True` so the operator-facing action is the safe one.
An override action always writes what the operator typed, so it never preserves.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/test_api_workflow.py`:

```python
def _first_range(client):
    tiles = client.get(
        "/api/rate/tiles", params={"start_date": _today(), "nights": 7}
    ).json()
    return tiles["tiles"][0]["room_type_id"], tiles["start_date"], tiles["end_date"]


def test_a_bulk_accept_preserves_a_hand_tuned_night_by_default(client):
    """The operator's per-night judgment is the whole reason night mode
    exists. A later bulk accept must not silently replace it."""
    room_type_id, start, end = _first_range(client)
    client.post("/api/rate/accept", json={
        "room_type_id": room_type_id, "start_date": start, "end_date": end,
    })
    room_type_id, start, end = _first_range(client)
    detail = client.get("/api/rate/range", params={
        "room_type_id": room_type_id, "start_date": start, "end_date": end,
    }).json()
    tuned = next(n for n in detail["nightly"] if n["priced"])["stay_date"]

    client.post("/api/rate/override", json={
        "room_type_id": room_type_id,
        "start_date": tuned, "end_date": tuned,
        "final_net_rate": 1_999_000, "reason_code": "my_judgment",
    })

    room_type_id, start, end = _first_range(client)
    result = client.post("/api/rate/accept", json={
        "room_type_id": room_type_id, "start_date": start, "end_date": end,
    }).json()
    assert result["skipped_overridden"] >= 1

    detail = client.get("/api/rate/range", params={
        "room_type_id": room_type_id, "start_date": start, "end_date": end,
    }).json()
    night = next(n for n in detail["nightly"] if n["stay_date"] == tuned)
    assert night["decision"] == "overridden", "the hand-tuned night survived"


def test_an_operator_can_choose_to_overwrite_hand_tuned_nights(client):
    """Preserving is the default, not a rule. The operator is warned and then
    decides."""
    room_type_id, start, end = _first_range(client)
    detail = client.get("/api/rate/range", params={
        "room_type_id": room_type_id, "start_date": start, "end_date": end,
    }).json()
    tuned = next(n for n in detail["nightly"] if n["priced"])["stay_date"]
    client.post("/api/rate/override", json={
        "room_type_id": room_type_id,
        "start_date": tuned, "end_date": tuned,
        "final_net_rate": 1_998_000, "reason_code": "my_judgment",
    })

    room_type_id, start, end = _first_range(client)
    result = client.post("/api/rate/accept", json={
        "room_type_id": room_type_id, "start_date": start, "end_date": end,
        "preserve_overrides": False,
    }).json()
    assert result["skipped_overridden"] == 0

    detail = client.get("/api/rate/range", params={
        "room_type_id": room_type_id, "start_date": start, "end_date": end,
    }).json()
    night = next(n for n in detail["nightly"] if n["stay_date"] == tuned)
    assert night["decision"] == "accepted", "the operator asked to overwrite"


def test_accepting_one_night_writes_only_that_night(client):
    """A single day is a range of length one (D35), so night mode needs no
    second code path -- but it must not spill onto its neighbours."""
    room_type_id, start, end = _first_range(client)
    detail = client.get("/api/rate/range", params={
        "room_type_id": room_type_id, "start_date": start, "end_date": end,
    }).json()
    target = next(n for n in detail["nightly"] if n["priced"])

    result = client.post("/api/rate/accept", json={
        "room_type_id": room_type_id,
        "start_date": target["stay_date"], "end_date": target["stay_date"],
        "preserve_overrides": False,
    }).json()
    assert result["nights"] == 1
    assert result["decisions_written"] == 1
    assert result["net_rate"] == target["recommended_net_rate"], (
        "accepting one night writes that night's own price, not an average"
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_api_workflow.py -q -k "hand_tuned or overwrite_hand_tuned or accepting_one_night"
```

Expected: `KeyError: 'skipped_overridden'`.

- [ ] **Step 3: Add preservation to the service**

In `apps/api/dynamic_pricing/services/rate_decisions.py`, add to `BulkResult`:

```python
    skipped_overridden: int = 0
```

Add the parameter to `apply_to_range`'s signature, after `operator`:

```python
    preserve_overrides: bool = False,
```

Extend the docstring:

```
    ``preserve_overrides`` skips nights an operator has already priced by hand.
    D36 originally had a bulk accept replace every decision without prompting,
    which was right while the range was the only unit of work. Once a single
    night can be priced on its own, silently replacing that night destroys the
    judgment the per-night scope exists to capture -- so the caller warns
    first and the operator chooses (D40).
```

Extend the import:

```python
from ..constants import (
    DECISION_ACCEPTED,
    DECISION_OVERRIDDEN,
    STATUS_ACCEPTED,
    STATUS_ERROR,
    STATUS_OVERRIDDEN,
)
```

Add the counter and the skip inside the `for rec in rows:` loop, immediately
after the existing `STATUS_ERROR` check:

```python
    skipped_override = 0
```

(declare it next to `skipped = 0`), then:

```python
        if preserve_overrides and rec.status == STATUS_OVERRIDDEN:
            skipped_override += 1
            continue
```

And return it:

```python
        skipped_overridden=skipped_override,
```

- [ ] **Step 4: Expose it on the API**

In `apps/api/dynamic_pricing/routers/rate.py`, add to `RangeDecisionIn`:

```python
    # Defaults to True here while the SERVICE defaults to False: an operator
    # pressing "accept for 7 nights" is warned about hand-tuned nights and gets
    # the safe outcome unless they opt out, but an internal caller keeps the
    # older, simpler behaviour.
    preserve_overrides: bool = True
```

Add to `_result_payload`:

```python
        # Nights an operator had already priced by hand and that this action
        # deliberately left alone (D40).
        "skipped_overridden": result.skipped_overridden,
```

Pass it through in `accept_range`'s `apply_to_range(...)` call:

```python
            preserve_overrides=body.preserve_overrides,
```

**Do not** pass it in `override_range` — an override writes the operator's own
number and always applies.

- [ ] **Step 5: Run the tests**

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_api_workflow.py -q
```

- [ ] **Step 6: Run the full suite**

```bash
make test && make lint
```

- [ ] **Step 7: Review focus**

- Does the skip happen **after** the `STATUS_ERROR` check, so an unpriced night
  is still counted as unpriced rather than as preserved?
- Does `override_range` still overwrite unconditionally?
- Is `skipped_overridden` defaulted on `BulkResult` so existing constructions
  compile?
- Did any existing test that asserts overwrite behaviour break? If so, the
  service default is wrong — it must be `False`.

- [ ] **Step 8: Commit**

```bash
git add apps/api/dynamic_pricing/services/rate_decisions.py apps/api/dynamic_pricing/routers/rate.py apps/api/tests/test_api_workflow.py
git commit -m "$(cat <<'EOF'
feat(rate): keep hand-tuned nights when a bulk accept runs over them

D36 had a bulk accept replace every decision without prompting, which was
right while the range was the only unit of work. Once one night can be
priced on its own, silently replacing it destroys the judgment that scope
exists to capture. The operator is warned and chooses; preserving is the
default.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N2Zqrn8wX2qG52w9qytSw9
EOF
)"
```

---

## PHASE 4 — Fix the sentences that print impossible numbers

**Spec sections:** "The param bug — fixed in the message files, not in the averaging".

**Why:** the averaged breakdown currently renders "khi còn **4,5 ngày** đến ngày
nhận phòng", "**2,333 lượt đặt**", "Giá tham chiếu **2.465.714,286 ₫**", and says
"**ngày này**" about a group of nights.

**Files:**
- Modify: `apps/web/messages/en.json`
- Modify: `apps/web/messages/vi.json`
- Test: `apps/api/tests/test_localisation.py`

**Interfaces:**
- Consumes: `params.nights_covered` injected by `_adjustment_payload` (Phase 2).
- Produces: no new message keys. Existing `adjustments.pace.*.reason`,
  `adjustments.recent_pickup.*.reason` and `adjustments.market.applied.reason`
  gain a plural branch and number skeletons.

### Context you need

**Why this is not fixed in `_average_params`.** Rounding `days_to_arrival` from
4.5 to 4 replaces one false precision with another — the group covers 8/9 and
12/9 and no single lead time describes it. ICU only requires arguments the
*selected* branch references, so the multi-night branch can simply not mention
lead time at all.

**Why these are edits, not new keys.** `pace` has 8 label variants; a
`.reasonRange` sibling for each would be 16 new keys across two locales, all
guarded by `test_every_emittable_key_has_a_translation`. A plural branch inside
the existing `reason` is one edit per key and no new surface.

**The persisted-params trap.** `params` are stored on adjustment rows, and
`apps/web/lib/adjustments.ts:33` catches an ICU failure by dropping the entire
sentence. A message that references `{nights_covered}` will silently lose its
explanation for any row that lacks it — which is exactly why Phase 2 injects it
at serialization time for every row rather than relying on what was persisted.
**Verify that injection is in place before starting this phase.**

**ICU number skeletons.** `{x, number, ::.}` renders no decimals;
`{x, number, ::.#}` renders at most one. Use these instead of changing the data.

- [ ] **Step 1: Write the failing test**

Append to `apps/api/tests/test_localisation.py`:

```python
def test_a_multi_night_explanation_never_claims_a_fractional_lead_time():
    """Averaging integers across a group prints impossible values -- half a
    day to arrival, 2.333 bookings. ICU only requires the arguments the
    SELECTED branch uses, so the multi-night branch drops lead time rather
    than rounding one lie into another.
    """
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "web" / "messages"
    for locale in ("en", "vi"):
        messages = json.loads((root / f"{locale}.json").read_text(encoding="utf-8"))
        pace = messages["adjustments"]["pace"]
        for key, node in pace.items():
            reason = node["reason"]
            if "days_to_arrival" not in reason:
                continue
            assert "nights_covered" in reason, (
                f"{locale}: adjustments.pace.{key}.reason cites a lead time but "
                f"does not branch on how many nights it covers"
            )
            head, _, tail = reason.partition("other {")
            assert "days_to_arrival" not in tail, (
                f"{locale}: adjustments.pace.{key}.reason still cites a single "
                f"night's lead time in its multi-night branch"
            )


def test_a_dong_amount_is_never_rendered_with_decimals():
    """An averaged reference rate arrives as 2465714.2857. Rendered raw it
    reads '2.465.714,286 ₫', which is not a price anyone can charge."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "web" / "messages"
    for locale in ("en", "vi"):
        messages = json.loads((root / f"{locale}.json").read_text(encoding="utf-8"))
        reason = messages["adjustments"]["market"]["applied"]["reason"]
        assert "{reference_net_rate, number, ::." in reason, (
            f"{locale}: the comparable rate needs a whole-dong skeleton"
        )
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_localisation.py -q -k "fractional_lead_time or dong_amount"
```

Expected: FAIL on the missing `nights_covered` branch.

- [ ] **Step 3: Edit the English pace messages**

For **every** variant under `adjustments.pace` in `apps/web/messages/en.json`
whose `reason` cites `days_to_arrival` (`well_behind`, `behind`, `on_pace`,
`ahead`, `well_ahead`), replace the `reason` with:

```
"{nights_covered, plural, one {{occupancy, number, percent} sold with {days_to_arrival, number} day(s) to arrival. The booking curve expects {expected_occupancy, number, percent} by now, so this date is {gap_pp, number, ::.#} points {direction, select, ahead {ahead of} other {behind}} pace.} other {Across {nights_covered, number} nights, {occupancy, number, percent} sold on average against the {expected_occupancy, number, percent} the booking curve expects -- {gap_pp, number, ::.#} points {direction, select, ahead {ahead of} other {behind}} pace.}}"
```

Leave `unavailable`, `occupancy_unavailable` and `no_band` untouched — they cite
no lead time and already read correctly for any number of nights.

- [ ] **Step 4: Edit the English recent_pickup messages**

For every variant under `adjustments.recent_pickup` (`stalled`, `slowing`,
`as_expected`, `accelerating` — check the file for the full list), replace
`reason` with:

```
"{nights_covered, plural, one {{recent_pickup, number} booking(s) in the last {lookback_days, number} days versus {expected_pickup, number} expected ({delta, number}).} other {An average of {recent_pickup, number, ::.#} bookings per night in the last {lookback_days, number} days, versus {expected_pickup, number, ::.#} expected ({delta, number, ::.#}).}}"
```

- [ ] **Step 5: Edit the English market message**

In `adjustments.market.applied.reason`, change `{reference_net_rate, number}`
to `{reference_net_rate, number, ::.}` and `{delta_pct, number}` to
`{delta_pct, number, ::.#}`.

- [ ] **Step 6: Mirror all of it into Vietnamese**

Apply the same three edits to `apps/web/messages/vi.json`. The Vietnamese
`other` branches:

pace:
```
"{nights_covered, plural, other {Trong {nights_covered, number} đêm, trung bình đã bán {occupancy, number, percent} so với {expected_occupancy, number, percent} mà đường cong đặt phòng kỳ vọng -- {direction, select, ahead {nhanh hơn} other {chậm hơn}} tiến độ {gap_pp, number, ::.#} điểm.}}"
```

recent_pickup:
```
"{nights_covered, plural, other {Trung bình {recent_pickup, number, ::.#} lượt đặt mỗi đêm trong {lookback_days, number} ngày qua, so với {expected_pickup, number, ::.#} lượt kỳ vọng ({delta, number, ::.#}).}}"
```

**Both locales must describe the same keys** — `npm run check:messages` enforces
this. Vietnamese has no `one`/`other` plural distinction the way English does,
but ICU still requires an `other` branch; include a `one` branch matching the
existing singular sentence so a single night reads naturally.

- [ ] **Step 7: Run the tests**

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_localisation.py -q
cd apps/web && npm run check:messages
```

Both must pass. `check:messages` parses every message with the real ICU
compiler, so a malformed plural fails here.

- [ ] **Step 8: Verify against real data**

```bash
cd apps/api && .venv/bin/python -c "
from dynamic_pricing.db import SessionLocal
from dynamic_pricing.services.rate_page import load_range
from dynamic_pricing.services.configuration import get_active_configuration
from datetime import date
import json
s = SessionLocal()
inc = int(((get_active_configuration(s).payload or {}).get('rounding') or {}).get('increment') or 0)
agg, nights, _, _ = load_range(s, room_type_id=2, start=date(2026,9,6), end=date(2026,9,12), rounding_increment=inc)
for c in agg.adjustments:
    print(c.label_key, '->', c.nights_covered, 'nights')
"
```

Then confirm in the running app (`make dev`, open `/vi/rate/`, click a tile)
that no sentence reads "4,5 ngày" or "2,333 lượt".

- [ ] **Step 9: Run everything**

```bash
make test && make lint && cd apps/web && npm test
```

- [ ] **Step 10: Review focus**

- Does every edited `reason` still work for a **single** night? That is the
  `one` branch and it is what night mode renders.
- Did you edit **both** locale files, with the same key set?
- Did you avoid adding any new message key?
- Did you avoid touching `_average_params`?
- No ALL-CAPS, no single-word emphasis inside a sentence — both are banned by
  `apps/web/CLAUDE.md`.

- [ ] **Step 11: Commit**

```bash
git add apps/web/messages/en.json apps/web/messages/vi.json apps/api/tests/test_localisation.py
git commit -m "$(cat <<'EOF'
fix(i18n): stop the averaged explanation printing impossible numbers

Averaging integers across a group produced "4,5 ngày to arrival" and
"2,333 bookings", and every sentence said "this day" while describing
several. ICU only requires the arguments its selected branch uses, so the
multi-night branch drops lead time entirely rather than rounding one false
precision into another.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N2Zqrn8wX2qG52w9qytSw9
EOF
)"
```

---

## PHASE 5 — Frontend contract

**Files:**
- Modify: `apps/web/lib/types.ts` (`ExplainedStep` ~line 78-89, `RangeNight` ~line 272-281, `RangeDetail` ~line 284-309, `BulkDecisionResult` ~line 311-317)
- Modify: `apps/web/lib/api.ts` (`acceptRange` ~line 132)

**Interfaces:**
- Produces: `RangeNight` gains the Phase 2 fields; `ExplainedStep` gains
  `nights_covered: number`; `acceptRange` gains a `preserveOverrides` argument.

- [ ] **Step 1: Extend the types**

In `apps/web/lib/types.ts`, add to `ExplainedStep`:

```ts
  /** How many PRICED nights this row was averaged from. 1 for a per-night row.
   *  The ICU message branches on it, so it also appears inside `params`. */
  nights_covered: number;
```

Replace `RangeNight` with:

```ts
/** One night inside a range — the per-night strip, the pace curve, and the
 *  whole of the drawer's night scope. Self-sufficient on purpose: night mode
 *  issues no second request, so switching nights never shows a spinner. */
export interface RangeNight {
  stay_date: string;
  units_sold: number;
  units_total: number;
  recommended_net_rate: number;
  current_net_rate: number;
  base_net_rate: number;
  priced: boolean;
  days_to_arrival: number | null;
  expected_occupancy: number | null;
  occupancy: number | null;
  band: { min: number | null; base: number | null; max: number | null };
  rate_provenance: RangeProvenance;
  /** Set when an operator has already decided this night. "overridden" is the
   *  hand-tuned state a bulk accept preserves by default. */
  decision: "accepted" | "overridden" | null;
  /** Which band edge the engine's price was pulled back to. An AVERAGE is
   *  never clamped, so this exists per night only. */
  clamped: "min" | "max" | null;
  /** How far accepting the range average would move this night, in percent.
   *  Served rather than derived here (D10). */
  delta_vs_average_pct: number;
  adjustments: ExplainedStep[];
}
```

Add to `BulkDecisionResult`:

```ts
  /** Nights an operator had priced by hand that this action left alone. */
  skipped_overridden: number;
```

- [ ] **Step 2: Extend the API client**

In `apps/web/lib/api.ts`, replace `acceptRange` with:

```ts
  acceptRange: (
    room_type_id: number,
    start_date: string,
    end_date: string,
    // Preserving hand-tuned nights is the default; the operator is warned in
    // the drawer and opts out explicitly (D40).
    preserve_overrides = true,
    note?: string,
  ) =>
    request<BulkDecisionResult>("/api/rate/accept", {
      method: "POST",
      body: JSON.stringify({
        room_type_id,
        start_date,
        end_date,
        preserve_overrides,
        note: note || null,
      }),
    }),
```

- [ ] **Step 3: Verify it compiles**

```bash
cd apps/web && npx tsc --noEmit
```

Expected: errors ONLY in `RangeDrawer.tsx` (it passes `note` positionally where
`preserve_overrides` now sits). Fix that call site to
`api.acceptRange(detail.room_type_id, detail.start_date, detail.end_date)` —
the default is correct and no note is passed today.

- [ ] **Step 4: Run the frontend suite**

```bash
cd apps/web && npm test && npx tsc --noEmit
```

- [ ] **Step 5: Review focus**

- Do the TypeScript field names match the Python payload keys **exactly**?
  `delta_vs_average_pct`, not `deltaVsAveragePct`.
- Is `RangeProvenance` already imported/defined in `types.ts`? It is used by
  `RangeDetail` today, so it should be.

- [ ] **Step 6: Commit**

```bash
git add apps/web/lib/types.ts apps/web/lib/api.ts apps/web/components/RangeDrawer.tsx
git commit -m "$(cat <<'EOF'
feat(web): type the widened per-night payload

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N2Zqrn8wX2qG52w9qytSw9
EOF
)"
```

---

## PHASE 6 — The strip becomes the picker

**Spec sections:** decisions D-d, D-e; "Design-system constraints".

**Why:** `OccupancyStrip` already renders one column per night with a date label
and amber for unpriced. A separate chip strip would be a second horizontal
7-item date row stacked on the first.

**Files:**
- Modify: `apps/web/components/viz.tsx` (`PriceContribution` ~line 212-260, `OccupancyStrip` ~line 336-371, `PaceStripNight` ~line 373-378)
- Create: `apps/web/components/viz.test.tsx`
- Modify: `apps/web/messages/{en,vi}.json`

**Interfaces:**
- Produces:
  - `OccupancyStrip({ nights, selected?, onSelect?, showDeltas? })` — when
    `onSelect` is supplied each column becomes a `<button>`.
  - `PaceStripNight` gains `decision`, `delta_vs_average_pct`.
  - `PriceContribution({ adjustments, render, totalNights? })` — badges every
    row with its own night count when `totalNights > 1`; badges nothing when
    the scope is a single night.

### Context you need

**The bar height encodes occupancy.** Selection must be an outline only.
Changing height or bar colour on selection would make the chart's own data
encoding shift meaning under the operator — the single worst thing that could
happen to this component.

**Colour, from `apps/web/CLAUDE.md`:** `amber-*` is already used here for
unpriced. `violet-*` is reserved in this codebase for the "overridden" state and
nothing else — use it for hand-tuned. `brand-*` is the accent.

**Accessibility:** the strip is currently `role="img"` with an aria-label.
Once columns are interactive that is wrong — it becomes a list of buttons, each
labelled with its date and price delta.

- [ ] **Step 1: Add the message keys**

To `apps/web/messages/en.json` under `drawer`:

```json
    "nightsCovered": "{count, plural, one {# night} other {# nights}}",
    "stripSelect": "{date}, {delta} versus the range average",
    "stripHandTuned": "priced by hand",
    "stripDeltaCaption": "How each night compares with the average"
```

To `apps/web/messages/vi.json` under `drawer`:

```json
    "nightsCovered": "{count, plural, other {# đêm}}",
    "stripSelect": "{date}, {delta} so với trung bình dãy ngày",
    "stripHandTuned": "đã chỉnh tay",
    "stripDeltaCaption": "Mỗi đêm so với giá trung bình"
```

- [ ] **Step 2: Write the failing tests**

Create `apps/web/components/viz.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithIntl } from "./test-utils";
import { OccupancyStrip, PriceContribution } from "./viz";
import type { ExplainedStep } from "@/lib/types";

const night = (day: number, over: Partial<any> = {}) => ({
  stay_date: `2026-09-0${day}`,
  units_sold: 4,
  units_total: 8,
  priced: true,
  decision: null,
  delta_vs_average_pct: 0,
  ...over,
});

describe("OccupancyStrip", () => {
  it("is inert when no selection handler is given", () => {
    renderWithIntl(<OccupancyStrip nights={[night(1), night(2)]} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("becomes a list of buttons when a night can be picked", async () => {
    const onSelect = vi.fn();
    renderWithIntl(
      <OccupancyStrip
        nights={[night(1), night(2)]}
        selected="2026-09-01"
        onSelect={onSelect}
      />,
    );
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(2);
    await userEvent.click(buttons[1]);
    expect(onSelect).toHaveBeenCalledWith("2026-09-02");
  });

  it("marks the selected night without changing the bar it draws", () => {
    const { container } = renderWithIntl(
      <OccupancyStrip
        nights={[night(1, { units_sold: 4 }), night(2, { units_sold: 4 })]}
        selected="2026-09-01"
        onSelect={() => {}}
      />,
    );
    // Both nights sold the same, so both bars must still be the same height:
    // selection is an outline, never a change to the data encoding.
    const bars = Array.from(
      container.querySelectorAll<HTMLElement>("[data-bar]"),
    );
    expect(bars[0].style.height).toBe(bars[1].style.height);
    expect(bars[0].className).toBe(bars[1].className);
  });

  it("marks a hand-tuned night so a bulk accept is not a surprise", () => {
    const { container } = renderWithIntl(
      <OccupancyStrip
        nights={[night(1, { decision: "overridden" }), night(2)]}
        onSelect={() => {}}
      />,
    );
    expect(container.querySelectorAll("[data-hand-tuned]")).toHaveLength(1);
  });

  it("shows how far each night sits from the range average", () => {
    renderWithIntl(
      <OccupancyStrip
        nights={[
          night(1, { delta_vs_average_pct: 10.4 }),
          night(2, { delta_vs_average_pct: -8.7 }),
        ]}
        showDeltas
      />,
    );
    // Matched loosely on purpose: formatAdjPct owns the sign, separator and
    // precision, and this test is about the delta being SHOWN, not about how
    // that helper formats. Asserting the exact string here would make a
    // formatting change look like a regression in the strip.
    expect(screen.getByText(/10[.,]4/)).toBeTruthy();
    expect(screen.getByText(/8[.,]7/)).toBeTruthy();
  });
});

const step = (over: Partial<ExplainedStep> = {}): ExplainedStep => ({
  code: "pace",
  label: "Pace",
  label_key: "adjustments.pace.behind",
  delta: -1000,
  params: {},
  is_neutral: false,
  is_ignored: false,
  nights_covered: 1,
  ...over,
});

describe("PriceContribution", () => {
  const render = (a: ExplainedStep) => ({ label: a.label, reason: "" });

  it("badges a row that does not describe the whole range", () => {
    renderWithIntl(
      <PriceContribution
        adjustments={[step({ nights_covered: 2, label: "Behind" })]}
        render={render}
        totalNights={7}
      />,
    );
    expect(screen.getByText("2 nights")).toBeTruthy();
  });

  it("badges a row that covers every night too", () => {
    // Every row carries its own count so none has to be inferred from the
    // absence of one, and so the counts visibly add up across the rows a
    // single factor was split into.
    renderWithIntl(
      <PriceContribution
        adjustments={[step({ nights_covered: 7, label: "Market" })]}
        render={render}
        totalNights={7}
      />,
    );
    expect(screen.getByText("7 nights")).toBeTruthy();
  });

  it("badges nothing when the scope is a single night", () => {
    renderWithIntl(
      <PriceContribution
        adjustments={[step({ nights_covered: 1 })]}
        render={render}
        totalNights={1}
      />,
    );
    expect(screen.queryByText(/night/)).toBeNull();
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd apps/web && npx vitest run components/viz.test.tsx
```

Expected: failures on the missing `onSelect`/`showDeltas`/`totalNights` props.

- [ ] **Step 4: Extend `PaceStripNight`**

```tsx
export interface PaceStripNight {
  stay_date: string;
  units_sold: number;
  units_total: number;
  priced: boolean;
  /** Set when an operator has already priced this night by hand. */
  decision?: "accepted" | "overridden" | null;
  /** How far this night sits from the range average, in percent. */
  delta_vs_average_pct?: number;
}
```

- [ ] **Step 5: Rewrite `OccupancyStrip`**

```tsx
/**
 * One bar per night, and — when a night can be picked — the drawer's night
 * selector.
 *
 * The bar's HEIGHT is occupancy. Selection is drawn as an outline and never
 * touches height or bar colour, because a chart whose encoding changes meaning
 * when you click it is worse than no chart. The delta row underneath answers
 * the question the range average hides: accepting one price for every night
 * over- or under-prices these ones by this much.
 */
export function OccupancyStrip({
  nights,
  selected,
  onSelect,
  showDeltas = false,
}: {
  nights: PaceStripNight[];
  selected?: string | null;
  onSelect?: (stayDate: string) => void;
  showDeltas?: boolean;
}) {
  const t = useTranslations("drawer");
  const { formatDayMonth, formatAdjPct } = useFormat();

  if (nights.length < 2) return null;

  const interactive = typeof onSelect === "function";

  return (
    <div>
      <p className="mb-1 text-[10.5px] text-ink-400">
        {showDeltas ? t("stripDeltaCaption") : t("stripCaption")}
      </p>
      <div
        className="flex items-end gap-[3px]"
        {...(interactive ? {} : { role: "img", "aria-label": t("stripCaption") })}
      >
        {nights.map((n) => {
          const sold = n.units_total > 0 ? n.units_sold / n.units_total : 0;
          const pct = Math.round(sold * 100);
          const isSelected = selected === n.stay_date;
          const handTuned = n.decision === "overridden";
          const delta = n.delta_vs_average_pct ?? 0;

          const column = (
            <>
              <div
                className={`flex h-12 w-full items-end rounded-sm bg-ink-100 ${
                  isSelected ? "ring-2 ring-brand-500 ring-offset-1" : ""
                }`}
              >
                <div
                  data-bar
                  className={`w-full rounded-sm ${
                    !n.priced ? "bg-amber-300" : pct >= 80 ? "bg-brand-600" : "bg-brand-400"
                  }`}
                  // A night with nothing sold still gets a hairline, so an
                  // empty night reads as "measured, zero" rather than as a gap
                  // in the chart.
                  style={{ height: `${Math.max(pct, 3)}%` }}
                  title={`${formatDayMonth(n.stay_date)} · ${pct}%`}
                />
              </div>
              <span
                className={`text-[8.5px] leading-none ${
                  isSelected ? "font-semibold text-ink-700" : "text-ink-400"
                }`}
              >
                {formatDayMonth(n.stay_date).replace(/\s/g, "\u00a0")}
              </span>
              {showDeltas && (
                <span
                  className={`tnum text-[8.5px] leading-none ${
                    delta > 0.5
                      ? "text-emerald-700"
                      : delta < -0.5
                        ? "text-amber-700"
                        : "text-ink-300"
                  }`}
                >
                  {formatAdjPct(delta)}
                </span>
              )}
              {handTuned && (
                <span
                  data-hand-tuned
                  aria-label={t("stripHandTuned")}
                  className="h-1 w-1 rounded-full bg-violet-500"
                />
              )}
            </>
          );

          const className = "flex flex-1 flex-col items-center gap-1";

          return interactive ? (
            <button
              key={n.stay_date}
              type="button"
              onClick={() => onSelect!(n.stay_date)}
              aria-pressed={isSelected}
              aria-label={t("stripSelect", {
                date: formatDayMonth(n.stay_date),
                delta: formatAdjPct(delta),
              })}
              className={`${className} rounded-sm focus:outline-none focus-visible:ring-2
                focus-visible:ring-brand-500`}
            >
              {column}
            </button>
          ) : (
            <div key={n.stay_date} className={className}>
              {column}
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Add the badge to `PriceContribution`**

Change the signature to accept `totalNights`:

```tsx
export function PriceContribution({
  adjustments,
  render,
  totalNights,
}: {
  adjustments: ExplainedStep[];
  render: (a: ExplainedStep) => { label: string; reason: string };
  /** Nights in the scope being explained. Every row is badged with its own
   *  count, so none has to be inferred from the absence of one and the counts
   *  visibly add up across the rows a single factor was split into. Suppressed
   *  entirely for a single night, where every row would read "1 night" — which
   *  is the panel's heading, not information. */
  totalNights?: number;
}) {
```

Add `const t = useTranslations("drawer");` alongside the existing hook, and
inside the `<li>`, replace the label `<span>` with:

```tsx
            <span className="flex min-w-0 items-baseline gap-1.5">
              <span
                className={`truncate text-[11.5px] ${
                  a.is_ignored ? "text-ink-400" : "text-ink-700"
                }`}
              >
                {label}
              </span>
              {totalNights !== undefined && totalNights > 1 && (
                <span className="shrink-0 text-[10px] text-ink-400">
                  {t("nightsCovered", { count: a.nights_covered })}
                </span>
              )}
            </span>
```

- [ ] **Step 7: Run the tests**

```bash
cd apps/web && npx vitest run components/viz.test.tsx && npx tsc --noEmit
```

- [ ] **Step 8: Run everything**

```bash
cd apps/web && npm test && npm run check:messages
```

- [ ] **Step 9: Review focus**

- Does the selected bar have the **same** `style.height` and the **same**
  className as an unselected bar with equal occupancy? The test asserts it;
  make sure you did not satisfy it by accident.
- Is `role="img"` dropped when the strip is interactive?
- Is the hand-tuned marker `violet`, not amber? Amber already means unpriced
  here, and two states rendering alike is the bug.
- Does every interactive column have a visible focus ring?
- No caps labels, no new icons.

- [ ] **Step 10: Commit**

```bash
git add apps/web/components/viz.tsx apps/web/components/viz.test.tsx apps/web/messages/en.json apps/web/messages/vi.json
git commit -m "$(cat <<'EOF'
feat(web): make the occupancy strip the night picker

It already drew one column per night with a date and an unpriced state; a
separate chip strip would have stacked a second seven-item date row on the
first. Selection is an outline only -- bar height stays occupancy, so the
chart's encoding cannot shift meaning when clicked. The delta row shows what
the range average hides.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N2Zqrn8wX2qG52w9qytSw9
EOF
)"
```

---

## PHASE 7 — Split the drawer and add the two scopes

**Spec sections:** "UI", "Known risk".

**Why:** `RangeDrawer.tsx` is 465 lines. Threading `mode ?` through all five
sections pushes it past 600 and makes every section dual-purpose.

**Files:**
- Create: `apps/web/components/rangeDrawer/RangeDrawerShell.tsx`
- Create: `apps/web/components/rangeDrawer/RangeScopeBody.tsx`
- Create: `apps/web/components/rangeDrawer/NightScopeBody.tsx`
- Create: `apps/web/components/rangeDrawer/RangeDrawer.test.tsx`
- Modify: `apps/web/components/RangeDrawer.tsx` → thin re-export
- Modify: `apps/web/messages/{en,vi}.json`

**Interfaces:**
- Consumes: `RangeNight`, `RangeDetail` (Phase 5); `OccupancyStrip`,
  `PriceContribution` (Phase 6).
- Produces: `RangeDrawer({ selection, onClose, onChanged })` — unchanged public
  signature, so `app/[locale]/rate/page.tsx` needs no edit.

### Context you need

Read the current `RangeDrawer.tsx` end to end first. Everything it does today
is the **range scope**; you are lifting the shell out around it, not rewriting
it. Preserve verbatim:

- the `alive` guard in the fetch effect
- the `key`-based refetch on selection change
- the market `useMemo` percentile calculation
- the `act()` wrapper
- the `allUnpriced` withdrawal of the accept action
- the `rate_provenance !== "published"` amber note
- every existing comment

`Dialog` is imported directly from `radix-ui`, not from `components/ui/` — the
shadcn wrapper's centered-modal positioning conflicts with a right-hand drawer.
Keep that. Copy the `Tabs` usage from
`apps/web/app/[locale]/customisation/page.tsx:30-61`.

- [ ] **Step 1: Add the message keys**

The existing `drawer.acceptRate` is `"Accept {rate}"` — it names no scope. The
spec requires the button to state exactly what it will write, so it is
**replaced** by two scope-specific keys. `acceptRate` has one caller
(`RangeDrawer.tsx:440`); confirm with `grep -rn "acceptRate" apps/web --include=*.tsx`
and then delete it from both locale files.

`apps/web/messages/en.json`, under `drawer`:

```json
    "scopeRange": "Whole range",
    "scopeNight": "Night by night",
    "acceptForRange": "Accept {rate} for {nights, plural, one {# night} other {# nights}}",
    "acceptForNight": "Accept {rate} for {date}",
    "averageOf": "average of {nights, plural, one {# night} other {# nights}}",
    "clampedMin": "Held at your floor",
    "clampedMax": "Held at your ceiling"
```

`apps/web/messages/vi.json`, under `drawer`:

```json
    "scopeRange": "Cả dãy ngày",
    "scopeNight": "Từng ngày",
    "acceptForRange": "Chấp nhận {rate} cho {nights, plural, other {# đêm}}",
    "acceptForNight": "Chấp nhận {rate} cho {date}",
    "averageOf": "trung bình {nights, plural, other {# đêm}}",
    "clampedMin": "Giữ ở mức sàn của bạn",
    "clampedMax": "Giữ ở mức trần của bạn"
```

The range footer therefore renders
`t("acceptForRange", { rate: formatVND(target.rate), nights: nightsToWrite })`,
where `nightsToWrite` is the plain night count in Phase 7 and becomes the
override-aware count in Phase 8. The night footer renders
`t("acceptForNight", { rate: formatVND(night.recommended_net_rate), date: formatLongDate(night.stay_date) })`.

- [ ] **Step 2: Write the failing tests**

Create `apps/web/components/rangeDrawer/RangeDrawer.test.tsx`:

```tsx
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithIntl } from "../test-utils";
import { RangeDrawer } from "./RangeDrawerShell";
import type { RangeDetail, RangeNight } from "@/lib/types";

const nightAt = (day: number, over: Partial<RangeNight> = {}): RangeNight => ({
  stay_date: `2026-09-0${day}`,
  units_sold: 4,
  units_total: 8,
  recommended_net_rate: 2_000_000 + day * 10_000,
  current_net_rate: 2_100_000,
  base_net_rate: 2_000_000,
  priced: true,
  days_to_arrival: day,
  expected_occupancy: 0.6,
  occupancy: 0.5,
  band: { min: 1_800_000, base: 2_000_000, max: 2_300_000 },
  rate_provenance: "published",
  decision: null,
  clamped: null,
  delta_vs_average_pct: day,
  adjustments: [
    {
      code: "pace",
      label: "Pace",
      label_key: "adjustments.pace.behind",
      delta: -10_000,
      params: { nights_covered: 1 },
      is_neutral: false,
      is_ignored: false,
      nights_covered: 1,
    },
  ],
  ...over,
});

const detail = (over: Partial<RangeDetail> = {}): RangeDetail =>
  ({
    room_type_id: 2,
    room_type_name: "2BR Premium",
    room_category: "2br_premium",
    room_category_label: "2BR Premium",
    start_date: "2026-09-01",
    end_date: "2026-09-03",
    nights: 3,
    season: { key: "low_2", label: "Low 2", start: "2026-09-01", end: "2026-10-31" },
    base_net_rate: 2_000_000,
    average_recommended_net_rate: 2_020_000,
    average_current_net_rate: 2_100_000,
    band: { min: 1_800_000, base: 2_000_000, max: 2_300_000 },
    adjustments: [],
    nightly: [nightAt(1), nightAt(2), nightAt(3)],
    pace_gap: -0.1,
    units_sold: 12,
    units_total: 8,
    available_units: 4,
    availability_is_exact: true,
    unpriced_nights: 0,
    rate_provenance: "published",
    ...over,
  }) as RangeDetail;

const acceptRange = vi.fn().mockResolvedValue({});
const overrideRange = vi.fn().mockResolvedValue({});
let payload: RangeDetail;

vi.mock("@/lib/api", () => ({
  api: {
    status: () => Promise.resolve({ override_reasons: [{ code: "my_judgment" }] }),
    rateRange: () => Promise.resolve(payload),
    observations: () => Promise.resolve([]),
    acceptRange: (...a: unknown[]) => acceptRange(...a),
    overrideRange: (...a: unknown[]) => overrideRange(...a),
  },
}));

const selection = { roomTypeId: 2, startDate: "2026-09-01", endDate: "2026-09-03" };

describe("RangeDrawer", () => {
  beforeEach(() => {
    payload = detail();
    acceptRange.mockClear();
    overrideRange.mockClear();
  });

  it("opens on the range scope and accepts every night", async () => {
    renderWithIntl(
      <RangeDrawer selection={selection} onClose={() => {}} onChanged={() => {}} />,
    );
    const button = await screen.findByRole("button", { name: /3 nights/i });
    await userEvent.click(button);
    expect(acceptRange).toHaveBeenCalledWith(2, "2026-09-01", "2026-09-03", true);
  });

  it("hides the scope switch when the range is a single night", async () => {
    payload = detail({ nights: 1, end_date: "2026-09-01", nightly: [nightAt(1)] });
    renderWithIntl(
      <RangeDrawer
        selection={{ ...selection, endDate: "2026-09-01" }}
        onClose={() => {}}
        onChanged={() => {}}
      />,
    );
    await screen.findByText("2BR Premium");
    expect(screen.queryByRole("tab", { name: /night by night/i })).toBeNull();
  });

  // The strip's buttons are the only elements carrying aria-pressed, which
  // makes them addressable without depending on how a date is formatted.
  const stripButtons = (c: HTMLElement) =>
    Array.from(c.querySelectorAll<HTMLElement>("[aria-pressed]"));

  it("accepts only the selected night in the night scope", async () => {
    const { container } = renderWithIntl(
      <RangeDrawer selection={selection} onClose={() => {}} onChanged={() => {}} />,
    );
    await userEvent.click(await screen.findByRole("tab", { name: /night by night/i }));
    await userEvent.click(stripButtons(container)[1]);
    await userEvent.click(
      await screen.findByRole("button", { name: /accept .* for/i }),
    );
    expect(acceptRange).toHaveBeenCalledWith(2, "2026-09-02", "2026-09-02", true);
  });

  it("withdraws the accept action on an unpriced night", async () => {
    payload = detail({
      nightly: [nightAt(1), nightAt(2, { priced: false }), nightAt(3)],
      unpriced_nights: 1,
    });
    const { container } = renderWithIntl(
      <RangeDrawer selection={selection} onClose={() => {}} onChanged={() => {}} />,
    );
    await userEvent.click(await screen.findByRole("tab", { name: /night by night/i }));
    await userEvent.click(stripButtons(container)[1]);
    expect(screen.queryByRole("button", { name: /accept .* for/i })).toBeNull();
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd apps/web && npx vitest run components/rangeDrawer/RangeDrawer.test.tsx
```

Expected: module-not-found for `./RangeDrawerShell`.

- [ ] **Step 4: Create the shell**

`apps/web/components/rangeDrawer/RangeDrawerShell.tsx` owns: the `RangeSelection`
type, all data fetching, the market `useMemo`, `act()`, the scope state, the
header, the `Tabs`, and the footer. It renders `<RangeScopeBody>` or
`<NightScopeBody>` between them.

Key state:

```tsx
const [scope, setScope] = useState<"range" | "night">("range");
const [selectedDate, setSelectedDate] = useState<string | null>(null);

// The night scope always has a night. Defaulting to the first PRICED night
// rather than the first night means opening the scope never lands on a state
// with no action available.
const night = useMemo(() => {
  if (!detail) return null;
  const wanted = detail.nightly.find((n) => n.stay_date === selectedDate);
  return wanted ?? detail.nightly.find((n) => n.priced) ?? detail.nightly[0] ?? null;
}, [detail, selectedDate]);

// A single night is the same thing in both scopes, so offering a choice
// between them would be offering a choice that changes nothing.
const canSwitchScope = (detail?.nights ?? 0) > 1;
```

Reset `scope` and `selectedDate` in the existing selection-change effect, next
to `setDetail(null)`.

The footer computes its target from the scope:

```tsx
const target =
  scope === "night" && night
    ? { start: night.stay_date, end: night.stay_date, rate: night.recommended_net_rate }
    : {
        start: detail.start_date,
        end: detail.end_date,
        rate: detail.average_recommended_net_rate,
      };

// What the accept button will ACTUALLY write. Unpriced nights get no decision
// at all, so a button naming the selected span would promise more than the
// server delivers. Phase 8 subtracts preserved hand-tuned nights from this
// same figure.
const nightsToWrite =
  scope === "night" ? 1 : detail.nights - detail.unpriced_nights;
```

Move the `Tabs` list in under the header, rendered only when `canSwitchScope`,
copying the class names from `app/[locale]/customisation/page.tsx:35-48`.

- [ ] **Step 5: Create `RangeScopeBody`**

Move sections A–E of the current file across verbatim. Two changes only:

```tsx
<PriceContribution
  adjustments={detail.adjustments}
  render={adjustmentText}
  totalNights={detail.nights}
/>
```

and the strip gains the hand-tuned markers but stays non-interactive:

```tsx
<OccupancyStrip nights={detail.nightly} showDeltas />
```

- [ ] **Step 6: Create `NightScopeBody`**

Same five sections, scoped to one night. Differences from the range body:

- heading shows `formatLongDate(night.stay_date)`, and the "average of N nights"
  caption is absent
- `RateBand` receives `clamped={night.clamped}` — the real value, finally
- **no `PaceChart`** (spec decision D-f); the strip carries neighbour context
- the strip is interactive:

```tsx
<OccupancyStrip
  nights={detail.nightly}
  selected={night.stay_date}
  onSelect={setSelectedDate}
  showDeltas
/>
```

- `PriceContribution` gets `totalNights={1}`, so nothing is badged
- market observations are filtered to the night:

```tsx
const nightObservations = useMemo(
  () => observations.filter((o) => o.stay_date === night.stay_date),
  [observations, night.stay_date],
);
```

- [ ] **Step 7: Reduce `RangeDrawer.tsx` to a re-export**

```tsx
"use client";

// The drawer moved into its own directory when it gained a second scope: one
// shell around two bodies, rather than a mode conditional inside every
// section. This re-export keeps the import path every caller already uses.
export { RangeDrawer, type RangeSelection } from "./rangeDrawer/RangeDrawerShell";
```

- [ ] **Step 8: Run the tests**

```bash
cd apps/web && npx vitest run components/rangeDrawer/RangeDrawer.test.tsx && npx tsc --noEmit
```

- [ ] **Step 9: Run everything**

```bash
cd apps/web && npm test && npm run check:messages
```

- [ ] **Step 10: Verify in the real app**

```bash
make dev
```

Open `http://localhost:3000/vi/rate/`, click a tile, and check: the tabs appear,
switching to Từng ngày selects a night, clicking a bar changes the whole body,
the footer names the date, and a one-night range shows no tabs.

- [ ] **Step 11: Review focus**

- Did every preserved comment survive the move?
- Is the `alive` guard still in the fetch effect?
- Does `scope` reset when the selection changes? A stale `selectedDate` from a
  previous tile is a real bug.
- Does the night scope fall back to a priced night rather than opening on an
  unpriced one?
- Is `PaceChart` genuinely absent from the night body?
- Is `RangeDrawer.tsx` now only the re-export, with `app/[locale]/rate/page.tsx`
  unchanged?

- [ ] **Step 12: Commit**

```bash
git add apps/web/components/RangeDrawer.tsx apps/web/components/rangeDrawer/ apps/web/messages/
git commit -m "$(cat <<'EOF'
feat(web): give the rate drawer a per-night scope

One shell around two bodies rather than a mode conditional inside every
section -- the file was 465 lines before gaining a second scope. The night
body drops the range's build-up curve, which describes the range rather
than the night, and lights up the per-night clamp state RateBand has always
supported but never been given.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N2Zqrn8wX2qG52w9qytSw9
EOF
)"
```

---

## PHASE 8 — Warn before a bulk accept overwrites hand-tuned nights

**Spec sections:** decision D-b.

**Files:**
- Modify: `apps/web/components/rangeDrawer/RangeDrawerShell.tsx`
- Modify: `apps/web/components/rangeDrawer/RangeDrawer.test.tsx`
- Modify: `apps/web/messages/{en,vi}.json`

**Interfaces:**
- Consumes: `RangeNight.decision` (Phase 5), `acceptRange(..., preserve_overrides)` (Phase 5).

- [ ] **Step 1: Add the message keys**

`en.json` under `drawer`:

```json
    "handTunedKept": "{count, plural, one {# night you priced by hand will be kept} other {# nights you priced by hand will be kept}}",
    "handTunedOverwrite": "Overwrite them too",
    "handTunedOverwriting": "Hand-priced nights will be overwritten",
    "handTunedKeep": "Keep them"
```

`vi.json` under `drawer`:

```json
    "handTunedKept": "{count, plural, other {# đêm bạn đã chỉnh tay sẽ được giữ nguyên}}",
    "handTunedOverwrite": "Ghi đè cả những đêm này",
    "handTunedOverwriting": "Những đêm đã chỉnh tay sẽ bị ghi đè",
    "handTunedKeep": "Giữ nguyên"
```

- [ ] **Step 2: Write the failing tests**

Append to `apps/web/components/rangeDrawer/RangeDrawer.test.tsx`:

```tsx
  it("warns before a bulk accept would replace a hand-tuned night", async () => {
    payload = detail({
      nightly: [nightAt(1), nightAt(2, { decision: "overridden" }), nightAt(3)],
    });
    renderWithIntl(
      <RangeDrawer selection={selection} onClose={() => {}} onChanged={() => {}} />,
    );
    expect(await screen.findByText(/priced by hand will be kept/i)).toBeTruthy();
    // The button names what it will actually write, not what was selected.
    expect(screen.getByRole("button", { name: /2 nights/i })).toBeTruthy();
  });

  it("lets the operator overwrite hand-tuned nights on purpose", async () => {
    payload = detail({
      nightly: [nightAt(1), nightAt(2, { decision: "overridden" }), nightAt(3)],
    });
    renderWithIntl(
      <RangeDrawer selection={selection} onClose={() => {}} onChanged={() => {}} />,
    );
    await userEvent.click(
      await screen.findByRole("button", { name: /overwrite them too/i }),
    );
    await userEvent.click(screen.getByRole("button", { name: /3 nights/i }));
    expect(acceptRange).toHaveBeenCalledWith(2, "2026-09-01", "2026-09-03", false);
  });

  it("does not warn when nothing was priced by hand", async () => {
    renderWithIntl(
      <RangeDrawer selection={selection} onClose={() => {}} onChanged={() => {}} />,
    );
    await screen.findByText("2BR Premium");
    expect(screen.queryByText(/priced by hand/i)).toBeNull();
  });
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd apps/web && npx vitest run components/rangeDrawer/RangeDrawer.test.tsx
```

- [ ] **Step 4: Implement it in the shell**

Add the state and the hand-tuned set:

```tsx
const [overwriteHandTuned, setOverwriteHandTuned] = useState(false);

const handTuned = (detail?.nightly ?? []).filter((n) => n.decision === "overridden");
```

**Replace** the `nightsToWrite` you defined in Phase 7 with:

```tsx
// What the button will ACTUALLY write. An accept that preserves hand-tuned
// nights covers fewer nights than the operator selected, and a button that
// names the selection rather than the outcome is the same class of quiet
// partial success as an unpriced night written as zero.
const nightsToWrite =
  scope === "night"
    ? 1
    : detail.nights - detail.unpriced_nights -
      (overwriteHandTuned ? 0 : handTuned.length);
```

Reset `overwriteHandTuned` to `false` alongside `scope` when the selection
changes.

Render the notice above the action row, only in the range scope and only when
`handTuned.length > 0`, using the same amber block as `someUnpriced`:

```tsx
{scope === "range" && handTuned.length > 0 && (
  <div className="mb-2 flex items-center justify-between gap-2 rounded-lg border
    border-amber-200 bg-amber-50 px-2.5 py-1.5 text-[11.5px] text-amber-800">
    <span>
      {overwriteHandTuned
        ? t("handTunedOverwriting")
        : t("handTunedKept", { count: handTuned.length })}
    </span>
    <button
      type="button"
      onClick={() => setOverwriteHandTuned((v) => !v)}
      className="shrink-0 font-medium underline focus:outline-none
        focus-visible:ring-2 focus-visible:ring-brand-500"
    >
      {overwriteHandTuned ? t("handTunedKeep") : t("handTunedOverwrite")}
    </button>
  </div>
)}
```

Pass the flag through:

```tsx
api.acceptRange(
  detail.room_type_id,
  target.start,
  target.end,
  scope === "night" ? true : !overwriteHandTuned,
)
```

- [ ] **Step 5: Run the tests**

```bash
cd apps/web && npx vitest run components/rangeDrawer/RangeDrawer.test.tsx
```

- [ ] **Step 6: Run everything**

```bash
cd apps/web && npm test && npm run check:messages && npx tsc --noEmit
make test && make lint
```

- [ ] **Step 7: Review focus**

- Does the accept button's night count match what the server will write, in
  **both** states of the toggle?
- Is the notice hidden in the night scope? Accepting one night never touches a
  neighbour.
- Does `overwriteHandTuned` reset when the drawer opens on a different tile?
- Is the warning amber (a warning) while the strip marker stays violet (the
  overridden state)? Two different jobs, two different tokens — correct.

- [ ] **Step 8: Commit**

```bash
git add apps/web/components/rangeDrawer/ apps/web/messages/
git commit -m "$(cat <<'EOF'
feat(web): warn before a bulk accept replaces hand-priced nights

The button now names what it will actually write rather than what was
selected, and the operator chooses whether to keep or overwrite. Silently
replacing a hand-tuned night would destroy the judgment the per-night scope
exists to capture.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N2Zqrn8wX2qG52w9qytSw9
EOF
)"
```

---

## PHASE 9 — Record the decision

**Files:**
- Modify: `docs/DECISIONS.md`
- Modify: `apps/web/CLAUDE.md`

- [ ] **Step 1: Append D40**

After D39 in `docs/DECISIONS.md`:

```markdown
## D40 — A bulk accept preserves hand-priced nights, and says so first

**The change.** `POST /api/rate/accept` now skips nights whose recommendation
is already `overridden`, and reports them as `skipped_overridden`. The drawer
names the count before the operator clicks and offers to overwrite them
anyway. This amends D36, which had a bulk accept replace every decision
without prompting.

**Why it changed.** D36's rule was right while the range was the only unit of
work: the operator asked for a bulk action and got one. The drawer now has a
per-night scope, so an operator can accept a week and then tune one night —
and the next bulk accept would silently destroy exactly the judgment the new
scope exists to capture. D36 anticipated this: "Protecting a prior manual
override stays a small change: the `decision` field already distinguishes
accepted from overridden." It was.

**Why preserve is the default at the API and overwrite is the default in the
service.** `apply_to_range(preserve_overrides=False)` keeps every existing
caller behaving as before; `RangeDecisionIn.preserve_overrides = True` makes
the operator-facing action the safe one. An override always writes what the
operator typed and never preserves.

**What it cost.** The accept button no longer names the number of nights the
operator selected — it names the number it will write. A button whose count
disagrees with the selection needs the notice above it to explain why, which
is the same pattern already used for unpriced nights.

---

## D41 — The drawer has two scopes over one payload

**The change.** The Rate drawer switches between the whole range and a single
night. `GET /api/rate/range` grew to serve each night's adjustments, band,
provenance, clamp state and distance from the range average, so the night
scope renders from the same fetch with no second request.

**Why one payload.** Switching scope or night is a view change, not a
navigation. A spinner between nights would make comparing them — the entire
reason the scope exists — feel like a page load.

**Why no new endpoint.** A single day is a range of length one (D35), and
because the engine has already rounded each night to the increment,
`aggregate_range` over one night is the identity. Accepting one night is
`apply_to_range(start=X, end=X)`. One code path, as D35 intended.

**What the night scope shows that the range cannot.** The band's clamp
indicator. `RateBand` has always accepted `clamped`, and the range scope has
always passed `null` — correctly, since an average is not itself clamped. The
per-night scope is the first caller with a true answer to give it.

**What it drops.** The build-up curve. `PaceChart` plots the range; on a
screen whose whole job is one night, with the per-night strip directly beneath
it, it was describing something the reader was not looking at.

**The breakdown fix that came with it.** The averaged explanation grouped by
`(code, label_key)`, so `pace` rendered as up to five contradictory rows with
nothing saying which nights each covered, and `_average_params` printed
averaged integers as "4.5 days to arrival" and "2.333 bookings". Rows now
carry `nights_covered` and each is badged with it, so five pace rows reading
1 + 1 + 2 + 1 + 2 against a seven-night range visibly account for every night;
the sentences branch on that count in ICU and drop the figures that cannot be
averaged. The rows were never collapsed to one per factor: a range that is two
nights empty and two nights full would then render identically to one that is
evenly on pace, which is the disagreement D36's strip exists to expose.
```

- [ ] **Step 2: Note the drawer's new shape in `apps/web/CLAUDE.md`**

In the "Component architecture" section, after the paragraph about the three
components importing from `radix-ui` directly:

```markdown
- `components/rangeDrawer/` — the Rate drawer, split into a shell
  (`RangeDrawerShell`) plus one body per scope (`RangeScopeBody`,
  `NightScopeBody`). `components/RangeDrawer.tsx` is a re-export that keeps the
  original import path. The split happened when the drawer gained a second
  scope (D41): a `mode ?` conditional inside all five sections would have made
  every section dual-purpose in a file that was already 465 lines.
```

- [ ] **Step 3: Final verification**

```bash
make test && make lint
cd apps/web && npm test && npm run check:messages && npx tsc --noEmit
make bundle
```

`make bundle` catches anything that broke the static export.

- [ ] **Step 4: Commit**

```bash
git add docs/DECISIONS.md apps/web/CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: record D40 and D41

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N2Zqrn8wX2qG52w9qytSw9
EOF
)"
```

---

## Regression checklist

Run before opening a PR.

- [ ] `make test` — count is 535 + new tests, zero failures
- [ ] `cd apps/web && npm test` — zero failures
- [ ] `make lint` — ruff and the ICU/message check both clean
- [ ] `cd apps/web && npm run check:messages` — en and vi describe the same keys
- [ ] `cd apps/web && npx tsc --noEmit` — clean
- [ ] `make bundle` — the static export still builds
- [ ] `test_the_averaged_breakdown_sums_to_the_averaged_price` still green — the
      breakdown must reconcile exactly with the price above it
- [ ] Manual: `/vi/rate/`, open a tile, switch scopes, click through nights,
      confirm no sentence reads "4,5 ngày" or "2,333 lượt"
- [ ] Manual: accept a range, override one night, accept the range again —
      the hand-tuned night survives and the notice explains why
- [ ] Manual: a one-night range shows no scope tabs
