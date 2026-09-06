# Pricing Configuration Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Act on four operator-reported problems with the pricing configuration: the pickup expectation must be compared exactly as typed, the pickup window must be bounded to 7–14 days, every percentage input must step by a whole point, and a seasonal rate band with no MAX must save instead of returning a server error.

**Architecture:** All four are changes to flows that already exist. Three of them are backend-first: the rule lives in Python (`dynamic_pricing/pricing/defaults.py`, `features/engine.py`, `routers/rate_book.py`) and the frontend only renders or offers what the backend decides — D10. The fourth (the percentage step) is purely a frontend input affordance. No new modules, no new endpoints, no schema migration beyond a config-version bump that reseed handles.

**Tech Stack:** Python 3.10+ / FastAPI / SQLAlchemy / pytest on the backend; Next.js 15 (App Router, static export) / TypeScript / Tailwind / next-intl / Vitest + React Testing Library on the frontend.

**Spec:** This document, **Part 0** below. There is no separate spec file: the change set is four bounded fixes, and duplicating the reasoning across two documents would let them drift. Part 0 is the spec — read it before Phase 1, and argue from it if a phase's instructions ever seem to contradict it.

## Global Constraints

- **Two kinds of number, never mixed.** The seasonal MIN/BASE/MAX NET rate table is CLIENT-VALIDATED business fact (`pricing/rate_book.py`, `services/rate_book.py`, its own DB table, its own UI section). The dynamic layer — pace, pickup, events, market, day-of-week — is UNVALIDATED engineering invention (`pricing/defaults.py`). Never move a value from one side to the other, and never widen a validated guarantee to cover an unvalidated one.
- **D10 — no pricing logic in the frontend.** No multiplier, no threshold comparison, no derived percentage in a `.tsx` file. A `min`/`max`/`step` attribute on an `<input>` is an affordance, not logic, and is allowed — but the *rule* it mirrors must exist in Python, and Phase 3 adds a test that keeps the two copies in sync.
- **D17 — the season selects a band, it never scales one.** Nothing in this plan may introduce a seasonality factor.
- **D19 — the dynamic layer is additive percentages of BASE**, bounded, then clamped into the band. Do not make anything multiplicative.
- **D24 — config migrations happen by reseed, not Alembic.** A schema-version bump is followed by `make reseed`, not a migration script.
- **i18n contract.** The engine never composes a sentence: it emits a message *key* plus params, and `apps/web/messages/{en,vi}.json` render it. Any new message key needs a string in **both** locales or a backend test fails. Vietnamese is the default locale and is not optional.
- **Copy rules (`apps/web/CLAUDE.md`).** No ALL-CAPS labels for emphasis, no single capitalised word inside a sentence-case string. Colours: `ink-*` is warm charcoal, `brand-*` is antique brass, `emerald-*` is forest green — do not "fix" a colour by reasoning from the Tailwind class name.
- **Static export.** `apps/web` builds with `output: "export"`. Nothing may require a Next.js server runtime (middleware, server actions, ISR).
- **Surgical changes.** Every changed line must trace to one of the four requests. Do not refactor adjacent code, do not reformat, do not delete pre-existing dead code — note it instead.
- **Commit trailer.** Every commit in this plan ends with:

  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01Xq4byv5bSViXVxajrsxzoQ
  ```

- **Commit style.** Match the repo: a sentence-case imperative subject line, a body explaining *why*, no `feat:`/`fix:` prefixes.

---

# Part 0 — Orientation (read this first, even on a fresh session)

## What this product is

An explainable revenue-management copilot for one short-term rental property (Luminous Luxury Apartments), sitting above the Blue Jay PMS. It recommends a NET room rate per date, explains the recommendation in plain language, and lets an operator accept or override it. Nothing is ever pushed back to Blue Jay or any OTA — Shadow Mode, D22.

The pipeline:

```
Provider (Blue Jay / mock / snapshot)
  -> Feature Engine (features/)          measures occupancy, pickup, market, booking curve
  -> Seasonal Rate Book (pricing/rate_book.py)   CLIENT-VALIDATED MIN/BASE/MAX lookup
  -> Pricing Engine (pricing/engine.py)  bounded additive dynamic layer, clamped to the band
  -> Recommendation                      persisted with a reproducible snapshot
  -> Decision                            operator accept/override, never auto-applied
```

The two signals this plan touches:

- **Pace position** — `pace_gap = occupancy − expected_occupancy(category, season, days_to_arrival)`. The primary demand signal.
- **Recent pickup** — `pickup_delta = recent_pickup − expected_pickup`, where `recent_pickup` is the number of bookings created inside a lookback window. Deliberately a smaller lever than pace, because the two must not double-count the same demand.

Both are "actual minus expected", and both are compared against ordered configurable bands (`_band_for` in `pricing/engine.py`) to pick a percentage.

## The four requests, verbatim, and what each means

The operator wrote (Vietnamese):

1. *"Chênh (cái dùng để so sánh với mức) = Thực tế - Kì vọng (mình set)"* — the gap that gets compared against the band thresholds should be **actual minus the expectation we set**.
2. *"Fix luôn khoảng recent pickup: cho dao động từ 7-14 ngày để kết quả trả lại hợp lí"* — also fix the recent-pickup window: let it range over **7–14 days** so the results come back sensible.
3. *"Thứ trong tuần: chỉnh biên độ thay đổi % nhiều hơn được không (đang mặc định một cú click chuột là 0.5%)"* — day of week: can the percentage step be larger? One mouse click is currently 0.5%.
4. *"Hệ thống sẽ không hoạt động nếu giá MIN/BASE/MAX không có (hiện tại đang muốn không để giá MAX mà hoạt động luôn)"* — the system doesn't work when a MIN/BASE/MAX price is missing; they want to **leave MAX empty and still have it work**.

Investigation of the current code found:

| # | Finding |
|---|---|
| 1 | `pace_gap` and `pickup_delta` are already `actual − expected`. The one place the expectation is **not** what the operator typed is pickup: the Strategy field says *"Expected pickup per week"* and `features/engine.py` compares against `per_week × lookback_days / 7`. Set 1 with a 14-day window and the engine silently compares against 2. |
| 2 | `lookback_days` has no range at all. Any integer is accepted, including 0 and 400. |
| 3 | `NumberInput` in `StrategyPanel.tsx` defaults to `step={0.5}`, and `BandEditor`'s adjustment input hardcodes `step={0.5}`. Every one of those inputs is a percentage. |
| 4 | `routers/rate_book.py` guards with `min <= base <= max`. When MAX is `None` that chain evaluates `float <= None` and raises `TypeError`, so the save returns a server error. Everything else — the Pydantic schema, the DB column, `_coerce_ceiling`, the engine's clamp, the frontend's "empty means no ceiling" input — already handles a null MAX correctly. **ASSUMPTIONS U9 already documents an optional MAX as answered and working**, so the documentation currently promises behaviour the code breaks. |

## Decisions taken (do not re-litigate these mid-implementation)

- **Pickup expectation is compared as typed.** Rename `recent_pickup.expected_pickup_per_week` → `recent_pickup.expected_pickup_per_window` and drop the `× lookback/7` rescaling. Rejected: keeping per-week and merely displaying the derived number (leaves the operator's typed value not being the compared value); expressing pickup as a rate so bands are window-invariant (redefines every band threshold and message; nothing asks for it — YAGNI).
- **No legacy alias for the old key.** Hard rename, `CONFIG_SCHEMA_VERSION` 2 → 3, migration by reseed (D24). There is no live-tenant data to preserve.
- **The shipped default is unchanged in effect.** `lookback_days` stays 7 and the expectation stays 1.0, so `1.0/week × 7/7 = 1.0` and the default config prices *identically* after the rename. This is the main regression guard for Phase 2 — if a default-config pricing test changes value, something is wrong.
- **7–14 is enforced in Python**, reported as a translated validation problem, and mirrored as `min`/`max` on the input. Default stays 7.
- **1% step everywhere a percentage is entered** — day-of-week, band adjustments, event impacts, market max adjustment, dynamic bounds. Threshold steppers (`max_gap` 0.01, `max_delta` 0.25) and non-percentages (`sensitivity` 0.05, `min_observations` 1, `rounding.increment` 1000, `lookback_days` 1) keep their steps.
- **Docs:** one new `docs/DECISIONS.md` entry (D39) covering decisions 1 and 3 above, plus an ASSUMPTIONS U3 correction.
- **Branch:** a new branch off `main`. The `docs/fix-stale-docs` branch stays untouched for its own PR.

## Repo scan checklist — do this before Phase 1

Read, in this order. Do not skip: several of these files contain comments that explain *why* a line that looks wrong is right, and the codebase has a documented history of "fixes" that reintroduced bugs.

- [ ] `CLAUDE.md` (repo root) — the pipeline, the validated/unvalidated split, D10, the i18n contract, the commands.
- [ ] `apps/web/CLAUDE.md` — component architecture, design tokens, typography, the copy rules, the testing convention.
- [ ] `README.md` §"The pricing engine", §"Languages", §"Testing".
- [ ] `ASSUMPTIONS.md` — **U3** (recent-pickup thresholds; its "Current value" line is the one Phase 5 corrects) and **U9** (the optional MAX).
- [ ] `docs/DECISIONS.md` — skim the D1–D38 headings for house style, then read D17, D19, D24, D28, D30 in full.
- [ ] `apps/api/dynamic_pricing/pricing/defaults.py` — the whole file. This is the config schema, the coercion boundary, and the validator. The comments on `_deep_merge`, `_default_at`, `coerce_config` and `_band_problems` each record a specific past bug.
- [ ] `apps/api/dynamic_pricing/features/engine.py` lines 60–130 and 200–235 — the `_num` degradation helper (and the comment on why there is no `or default`), and the pickup/pace computation.
- [ ] `apps/api/dynamic_pricing/pricing/engine.py` — `_band_for` and `_recent_pickup`, to see how the delta reaches a band.
- [ ] `apps/api/dynamic_pricing/routers/rate_book.py` — `edit_band`.
- [ ] `apps/web/components/customisation/StrategyPanel.tsx` — the whole file (~600 lines).
- [ ] `apps/api/tests/conftest.py` — `make_context`, the `config`/`engine` fixtures, and `STAY`.

Then verify the baseline is green **before changing anything**:

```bash
cd /Users/tan.nguyen/Workspace/dynamic-pricing-property
make test                      # backend pytest — expect 527 passed
cd apps/web && npm test        # frontend Vitest
cd apps/web && npm run check:messages
```

If the baseline is not green, stop and report — do not start a phase on a red suite.

## Commands you will need

```bash
make test          # full backend suite (does NOT run frontend tests)
make lint          # ruff on the backend + real-ICU parse of every message
make reseed        # rebuild the demo DB from scratch (required after a config schema change)
make dev           # API on :8000 and web on :3000 together

# a single backend test
cd apps/api && .venv/bin/python -m pytest tests/test_file.py::test_name -q

# a single frontend test file
cd apps/web && npx vitest run components/customisation/StrategyPanel.test.tsx
```

## Branch setup (do this once, before Phase 1)

```bash
cd /Users/tan.nguyen/Workspace/dynamic-pricing-property
git status                      # must be clean; stash -u anything that is not
git checkout main
git checkout -b feat/pricing-config-fixes
```

## The phase cycle — every phase follows this, without exception

1. **Read** the phase in this plan, start to finish, before touching anything.
2. **Investigate** — open every file the phase names and read the surrounding code and comments. Confirm the described current state actually matches what you see. If it does not, stop and report the discrepancy rather than improvising.
3. **Red light** — write the tests exactly as given, run them, and *confirm they fail for the stated reason*. A test that passes before the implementation is a broken test; a test that fails with a different error than the plan predicts means the investigation was incomplete.
4. **Green light** — write the minimal implementation, run the phase's tests, then run the whole relevant suite (`make test` for backend phases, `npm test` for frontend ones) to prove nothing else moved.
5. **Focused review** — read your own `git diff` against the phase's review checklist. Every changed line must trace to this phase.
6. **Commit** with the given message.

**Never** skip the red light to "save time". **Never** widen a phase's scope because you noticed something else. If you find a real problem outside the phase, write it in your final report and leave the code alone.

---

# Phase 1 — A rate band with no MAX must save, not fail

**Why first:** it is the smallest change, it is entirely backend, and it fixes an outright server error the operator hits today. Nothing else in this plan depends on it.

**Files:**
- Modify: `apps/api/dynamic_pricing/routers/rate_book.py` — the guard inside `edit_band` (line 85 as of writing)
- Test: `apps/api/tests/test_api_workflow.py` — new tests after `test_rate_band_rejects_inverted_bounds` (~line 113)

**Interfaces:**
- Consumes: `PUT /api/rate-book/{band_id}` with body `RateBandUpdateIn(min_net_rate: float, base_net_rate: float, max_net_rate: float | None = None)` (`schemas.py:64-69`); `update_band(session, band_id, *, min_net_rate, base_net_rate, max_net_rate)` (`services/rate_book.py:93`), which already routes a `None` through `_coerce_ceiling` and stores it as SQL NULL.
- Produces: nothing new. The endpoint's contract is unchanged for a band that has a MAX; it stops raising for one that does not.

**Read before starting:** `ASSUMPTIONS.md` U9 (which already declares an optional MAX to be working), `services/rate_book.py:81-117`, and the ordering note at the top of `tests/test_api_workflow.py` — that module shares one database across tests and several tests are destructive, which is why the tests below pass `?regenerate=false` and reset what they touch.

- [ ] **Step 1: Write the failing tests**

Add to `apps/api/tests/test_api_workflow.py`, immediately after `test_rate_band_rejects_inverted_bounds`:

```python
def test_a_band_saves_with_no_ceiling_at_all(client):
    """An absent MAX is legitimate (ASSUMPTIONS U9): the season imposes no
    ceiling of its own and the dynamic bound is the only limit.

    The guard chained `min <= base <= max` straight into a None, so Python
    compared a float with None and the operator's save came back as a server
    error -- while the schema, the column, the engine's clamp and the input that
    sends null all handled the absence correctly.
    """
    band = next(
        b for b in client.get("/api/rate-book").json() if b["max_net_rate"] is not None
    )
    saved = client.put(
        f"/api/rate-book/{band['id']}?regenerate=false",
        json={
            "min_net_rate": band["min_net_rate"],
            "base_net_rate": band["base_net_rate"],
            "max_net_rate": None,
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["max_net_rate"] is None

    # ...and the absence survives the round trip rather than coming back as 0,
    # which would clamp every recommendation for that season down to nothing.
    reread = next(b for b in client.get("/api/rate-book").json() if b["id"] == band["id"])
    assert reread["max_net_rate"] is None

    client.post("/api/rate-book/reset?regenerate=false")


def test_a_band_with_no_ceiling_still_rejects_a_min_above_its_base(client):
    """Dropping the ceiling must not drop the floor check with it."""
    band = client.get("/api/rate-book").json()[0]
    response = client.put(
        f"/api/rate-book/{band['id']}?regenerate=false",
        json={
            "min_net_rate": band["base_net_rate"] + 100_000,
            "base_net_rate": band["base_net_rate"],
            "max_net_rate": None,
        },
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_api_workflow.py -k "no_ceiling" -v
```

Expected: **FAIL**. `TestClient` re-raises server exceptions by default, so the first test raises `TypeError: '<=' not supported between instances of 'float' and 'NoneType'` from `routers/rate_book.py`. The second test fails the same way (the chain raises before it can return 422).

If instead you see a 422 or a 200, stop: the guard is not the code this plan describes, and the investigation needs redoing.

- [ ] **Step 3: Write the minimal implementation**

In `apps/api/dynamic_pricing/routers/rate_book.py`, replace the single chained guard:

```python
    if not (body.min_net_rate <= body.base_net_rate <= body.max_net_rate):
        raise HTTPException(
            status_code=422, detail="Rate band must satisfy MIN <= BASE <= MAX."
        )
```

with two guards that treat the ceiling as optional:

```python
    if body.min_net_rate > body.base_net_rate:
        raise HTTPException(status_code=422, detail="Rate band must satisfy MIN <= BASE.")
    # MAX is optional (ASSUMPTIONS U9): absent, the season imposes no ceiling and
    # the dynamic bound is the only limit. Chaining it into the comparison above
    # compared a float with None and turned a legitimate save into a 500.
    if body.max_net_rate is not None and body.base_net_rate > body.max_net_rate:
        raise HTTPException(status_code=422, detail="Rate band must satisfy BASE <= MAX.")
```

Change nothing else in the file.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_api_workflow.py -k "no_ceiling" -v
cd apps/api && .venv/bin/python -m pytest tests/test_api_workflow.py -q
make test
```

Expected: the two new tests PASS, `test_rate_band_rejects_inverted_bounds` still PASSES (it sends MIN 5,000,000 above BASE 2,000,000, so the first guard fires), and the full suite is green with two more tests than the baseline.

- [ ] **Step 5: Focused review**

Read `git diff` and confirm:
- Exactly two files changed, and the router diff is the guard and nothing else.
- No change to `services/rate_book.py`, `schemas.py`, or `models.py` — they already handled a null ceiling.
- The new tests restore what they touched (`?regenerate=false` on every write, plus the reset), so the shared module database is left as they found it.
- The `detail` strings stay English. They are developer-facing and are surfaced verbatim by `SeasonalPanel`; translating them is a separate piece of work, not this phase's.

- [ ] **Step 6: Commit**

```bash
git add apps/api/dynamic_pricing/routers/rate_book.py apps/api/tests/test_api_workflow.py
git commit -m "$(cat <<'EOF'
Let a seasonal band save with no MAX instead of returning a server error

ASSUMPTIONS U9 already documents an optional MAX -- leaving it empty means
the season imposes no ceiling of its own and the dynamic bound is the only
limit -- and the schema, the nullable column, _coerce_ceiling, the engine's
clamp and the frontend input that sends null all honoured that. The API
guard did not: `min <= base <= max` chained straight into a None, so Python
compared a float with None and the operator's save came back as a 500.

Split into two guards so the floor is still checked and the ceiling is only
checked when there is one.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xq4byv5bSViXVxajrsxzoQ
EOF
)"
```

---

# Phase 2 — The pickup expectation is compared exactly as typed

**Why:** the operator's own formula is *Chênh = Thực tế − Kì vọng (mình set)*. Today the third term is not what they set — `features/engine.py` rescales it by `lookback_days / 7`, so a 14-day window silently doubles it. A hidden multiplier is the exact thing D17 forbids for seasonality and the exact thing this codebase's explainability premise rules out.

**Files:**
- Modify: `apps/api/dynamic_pricing/pricing/defaults.py` — `CONFIG_SCHEMA_VERSION` (line 27), the `recent_pickup` block (lines 71–82), `NUMERIC_LEAVES` (line 249), `validate_config`'s pickup floor (lines 530–538)
- Modify: `apps/api/dynamic_pricing/features/engine.py` — the NOTE comment (lines 80–87) and the expectation (line 222)
- Modify: `apps/api/tests/test_regressions.py` — the two floor computations (lines 160 and 273)
- Modify: `apps/web/components/customisation/StrategyPanel.tsx` — the expected-pickup `NumberInput` (lines 337–343)
- Modify: `apps/web/messages/en.json` and `apps/web/messages/vi.json` — `settings.expectedPickup`
- Test: `apps/api/tests/test_booking_curve_and_features.py` — new test after `test_recent_pickup_counts_only_the_lookback_window` (~line 177)

**Interfaces:**
- Consumes: the `session` fixture, `add_inventory(session, stay_date, sold=4, total=10, net_rate=2_100_000, **kw)`, `build(session, inv, config=None)` and `TODAY = date(2026, 9, 1)`, all defined in `tests/test_booking_curve_and_features.py`.
- Produces: config key `recent_pickup.expected_pickup_per_window: float` (was `expected_pickup_per_week`) and the `FeatureEngine.expected_pickup_per_window` attribute (was `expected_pickup_per_week`). `PricingContext.expected_pickup` keeps its name and meaning — "the number `recent_pickup` was compared against" — and is what the message `adjustments.recent_pickup.*.reason` interpolates as `{expected_pickup}`.

**Read before starting:** the NOTE comment at `features/engine.py:80-84` — it records why there is no `or default` on this read (`expected_pickup_per_week=0` means "expect no pickup", and `or` silently turned that into 1.0). Preserve that property. Also read `test_recent_pickup_counts_only_the_lookback_window`: it asserts `pickup_delta == 1.0` under the default 7-day config and **must keep passing unchanged** — that is the proof this rename does not move any default-config price.

- [ ] **Step 1: Write the failing test**

Add to `apps/api/tests/test_booking_curve_and_features.py`, immediately after `test_recent_pickup_counts_only_the_lookback_window`:

```python
def test_the_expected_pickup_is_the_number_the_operator_typed(session):
    """`Chênh = Thực tế − Kì vọng (mình set)`.

    The expectation compared against the pickup bands is the value in the
    config, full stop. It used to be rescaled by lookback_days/7, so an operator
    who typed 1 and widened the window to 14 days was silently compared against
    2 while the field they had just filled in still read 1.
    """
    rt = session.query(RoomType).first()
    stay = TODAY + timedelta(days=20)
    inv = add_inventory(session, stay)
    for i, booked in enumerate([TODAY - timedelta(days=1), TODAY - timedelta(days=9)]):
        session.add(
            Booking(external_id=f"B{i}", room_type_id=rt.id, stay_date=stay, booked_at=booked)
        )
    session.commit()

    config = default_config()
    config["recent_pickup"]["lookback_days"] = 14
    config["recent_pickup"]["expected_pickup_per_window"] = 1.0

    ctx = build(session, inv, config)
    assert ctx.recent_pickup == 2, "both bookings fall inside a 14-day window"
    assert ctx.expected_pickup == pytest.approx(1.0), "as typed — not rescaled to 2.0"
    assert ctx.pickup_delta == pytest.approx(1.0)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_booking_curve_and_features.py::test_the_expected_pickup_is_the_number_the_operator_typed -v
```

Expected: **FAIL** on `assert ctx.expected_pickup == pytest.approx(1.0)`, with the actual value `2.0` — the new key is not read at all, so the default 1.0 is taken from `expected_pickup_per_week` and multiplied by `14 / 7`.

- [ ] **Step 3: Write the implementation**

**3a.** `apps/api/dynamic_pricing/pricing/defaults.py` — bump the schema version (line 27):

```python
# 3: recent_pickup.expected_pickup_per_week became expected_pickup_per_window,
#    compared as typed rather than rescaled by the window length (D39).
CONFIG_SCHEMA_VERSION = 3
```

**3b.** the same file, the `recent_pickup` block — rename the key and say what it means now:

```python
    "recent_pickup": {
        "enabled": True,
        "lookback_days": 7,
        # Compared AS TYPED (D39): whatever number is here is what the window's
        # booking count is measured against, whatever the window's length. It is
        # NOT a per-week figure the engine rescales -- that made the compared
        # expectation differ from the one the operator filled in.
        "expected_pickup_per_window": 1.0,
```

Leave `bands`, and every threshold in it, exactly as they are.

**3c.** the same file, `NUMERIC_LEAVES` (line 249):

```python
    ("recent_pickup.expected_pickup_per_window", float),
```

**3d.** the same file, `validate_config`'s pickup section — drop the rescaling:

```python
    pickup = config.get("recent_pickup", {})
    if pickup.get("enabled", True):
        expected = float(pickup.get("expected_pickup_per_window", 1.0) or 1.0)
        # recent_pickup cannot be negative, so -expected is the true floor.
        problems += _band_problems(
            pickup.get("bands", []), "max_delta", "recent_pickup", -expected, float("inf"), True
        )
```

Keep the `or 1.0` exactly as it is. It is inconsistent with the feature engine's treatment of a 0 expectation, but changing it here would newly reject a configuration that is accepted today, which is outside this phase. Note it in your report.

**3e.** `apps/api/dynamic_pricing/features/engine.py` — the read (line 87) and the NOTE above it (lines 80–84). Update the comment's key name and keep its point intact:

```python
        # NOTE: no `or default` here. Coercion guarantees a number, so `or`
        # is no longer defensive -- it is the only thing that could corrupt a
        # legitimate 0. expected_pickup_per_window=0 means "expect no pickup",
        # and silently reading it as 1.0 shifted pickup_delta by a full unit on
        # every row while the UI displayed the 0 the operator saved.
        pickup_cfg = self.config.get("recent_pickup", {}) or {}
        self.pickup_lookback_days = _num(pickup_cfg, "lookback_days", 7, int)
        self.expected_pickup_per_window = _num(
            pickup_cfg, "expected_pickup_per_window", 1.0, float
        )
```

**3f.** the same file, the expectation (line 222):

```python
        # --- recent pickup (acceleration, distinct from pace position) ----
        # The expectation is compared as typed (D39). Rescaling it by the window
        # meant the number the operator entered was not the number the bands were
        # measured against.
        expected_pickup = self.expected_pickup_per_window
```

**3g.** `apps/api/tests/test_regressions.py` — the two floor computations. Line 160, in `test_pickup_stalled_band_is_reachable_at_the_floor`:

```python
    floor = 0 - config["expected_pickup_per_window"]
```

and line 273, in `test_every_configured_band_is_reachable`:

```python
    floor = -pickup["expected_pickup_per_window"]
```

Both keep their surrounding assertions unchanged: the default expectation is 1.0, so the floor is still exactly −1.0, which is exactly the "Pickup stalled" threshold, which is why that band's comparison is inclusive.

**3h.** `apps/web/components/customisation/StrategyPanel.tsx` — the expected-pickup field:

```tsx
              <Field label={t("expectedPickup")}>
                <NumberInput
                  step={0.1}
                  value={draft.recent_pickup.expected_pickup_per_window}
                  onChange={(v) => update(["recent_pickup", "expected_pickup_per_window"], v)}
                />
              </Field>
```

**3i.** `apps/web/messages/en.json` — `settings.expectedPickup`:

```json
    "expectedPickup": "Expected pickup over the window (units)",
```

**3j.** `apps/web/messages/vi.json` — the same key. Keep "cửa sổ theo dõi", which is already how `settings.lookbackDays` names the window in Vietnamese:

```json
    "expectedPickup": "Lượng đặt kỳ vọng trong cửa sổ theo dõi (căn)",
```

Do not rename the message *key* — it is `settings.expectedPickup` in both files and is referenced by name in `StrategyPanel.tsx`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_booking_curve_and_features.py -q
cd apps/api && .venv/bin/python -m pytest tests/test_regressions.py tests/test_specifications_stay_true.py -q
make test
cd apps/web && npm test && npm run check:messages
make lint
```

Expected: all green. Pay particular attention to three tests that police this change and will fail loudly if a step was missed:
- `test_numeric_leaf_coverage_is_complete` — fails if the `NUMERIC_LEAVES` entry still names the old key.
- `test_recent_pickup_counts_only_the_lookback_window` — must pass **unchanged**, proving the default config still prices identically.
- `test_the_locales_describe_exactly_the_same_things` — fails if only one locale file was edited.

Then rebuild the demo database, because the saved config row still carries the old key (D24 — migration by reseed):

```bash
make reseed
```

- [ ] **Step 5: Focused review**

Read `git diff` and confirm:
- No occurrence of `expected_pickup_per_week` remains anywhere: `grep -rn "expected_pickup_per_week" --include="*.py" --include="*.tsx" --include="*.json" . | grep -v node_modules | grep -v "\.venv"` returns nothing.
- The `× lookback / 7` arithmetic is gone from **both** places it lived — `features/engine.py` and `validate_config`.
- `lookback_days` still defaults to 7 and the expectation still defaults to 1.0, so no default-config price moved.
- No band threshold changed.
- The NOTE comment about `or default` and a legitimate 0 is intact, with the key name updated.
- No new pricing logic appeared in any `.tsx` file (D10).

- [ ] **Step 6: Commit**

```bash
git add apps/api/dynamic_pricing/pricing/defaults.py apps/api/dynamic_pricing/features/engine.py apps/api/tests/test_booking_curve_and_features.py apps/api/tests/test_regressions.py apps/web/components/customisation/StrategyPanel.tsx apps/web/messages/en.json apps/web/messages/vi.json
git commit -m "$(cat <<'EOF'
Compare recent pickup against the expectation as typed, not rescaled

The Strategy field read "Expected pickup per week" and the feature engine
compared the window's booking count against `per_week * lookback_days / 7`.
An operator who typed 1 and widened the window to 14 days was silently
measured against 2 -- a hidden multiplier in the one part of this system
whose premise is that an operator can add the numbers up by hand.

Renamed recent_pickup.expected_pickup_per_week to expected_pickup_per_window
and dropped the rescaling in both places it lived: the feature engine and the
validator's band floor. CONFIG_SCHEMA_VERSION 2 -> 3; migration by reseed
(D24). The shipped default is unchanged in effect -- 1.0 over a 7-day window
is what 1.0/week x 7/7 already was -- so no default-config price moves.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xq4byv5bSViXVxajrsxzoQ
EOF
)"
```

---

# Phase 3 — The pickup window is bounded to 7–14 days

**Why:** `lookback_days` accepts any integer today, including values that make the signal meaningless. The operator asked for 7–14. The rule belongs in Python (D10); the input's `min`/`max` is the affordance that stops them typing a value the save would reject.

**Files:**
- Modify: `apps/api/dynamic_pricing/pricing/defaults.py` — new module constants, `PROBLEM_CODES` (line 199), `validate_config` (line 530)
- Modify: `apps/web/components/customisation/StrategyPanel.tsx` — `NumberInput` gains optional `min`/`max`, the lookback field passes 7/14
- Modify: `apps/web/messages/en.json`, `apps/web/messages/vi.json` — `validation.out_of_range`
- Modify: `apps/api/tests/test_localisation.py` — add an out-of-range payload to `bad_configs` in `test_every_validation_placeholder_is_supplied` (~line 620)
- Test: `apps/api/tests/test_regressions.py` — new parametrised validator test
- Test: `apps/api/tests/test_specifications_stay_true.py` — new Python↔TSX range-sync test
- Create: `apps/web/components/customisation/StrategyPanel.test.tsx`

**Interfaces:**
- Consumes: `_problem(code, message, *, path=None, **params) -> dict` and `prepare_config(payload) -> dict` / `ConfigurationInvalid(problems)` from `pricing/defaults.py`; `WEB_ROOT` (`= API_ROOT.parent / "web"`, line 337) in `tests/test_specifications_stay_true.py`; `renderWithIntl(ui)` from `apps/web/components/test-utils.tsx`.
- Produces: `PICKUP_LOOKBACK_MIN_DAYS = 7` and `PICKUP_LOOKBACK_MAX_DAYS = 14` in `pricing/defaults.py`; problem code `"out_of_range"` with params `minimum`, `maximum`, `value` and path `recent_pickup.lookback_days`; `NumberInput`'s optional `min`/`max` props; the `CONFIG_PAYLOAD` and `PREVIEW` fixtures in `StrategyPanel.test.tsx`, which Phase 4 reuses.

**Read before starting:** `validate_config` and `_band_problems` in `pricing/defaults.py` (the validator assumes already-coerced input — that is why `int(lookback)` below is safe); `preview_config`'s recovery behaviour (a problem carrying a path causes the whole affected *section* to be restored from the shipped defaults so the live preview still renders — so an out-of-range window previews as the default config, which is correct and consistent with every other validation problem); and `test_every_validation_placeholder_is_supplied` in `tests/test_localisation.py`, which is why a new problem code has to be reachable from that test's payload list.

- [ ] **Step 1: Write the failing backend tests**

**1a.** Add to `apps/api/tests/test_regressions.py`, at the end of the file:

```python
# --- the pickup window has to be a window ---------------------------------
@pytest.mark.parametrize("days,accepted", [(6, False), (7, True), (14, True), (15, False)])
def test_the_pickup_window_is_bounded_to_a_week_or_two(days, accepted):
    """Below a week a single weekend swings the signal; above two weeks it stops
    being "recent" and starts measuring the same demand pace already measures,
    which is the double-count the two signals exist to avoid.

    Enforced in Python, not just as an input attribute: the input is an
    affordance, and an affordance is not a rule.
    """
    from dynamic_pricing.pricing.defaults import ConfigurationInvalid, prepare_config

    if accepted:
        prepared = prepare_config({"recent_pickup": {"lookback_days": days}})
        assert prepared["recent_pickup"]["lookback_days"] == days
        return

    with pytest.raises(ConfigurationInvalid) as caught:
        prepare_config({"recent_pickup": {"lookback_days": days}})
    problems = caught.value.problems
    assert "out_of_range" in [p["code"] for p in problems]
    offending = next(p for p in problems if p["code"] == "out_of_range")
    assert offending["path"] == "recent_pickup.lookback_days"
    assert offending["params"]["minimum"] == 7
    assert offending["params"]["maximum"] == 14
```

**1b.** Add to `apps/api/tests/test_specifications_stay_true.py`, at the end of the file:

```python
# --------------------------------------------------------------------------
# An input's range and the rule it mirrors are two copies of one fact
# --------------------------------------------------------------------------
def test_the_lookback_input_offers_exactly_the_range_the_backend_enforces():
    """The min/max on the input is an affordance; the rule lives in Python (D10).

    Two copies of the same numbers drift, and this drift is invisible in the
    worst way: the input would happily offer a window the save then rejects,
    and the operator would read a validation error about a value the UI told
    them was allowed.
    """
    import re

    from dynamic_pricing.pricing.defaults import (
        PICKUP_LOOKBACK_MAX_DAYS,
        PICKUP_LOOKBACK_MIN_DAYS,
    )

    source = (
        WEB_ROOT / "components" / "customisation" / "StrategyPanel.tsx"
    ).read_text(encoding="utf-8")
    match = re.search(r'lookbackDays[\s\S]{0,400}?</Field>', source)
    assert match, "the lookback field is no longer recognisable in StrategyPanel.tsx"

    field = match.group(0)
    assert f"min={{{PICKUP_LOOKBACK_MIN_DAYS}}}" in field, (
        f"the lookback input does not offer min={PICKUP_LOOKBACK_MIN_DAYS}, which is "
        f"the floor validate_config enforces"
    )
    assert f"max={{{PICKUP_LOOKBACK_MAX_DAYS}}}" in field, (
        f"the lookback input does not offer max={PICKUP_LOOKBACK_MAX_DAYS}, which is "
        f"the ceiling validate_config enforces"
    )
```

- [ ] **Step 2: Run the backend tests to verify they fail**

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_regressions.py -k "pickup_window_is_bounded" -v
cd apps/api && .venv/bin/python -m pytest tests/test_specifications_stay_true.py -k "lookback_input" -v
```

Expected: the parametrised test FAILS on the `6` and `15` cases (`DID NOT RAISE ConfigurationInvalid`) and PASSES on `7` and `14` — those two are already accepted, and that is the point of including them. The sync test FAILS on `ImportError: cannot import name 'PICKUP_LOOKBACK_MIN_DAYS'`.

- [ ] **Step 3: Write the backend implementation**

**3a.** `apps/api/dynamic_pricing/pricing/defaults.py` — add the constants directly above `DEMO_DEFAULTS` (after `CONFIG_SCHEMA_VERSION`):

```python
# The operator-tunable bounds on the recent-pickup window, in days. Bounded
# because the signal stops meaning what it says outside them: under a week one
# weekend swings it, and over two it stops being "recent" and starts measuring
# the same demand that pace position already measures -- the double-count the
# two signals are separated to avoid. UNVALIDATED, like everything in this file.
PICKUP_LOOKBACK_MIN_DAYS = 7
PICKUP_LOOKBACK_MAX_DAYS = 14
```

**3b.** the same file, `PROBLEM_CODES` — add the new code (keep the tuple's existing order, append before the closing paren):

```python
    "not_an_allowed_value",
    "out_of_range",
)
```

**3c.** the same file, `validate_config` — check the range *before* the band floor, inside the existing `enabled` guard:

```python
    pickup = config.get("recent_pickup", {})
    if pickup.get("enabled", True):
        lookback = pickup.get("lookback_days")
        if lookback is not None and not (
            PICKUP_LOOKBACK_MIN_DAYS <= int(lookback) <= PICKUP_LOOKBACK_MAX_DAYS
        ):
            problems.append(
                _problem(
                    "out_of_range",
                    f"recent_pickup.lookback_days must be between "
                    f"{PICKUP_LOOKBACK_MIN_DAYS} and {PICKUP_LOOKBACK_MAX_DAYS}; "
                    f"got {lookback}.",
                    path="recent_pickup.lookback_days",
                    minimum=PICKUP_LOOKBACK_MIN_DAYS,
                    maximum=PICKUP_LOOKBACK_MAX_DAYS,
                    value=int(lookback),
                )
            )
        expected = float(pickup.get("expected_pickup_per_window", 1.0) or 1.0)
        # recent_pickup cannot be negative, so -expected is the true floor.
        problems += _band_problems(
            pickup.get("bands", []), "max_delta", "recent_pickup", -expected, float("inf"), True
        )
```

**3d.** `apps/web/messages/en.json` — add to the `validation` object, after `not_an_allowed_value`:

```json
    "out_of_range": "{path} must be between {minimum, number} and {maximum, number} — {value, number} is outside that.",
```

**3e.** `apps/web/messages/vi.json` — the same key, same position:

```json
    "out_of_range": "{path} phải nằm trong khoảng {minimum, number}–{maximum, number} — {value, number} nằm ngoài khoảng đó.",
```

**3f.** `apps/api/tests/test_localisation.py` — make the new code reachable from the placeholder check. In `test_every_validation_placeholder_is_supplied`, add one entry to `bad_configs`:

```python
        {"recent_pickup": {"lookback_days": 30}},
```

- [ ] **Step 4: Run the backend tests to verify they pass**

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_regressions.py -k "pickup_window_is_bounded" -v
cd apps/api && .venv/bin/python -m pytest tests/test_specifications_stay_true.py -k "lookback_input" -v
```

Expected: the parametrised test is PASS on all four cases. The sync test still **FAILS** — the input does not carry `min`/`max` yet. That is the next step's red light.

Also run the localisation suite, which must already be green:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_localisation.py -q
```

Expected: PASS. `test_every_configuration_problem_code_has_a_translation` covers the new code in both locales, and `test_every_validation_placeholder_is_supplied` now exercises it.

- [ ] **Step 5: Write the failing frontend test**

Create `apps/web/components/customisation/StrategyPanel.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithIntl } from "@/components/test-utils";

// The panel loads its own configuration and preview on mount, so both calls are
// mocked. CONFIG_PAYLOAD is a FULL config: the panel reads every section
// directly (draft.pace.bands, draft.rounding.increment, ...) and a partial
// fixture throws before anything renders.
const CONFIG_PAYLOAD = {
  schema_version: 3,
  label: "test-defaults",
  currency: "VND",
  mode: "shadow",
  rounding: { increment: 10000, mode: "nearest" },
  dynamic: { max_total_adjustment_pct: 15, min_total_adjustment_pct: -15 },
  pace: {
    enabled: true,
    bands: [{ key: "on_pace", label: "On pace", max_gap: 0.08, adjustment_pct: 0 }],
  },
  recent_pickup: {
    enabled: true,
    lookback_days: 7,
    expected_pickup_per_window: 1,
    bands: [
      { key: "as_expected", label: "Pickup as expected", max_delta: 0.5, adjustment_pct: 0 },
    ],
  },
  event: { enabled: true, impact_adjustment_pct: { low: 3, medium: 8, high: 15 } },
  market: {
    enabled: true,
    min_confidence: "MEDIUM",
    min_observations: 2,
    observation_max_age_days: 14,
    sensitivity: 0.5,
    max_adjustment_pct: 5,
  },
  day_of_week: {
    enabled: true,
    adjustment_pct: {
      monday: 0,
      tuesday: 0,
      wednesday: 0,
      thursday: 0,
      friday: 0,
      saturday: 0,
      sunday: 0,
    },
  },
  booking_curve: { provider: "demo", anchors: null, season_pace: null, category_pace: null },
};

const PREVIEW = {
  problems: [],
  room_type_id: 1,
  room_type_name: "2BR Regular",
  room_category_label: "2BR Regular",
  room_category: "2br_regular",
  stay_date: "2026-09-10",
  currency: "VND",
  season_label: "Low Season 2",
  season_key: "low_2",
  band_min_net_rate: 1800000,
  band_base_net_rate: 2100000,
  band_max_net_rate: 2300000,
  base_net_rate: 2100000,
  current_net_rate: 2100000,
  recommended_net_rate: 2100000,
  change_pct: 0,
  total_adjustment_pct: 0,
  adjustments: [],
  engine_version: "1.0.0",
};

vi.mock("@/lib/api", () => ({
  api: {
    config: () =>
      Promise.resolve({
        version: 1,
        label: "test-defaults",
        payload: CONFIG_PAYLOAD,
        is_active: true,
        created_at: "2026-09-06T00:00:00",
        note: null,
      }),
    preview: () => Promise.resolve(PREVIEW),
    saveConfig: () => Promise.resolve({}),
    resetConfig: () => Promise.resolve({}),
  },
}));

import { StrategyPanel } from "./StrategyPanel";

describe("StrategyPanel — the pickup window", () => {
  it("offers only the range the backend accepts", async () => {
    renderWithIntl(<StrategyPanel onOpenSeasonal={() => {}} />);

    const input = await screen.findByLabelText("Lookback window (days)");
    expect(input).toHaveAttribute("min", "7");
    expect(input).toHaveAttribute("max", "14");
    expect(input).toHaveAttribute("step", "1");
  });
});
```

- [ ] **Step 6: Run the frontend test to verify it fails**

```bash
cd apps/web && npx vitest run components/customisation/StrategyPanel.test.tsx
```

Expected: **FAIL** on `expect(input).toHaveAttribute("min", "7")` — the element has no `min` attribute. The `step` assertion already passes (the field passes `step={1}` today) and is there to pin it.

If the test instead fails to render at all, the fixture is missing a section the panel reads — fix the fixture, not the panel.

- [ ] **Step 7: Write the frontend implementation**

**7a.** `apps/web/components/customisation/StrategyPanel.tsx` — give `NumberInput` optional bounds. The whole component becomes:

```tsx
function NumberInput({
  value,
  onChange,
  step = 0.5,
  min,
  max,
  suffix,
}: {
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  step?: number;
  min?: number;
  max?: number;
  suffix?: string;
}) {
  return (
    <div className="h-full overflow-y-auto relative">
      <Input
        type="number"
        step={step}
        min={min}
        max={max}
        className={`tnum ${suffix ? "pr-7" : ""}`}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
      {suffix && (
        <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[11px] text-ink-400">
          {suffix}
        </span>
      )}
    </div>
  );
}
```

(Leave `step = 0.5` alone here — Phase 4 changes it. One default, one phase.)

**7b.** the same file, the lookback field:

```tsx
              <Field label={t("lookbackDays")}>
                <NumberInput
                  step={1}
                  min={7}
                  max={14}
                  value={draft.recent_pickup.lookback_days}
                  onChange={(v) => update(["recent_pickup", "lookback_days"], v)}
                />
              </Field>
```

Do not add `min`/`max` to any other field in this phase.

- [ ] **Step 8: Run everything to verify green**

```bash
cd apps/web && npx vitest run components/customisation/StrategyPanel.test.tsx
cd apps/web && npm test && npm run check:messages
make test
make lint
```

Expected: all green, including the Python↔TSX sync test from Step 1b, which now finds `min={7}` and `max={14}` in the file.

- [ ] **Step 9: Focused review**

Read `git diff` and confirm:
- The rule exists in Python and the frontend only mirrors it — no comparison against 7 or 14 anywhere in a `.tsx` file other than the two input attributes (D10).
- `7` and `14` appear in exactly two places: the Python constants and the input's attributes, with a test tying them together.
- Both locale files have `validation.out_of_range`, both use the same three placeholders, and the Vietnamese is a real translation rather than a copy of the English.
- The `out_of_range` message follows the house copy rules — sentence case, no ALL-CAPS emphasis.
- The new `bad_configs` entry is the only change to `test_localisation.py`.
- The frontend fixtures live in the test file only; nothing test-shaped leaked into `StrategyPanel.tsx`.

- [ ] **Step 10: Commit**

```bash
git add apps/api/dynamic_pricing/pricing/defaults.py apps/api/tests/test_regressions.py apps/api/tests/test_specifications_stay_true.py apps/api/tests/test_localisation.py apps/web/components/customisation/StrategyPanel.tsx apps/web/components/customisation/StrategyPanel.test.tsx apps/web/messages/en.json apps/web/messages/vi.json
git commit -m "$(cat <<'EOF'
Bound the recent-pickup window to 7-14 days

lookback_days accepted any integer, including values that make the signal
meaningless: under a week one weekend swings it, and over two weeks it stops
being "recent" and starts measuring the same demand pace position already
measures -- the double-count the two signals are kept separate to avoid.

The rule is in validate_config as a new translated `out_of_range` problem, so
an API caller cannot bypass it; the input's min/max is the affordance that
stops an operator typing a value the save would reject. A new test reads the
range straight out of StrategyPanel.tsx and compares it with the Python
constants, because two copies of one fact drift silently.

Adds the first test for a customisation panel, with reusable config and
preview fixtures.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xq4byv5bSViXVxajrsxzoQ
EOF
)"
```

---

# Phase 4 — One click is one percentage point

**Why:** the operator asked for a bigger step than 0.5% on the day-of-week adjustments, and chose 1% for every percentage input rather than day-of-week alone — a percentage input that steps differently depending on which section it is in is its own small surprise.

**In scope:** `NumberInput`'s default step, and `BandEditor`'s adjustment-percentage step. Both are percentages at every call site: event impacts, market max adjustment, dynamic min/max total, day-of-week, and each band's adjustment.

**Explicitly NOT in scope:** the threshold steppers (`max_gap` 0.01, `max_delta` 0.25 — they are gaps and unit deltas, not percentages), `market.sensitivity` (0.05, a coefficient), `min_observations` (1, a count), `rounding.increment` (1000, VND), and `lookback_days` (1, days).

**Files:**
- Modify: `apps/web/components/customisation/StrategyPanel.tsx` — `NumberInput`'s `step` default, `BandEditor`'s adjustment `Input`
- Modify: `apps/web/components/customisation/StrategyPanel.test.tsx` — a second `describe` block

**Interfaces:**
- Consumes: the `CONFIG_PAYLOAD`, `PREVIEW` and `vi.mock("@/lib/api", …)` set up by Phase 3 in `StrategyPanel.test.tsx`. Do not duplicate them — append to the file.
- Produces: nothing other components consume.

**Read before starting:** every `NumberInput` call site in `StrategyPanel.tsx`, and confirm for yourself that each one relying on the default is a percentage. If you find one that is not, stop and report it rather than changing the default.

- [ ] **Step 1: Write the failing tests**

Append to `apps/web/components/customisation/StrategyPanel.test.tsx`:

```tsx
describe("StrategyPanel — percentage inputs", () => {
  it("steps a percentage by a whole point, in every section", async () => {
    renderWithIntl(<StrategyPanel onOpenSeasonal={() => {}} />);

    expect(await screen.findByLabelText("Monday")).toHaveAttribute("step", "1");
    expect(screen.getByLabelText("Low impact")).toHaveAttribute("step", "1");
    expect(screen.getByLabelText("Max total adjustment")).toHaveAttribute("step", "1");
    expect(screen.getByLabelText("Max adjustment")).toHaveAttribute("step", "1");
  });

  it("leaves no half-point stepper anywhere in the panel", async () => {
    const { container } = renderWithIntl(<StrategyPanel onOpenSeasonal={() => {}} />);
    await screen.findByLabelText("Lookback window (days)");

    // Covers the band adjustment inputs too, which carry no label of their own.
    expect(container.querySelectorAll('input[step="0.5"]')).toHaveLength(0);
  });

  it("leaves the inputs that are not percentages alone", async () => {
    renderWithIntl(<StrategyPanel onOpenSeasonal={() => {}} />);

    expect(await screen.findByLabelText("Sensitivity")).toHaveAttribute("step", "0.05");
    expect(screen.getByLabelText("Min observations")).toHaveAttribute("step", "1");
    expect(screen.getByLabelText("Rounding increment (VND)")).toHaveAttribute("step", "1000");
    expect(screen.getByLabelText("Expected pickup over the window (units)")).toHaveAttribute(
      "step",
      "0.1",
    );
  });
});
```

The labels come from `apps/web/messages/en.json` (`settings.maxTotal` = "Max total adjustment", `settings.maxAdjustment` = "Max adjustment", `settings.sensitivity`, `settings.minObservations`, `settings.roundingIncrement`, `settings.expectedPickup` as Phase 2 rewrote it) and from `vocab.days.monday` = "Monday". "Low impact" is built in the component itself — `` `${level[0].toUpperCase()}${level.slice(1)} impact` `` — and is, note, one of the few strings on this page that is not translated. That is pre-existing; leave it.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd apps/web && npx vitest run components/customisation/StrategyPanel.test.tsx
```

Expected: the first test FAILS (`expected step="1", received step="0.5"` on Monday), the second FAILS (it finds several `input[step="0.5"]`), and the third PASSES — it is the guard that the change does not spill into non-percentages.

- [ ] **Step 3: Write the implementation**

**3a.** `apps/web/components/customisation/StrategyPanel.tsx` — `NumberInput`'s default:

```tsx
function NumberInput({
  value,
  onChange,
  step = 1,
  min,
  max,
  suffix,
}: {
```

**3b.** the same file, in `BandEditor`, the adjustment-percentage input — change `step={0.5}` to `step={1}`:

```tsx
          <div className="relative">
            <Input
              type="number"
              step={1}
              className="tnum pr-7"
              value={band.adjustment_pct ?? ""}
```

Leave `thresholdStep` and its `0.01` / `0.25` defaults untouched.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd apps/web && npx vitest run components/customisation/StrategyPanel.test.tsx
cd apps/web && npm test
cd apps/web && npx tsc --noEmit
```

Expected: all three tests PASS and the whole frontend suite is green. `make test` is unaffected by this phase but run it anyway to be sure:

```bash
make test
```

- [ ] **Step 5: Focused review**

Read `git diff` and confirm:
- Exactly two numbers changed in `StrategyPanel.tsx`: `NumberInput`'s default and `BandEditor`'s adjustment step.
- No call site's explicit `step` was touched, so every non-percentage keeps its own.
- No `min`/`max` was added to anything in this phase.
- Nothing in the diff caps a percentage's *value*. The bound on the whole dynamic layer is `dynamic.min/max_total_adjustment_pct` in the engine, and it stays the only cap — a per-input `max` here would be a second, silent one.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/customisation/StrategyPanel.tsx apps/web/components/customisation/StrategyPanel.test.tsx
git commit -m "$(cat <<'EOF'
Step every percentage input by a whole point, not half

One click on a day-of-week adjustment moved it 0.5%, which is finer than the
operator wants to work and finer than any of these unvalidated numbers can
justify. Raised NumberInput's default step and the band adjustment's step to
1, which covers day-of-week, event impacts, the market cap, the dynamic
bounds and every band's percentage.

The steppers that are not percentages keep theirs: band thresholds (0.01 gap,
0.25 units), market sensitivity (0.05), min observations (1), the rounding
increment (1000 VND) and the lookback window (1 day). A test pins that.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xq4byv5bSViXVxajrsxzoQ
EOF
)"
```

---

# Phase 5 — Record the decisions and land the branch

**Why:** this repo keeps numbered engineering decisions (D1–D38) and a register of unvalidated guesses, and both currently describe behaviour that Phases 2 and 3 changed. `ASSUMPTIONS.md` U3's "Current value" line literally reads *"(7-day window, 1.0 unit/week expected)"*, and the "Ask the operator" question asks what counts as a normal *week's* pickup. A stale assumptions register is worse than none: it is what the client conversation is run from.

**Files:**
- Modify: `docs/DECISIONS.md` — new D39 at the end
- Modify: `ASSUMPTIONS.md` — U3's "Current value" and "Ask the operator" rows
- Modify: `README.md`, `CLAUDE.md`, `docs/RUNNING.md` — the backend test count
- Test: no new tests. The deliverable is verified by the full suite plus `make demo`.

**Interfaces:** none. Documentation only.

**Read before starting:** two or three existing D-entries in full (D35 and D37 are good models) to match the house style — a `## Dn — <claim as a sentence>` heading, then the decision, the reasoning, and what was rejected. Also re-read `ASSUMPTIONS.md` U3 and U9 in full.

- [ ] **Step 1: Add D39 to `docs/DECISIONS.md`**

Append after D38:

````markdown
## D39 — A configured expectation is compared exactly as typed, and the pickup window is bounded

The recent-pickup signal compares the bookings created inside a window against
an expectation the operator sets in Strategy. That expectation used to be
entered *per week* and rescaled by the window — `per_week × lookback_days / 7`
— so an operator who typed 1 and widened the window to 14 days was silently
measured against 2, while the field they had just filled in still read 1.

The signal is now measured against the number as typed:

```
pickup_delta = recent_pickup − expected_pickup_per_window
```

**Why.** The whole premise of this product is that an operator can add the
breakdown up by hand. A multiplier they cannot see between the field they fill
in and the number the bands compare against defeats that, and it is the same
class of error D17 rules out for seasonality: a factor applied on top of a
figure that already accounts for it. The convenience the rescaling bought —
a unit that stays meaningful when the window changes — is worth very little in
a tool with one property and a window that is set once.

**The window is bounded to 7–14 days.** `lookback_days` previously accepted any
integer. Under a week, one weekend's bookings swing the signal; over two weeks,
it stops being "recent" and starts measuring the same demand that pace position
already measures, which is the double-count the two signals are kept separate to
avoid. The bound is enforced in `validate_config` and reported as a translated
`out_of_range` problem, so an API caller cannot bypass it. The input's
`min`/`max` mirrors it as an affordance only, and a test reads the range out of
`StrategyPanel.tsx` and compares it against the Python constants — two copies of
one fact drift, and this drift would show up as a validation error about a value
the UI said was allowed.

**Cost.** `CONFIG_SCHEMA_VERSION` went 2 → 3 and the config key was renamed
`expected_pickup_per_week` → `expected_pickup_per_window`, with no legacy alias:
migration is by reseed (D24), and there is no live-tenant data. The shipped
default is unchanged in effect — 1.0 over a 7-day window is exactly what
1.0/week × 7/7 already was — so no default-config price moved.

**Rejected.** Keeping the per-week key and merely displaying the derived figure
beside the field: cheaper, but it leaves the operator's typed value still not
being the compared value. Expressing pickup as a rate so the bands become
window-invariant: a real idea, but it redefines every band threshold and every
pickup message, and nothing asks for it yet.

**Still unvalidated.** Every number here — the expectation, the bands, and the
7–14 bound itself — remains an engineering guess. See ASSUMPTIONS U3.
````

- [ ] **Step 2: Correct `ASSUMPTIONS.md` U3**

Change the "Current value" row from:

```
| **Current value** | delta < −1.0 → −3% · < −0.25 → −1.5% · ≤ +0.5 → 0% · ≤ +2 → +2% · > +2 → +4% (7-day window, 1.0 unit/week expected) |
```

to:

```
| **Current value** | delta < −1.0 → −3% · < −0.25 → −1.5% · ≤ +0.5 → 0% · ≤ +2 → +2% · > +2 → +4% (7-day window, 1.0 unit expected over that window). The window is operator-tunable between 7 and 14 days, and the expectation is compared as typed rather than rescaled — D39. |
```

Change the "Ask the operator" row from:

```
| **Ask the operator** | *"Over what window do you judge whether bookings are coming in well? What counts as a normal week's pickup for one apartment?"* |
```

to:

```
| **Ask the operator** | *"Over what window do you judge whether bookings are coming in well — a week, two? And over that window, how many bookings for one apartment is normal?"* |
```

Leave every other row, and every other U-entry, alone. U9 already describes an
optional MAX correctly — Phase 1 made the code match the document, so the
document needs no change.

- [ ] **Step 3: Update the backend test count**

The suite grew. Get the real number, then update every place that states it:

```bash
make test 2>&1 | tail -3     # read the "N passed" figure
grep -rn "527" README.md CLAUDE.md docs/RUNNING.md
```

Replace `527` with the new count in all four places:
- `README.md` line ~35 (`make test` runs 527 backend tests)
- `README.md` line ~342 (`make test    # 527 backend tests …`)
- `CLAUDE.md` line ~30 (`make test           # backend pytest suite (527 tests) …`)
- `docs/RUNNING.md` line ~74 (``make test`` should report **527 passed**)

Do not guess the number. Read it from the run.

- [ ] **Step 4: Verify the whole thing end to end**

```bash
make test
cd apps/web && npm test && npm run check:messages && npx tsc --noEmit
make lint
make reseed
make demo     # then open http://localhost:3000 and check the four changes by hand
```

By hand, in the app:
1. **Customisation → Strategy**: the expected-pickup field reads "over the window"; the lookback input refuses 6 and 15 and accepts 7–14; every percentage input moves by 1.0 per click; a band threshold still moves by 0.01 / 0.25.
2. Set the lookback to 14 with the expectation at 1 and confirm the live preview's pickup line says "versus 1 expected", not 2.
3. Type 30 into the lookback via the API (`curl -X POST 127.0.0.1:8000/api/settings/preview …`) or by removing the input's max in devtools, and confirm the amber problems list shows the translated out-of-range message — in Vietnamese on `/vi`.
4. **Customisation → Seasonal**: clear a MAX, save, and confirm it saves and the "no ceiling" note appears rather than an error.

- [ ] **Step 5: Focused review of the whole branch**

```bash
git log --oneline main..HEAD
git diff main..HEAD --stat
git diff main..HEAD
```

Confirm:
- Four commits, one per phase, each self-contained.
- Every changed line traces to one of the four requests. Nothing was reformatted, no adjacent code was "improved", no pre-existing dead code was deleted.
- No pricing logic entered the frontend (D10); no seasonality factor appeared anywhere (D17); the dynamic layer is still additive (D19).
- Both locale files changed together, every time either changed.
- The docs now describe the code that exists.

- [ ] **Step 6: Commit and open the PR**

```bash
git add docs/DECISIONS.md ASSUMPTIONS.md README.md CLAUDE.md docs/RUNNING.md
git commit -m "$(cat <<'EOF'
Record D39 and correct the stale pickup assumptions

ASSUMPTIONS U3 described a per-week expectation rescaled by the window and
asked the operator what a normal week's pickup is -- both untrue after the
rename, and U3 is what the client validation conversation is run from.

Adds D39 for the two decisions behind it: an expectation is compared as typed,
and the pickup window is bounded to 7-14 days with the rule in Python and the
input's range mirroring it. Also refreshes the backend test count in the four
places that state it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xq4byv5bSViXVxajrsxzoQ
EOF
)"

git push -u origin feat/pricing-config-fixes
gh pr create --base main --title "Four pricing-configuration fixes from operator feedback" --body "$(cat <<'EOF'
Four problems the operator reported, in four commits.

**1. The pickup expectation is compared exactly as typed.** The Strategy field
said "Expected pickup per week" while the engine compared against
`per_week × lookback_days / 7`, so a 14-day window silently doubled it.
Renamed to `expected_pickup_per_window`, rescaling dropped. Config schema
2 → 3, migration by reseed (D24). The shipped default prices identically.

**2. The pickup window is bounded to 7–14 days.** `lookback_days` accepted any
integer. The rule is enforced in `validate_config` as a translated
`out_of_range` problem; the input's min/max mirrors it, with a test tying the
two copies together.

**3. Every percentage input steps by a whole point.** One click was 0.5%.
Non-percentages — band thresholds, market sensitivity, the rounding increment,
the window in days — keep their own steps, pinned by a test.

**4. A rate band with no MAX saves instead of failing.** `min <= base <= max`
chained into a `None` and raised `TypeError`, so a legitimate save (ASSUMPTIONS
U9: an empty MAX means the season imposes no ceiling) returned a 500. Split
into two guards.

Plus D39 recording 1 and 2, and an ASSUMPTIONS U3 correction.

Adds the first test for a customisation panel — `StrategyPanel.test.tsx`, with
reusable config and preview fixtures.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01Xq4byv5bSViXVxajrsxzoQ
EOF
)"
```

---

# Appendix — Self-review of this plan

**Spec coverage.** Each of the four requests maps to a phase: request 1 → Phase 2; request 2 → Phase 3; request 3 → Phase 4; request 4 → Phase 1. The documentation consequences of requests 1 and 2 → Phase 5. Every decision recorded in Part 0 has an implementing step.

**Cross-phase name consistency.** `expected_pickup_per_window` is the config key in Phases 2, 3 (the validator's floor read) and 4 (the test fixture). `PICKUP_LOOKBACK_MIN_DAYS` / `PICKUP_LOOKBACK_MAX_DAYS` are introduced in Phase 3 and used by the sync test in the same phase. `CONFIG_PAYLOAD` / `PREVIEW` are created in Phase 3 Step 5 and consumed in Phase 4 Step 1. `NumberInput`'s `min`/`max` props are added in Phase 3 Step 7a and its `step` default is changed in Phase 4 Step 3a — deliberately split, so each phase owns one edit to that signature.

**Ordering constraints.** Phase 3 must run after Phase 2: its validator snippet reads `expected_pickup_per_window`, which Phase 2 introduces. Phase 4 must run after Phase 3: it appends to the test file Phase 3 creates. Phase 1 is independent and could run at any point. Phase 5 must run last.

**Observations found during investigation, deliberately NOT fixed here** (report them, leave the code alone):
- `SeasonalRateBook.all_bands()` (`apps/api/dynamic_pricing/pricing/rate_book.py:289`) has no callers anywhere in the repo, and its `float(maximum)` would raise on a band with no ceiling — dead code that would break if revived.
- `validate_config` reads the pickup expectation as `float(... or 1.0)`, so a deliberate expectation of `0` is validated as though it were `1.0`. The feature engine deliberately does *not* do this (see its NOTE comment). Fixing the inconsistency would newly reject a config accepted today.
- The event-impact field labels in `StrategyPanel.tsx` are built in TypeScript as `` `${level} impact` `` and never translated — the only untranslated operator-facing labels on that page.
- The 422 `detail` strings from `PUT /api/rate-book/{id}` are English prose rendered verbatim by `SeasonalPanel`, unlike configuration problems, which are codes translated at render time.
