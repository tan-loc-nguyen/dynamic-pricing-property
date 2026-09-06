# Rate drawer: two scopes over one payload

**Date:** 2026-09-06
**Status:** approved, ready for implementation

## The request

From product, about the drawer opened by clicking a tile on the Rate page:

> Bây giờ khi mở cái drawer lên thì nó vẫn để giá trung bình của dãy ngày được
> chọn đó [...] chứ ko xem từng ngày giá như nào rồi điều chỉnh dc, phần "vì sao
> giá thay đổi" thì lại hiện 2 ngày trong tổng 7 ngày đó.
>
> Tôi muốn thay đổi nó lại là khi mở drawer thì tôi sẽ có thể chọn giữa 2 chế độ:
> - Chi tiết của dãy ngày được chọn như bây giờ -> chấp nhận ghi đè giá cho cả dãy ngày
> - Từng ngày để xem chi tiết của ngày đó -> chấp nhận ghi đè giá cho ngày được chọn

Two things are asked for: a per-night mode, and a fix to the "why the price
changed" breakdown.

## What the investigation found

The second half of the report was checked against the demo database before any
design work. **The literal claim is false — but a real defect sits underneath it.**

For 2BR Premium, 6/9 → 12/9 (7 nights), `/api/rate/range` returns **11
breakdown rows, not 2**. Nothing is truncated (`viz.tsx:224` maps every row),
all 7 nights are represented, and the rows sum exactly to the 2.310.000 ₫
headline. Coverage was never the problem.

What is actually wrong:

**1. Five contradictory `pace` rows, none saying which nights they cover.**
`aggregate_range` groups by `(code, label_key)`, and `pace` has 8 label
variants, so one factor renders as five mutually contradictory rows:

| row | delta | nights it actually covers |
|---|---|---|
| Đúng tiến độ | +0 | 6/9 |
| Chậm hơn | −13.714 | 7/9 |
| Chậm hơn nhiều | −54.857 | 8/9, 12/9 |
| Nhanh hơn nhiều | +27.429 | 9/9 |
| Nhanh hơn | +27.429 | 10/9, 11/9 |

The night attribution exists only in the raw data. The UI shows none of it.

**2. Every reason says "ngày này" (*this day*) while describing several nights.**
"Chậm hơn nhiều — Đã bán 19% khi còn 4 ngày… nên **ngày này** đang chậm hơn
43,55 điểm" is 8/9 *and* 12/9 averaged.

**3. Averaging integers prints impossible values.** `_average_params`
(`rate_range.py:123-141`) averages every numeric param:
- "khi còn **4,5 ngày** đến ngày nhận phòng" — half a day of lead time
- "**2,333 lượt đặt** trong 7 ngày qua" — 2.333 bookings
- "Giá tham chiếu **2.465.714,286 ₫**" — three decimals on a dong amount

**4. Where "2 ngày trong tổng 7 ngày" likely came from.** The line
"**2,333 lượt đặt trong 7 ngày qua**". In Vietnamese formatting `2,333` is
*2.333*, and `7 ngày` is the pickup lookback window — not the selected range.
Skimmed, it reads as "2 out of the 7 days". A pickup sentence misread as a day
count.

## Decisions taken

| # | Decision |
|---|---|
| D-a | Explicit two-mode switch, not a drill-down. Radix `Tabs`, matching `app/[locale]/customisation/page.tsx:30-61`. |
| D-b | Bulk accept **warns before the click** and preserves hand-tuned nights by default; overwriting is an explicit opt-in. Amends D36. |
| D-c | Breakdown rows are **labelled with the nights they cover**; rows are NOT collapsed to one per factor. |
| D-d | `OccupancyStrip` becomes the night picker. No separate chip strip. |
| D-e | Per-night price shown on the strip as a **signed % against the range average**, served from Python. |
| D-f | `PaceChart` is dropped in night mode; the strip carries neighbour context. |

### Why not collapse to one row per factor

Collapsing `pace` into a single averaged row was requested and then rejected on
evidence: a range that is two nights empty and two nights full would render
identically to one that is evenly on pace. That is precisely the disagreement
D36's per-night strip exists to expose. Labelling each row with its night count
turns five confusing rows into five self-explanatory ones without hiding
anything.

### Why the price delta, and why a percentage

Night mode exists because the average hides per-night variation, so the
operator's question is *"which nights does this average get wrong?"* With real
data the engine wants 2.110.000 – 2.550.000 across the range against a
2.310.000 average — accepting the average underprices 9/9 by 10,4% and
overprices 12/9 by 8,7%. That disagreement in **price** is currently invisible
anywhere in the product; only occupancy is plotted.

Absolute values do not work for scanning: seven 9-character strings differing
in the third digit. A signed percentage is 3–4 characters and makes the
outliers pop.

## Architecture

**Night mode needs almost no new backend.** `load_range` already builds
`NightlyPrice` objects carrying `.adjustments` (full `Contribution` tuples with
params), `.band_min/base/max`, `.current_net_rate`, `.rate_provenance`,
`.days_to_arrival`, `.occupancy`, `.expected_occupancy`. The router
(`rate.py:209-221`) loads all of it and serializes only 7 fields, dropping the
rest.

1. **Widen the `nightly` serialization; add no endpoint.** One
   `/api/rate/range` fetch powers both modes, so switching mode or night is
   instant with no loading state inside the drawer.

2. **Accepting one night is a range of length one.** `apply_to_range(start=X,
   end=X)` already works, and because the engine already rounded each night to
   the increment, `aggregate_range` over a single night is the identity — the
   accepted price is exactly that night's recommended rate. Preserves D35's
   "one code path rather than two".

3. **New data:**

| Field | Where | Why |
|---|---|---|
| `nights_covered` | each `Contribution` | the "n đêm" badge; `len(rows)` in the existing grouping loop |
| `decision` | each `NightlyPrice` | marks hand-tuned nights for the strip marker and clash warning |
| `clamped` | each `NightlyPrice` | derived from `net_rate_before_clamp` vs band bounds |
| `delta_vs_average_pct` | each `NightlyPrice` | the strip's signed percentage (D10: served, not computed in the browser) |
| `preserve_overrides` | `apply_to_range` + request body | skip hand-tuned nights, report `skipped_overridden` |

The pricing engine, `rate_book`, `features/`, and `aggregate_range`'s
reconciling-sum invariant are untouched.

## UI

```
┌─ 2BR Premium ──────────────────── [Đóng] ─┐
│ 6/9 → 12/9 · 7 đêm · Mùa thấp điểm 2      │
├───────────────────────────────────────────┤
│  Cả dãy ngày │ Từng ngày                  │  ← Radix Tabs, border-b
│──────────────┴────────────────────────────│
│ Giá NET đề xuất — Thứ Hai, 8/9            │
│ 2.140.000 ₫            Hiện tại 2.700.000 │
├───────────────────────────────────────────┤
│ Khoảng giá của bạn                        │
│ ├──MIN────●────────────────────MAX──┤     │  ← real clamp state
├───────────────────────────────────────────┤
│ Đang bán thế nào                          │
│  ▁    ▃    ▅    █    ▆    ▃    ▁          │
│ 6/9  7/9 │8/9│ 9/9 10/9 11/9 12/9         │
│ +2%  -6%  -7%  +10%  +1%  +6%  -9%        │
├───────────────────────────────────────────┤
│ Vì sao giá thay đổi                       │
├───────────────────────────────────────────┤
│ [ Chấp nhận 2.140.000 ₫ cho T2, 8/9 ]     │
└───────────────────────────────────────────┘
```

| Section | `Cả dãy ngày` | `Từng ngày` |
|---|---|---|
| Price | average + "TB 7 đêm" | that night's price + weekday/date |
| Band | `clamped={null}` (unchanged) | real clamp state |
| Pace | mean `pace_gap` + `PaceChart` + strip | that night's figures + strip only |
| Why | averaged rows + "n đêm" badges | that night's rows, no badges |
| Market | observations across range | same list filtered to that date |
| Footer | `…cho 7 đêm` + clash warning | `…cho T2, 8/9` |

Two independent statements of scope — the price heading and the button — so
switching mode without noticing cannot write the wrong range.

### Design-system constraints (from `apps/web/CLAUDE.md`)

- **Colour:** unpriced → `amber` (already shipped in `OccupancyStrip`);
  hand-tuned → `violet` (reserved in this codebase for "overridden" and nothing
  else); selected → **outline only**. Selection must never alter bar height or
  bar colour, or the chart's data encoding shifts meaning under the operator.
- **Sentence case**, never caps labels.
- **Karla, not Fraunces**, for the night date heading — functional data, not an
  identity moment.
- `tnum` on any numeric column.
- **No motion** on mode or night switch; the codebase has none and it would be
  decoration, not feedback.
- Toggle is hidden entirely when the range is 1 night, since the modes are
  identical.

## The breakdown fix

### Night badges

`nights_covered = len(rows)` in the existing grouping loop; default `1` on the
dataclass so per-night rows are correct untouched. The synthesized rounding row
(`rate_range.py:218-224`) must pass it explicitly.

**Badge renders only when `nights_covered < nights`.** Every structural row
(`rate_band`, `rounding`, `market`) covers all nights, so badges everywhere
would stop carrying information. Absence means "covers every night"; presence
means "this row does not describe the whole range" — exactly the pace/pickup
rows that caused the confusion. The alternative, hardcoding a list of
"structural" codes in the frontend, is rejected.

### The param bug — fixed in the message files, not in the averaging

ICU only requires arguments the *selected* branch references. A plural branch on
`nights_covered` can omit lead time entirely when a row covers several nights:

```
one   → "…with {days_to_arrival} day(s) to arrival… so this date is…"
other → "across {nights_covered} nights, {occupancy} sold on average against
         {expected_occupancy} expected…"
```

This kills `4,5 ngày` at the source rather than rounding it into a different
lie, and fixes "ngày này" in the same edit. These are **edits to existing keys,
not new ones**, so `test_every_emittable_key_has_a_translation` keeps passing
and there is no key explosion across 8 pace variants × 2 locales.

`_average_params` is **not** changed. Number presentation is fixed with ICU
skeletons in the message, consistent with D30 (the engine emits numbers; the
sentence is assembled at render).

**Critical:** `params` are persisted on adjustment rows, and `adjustments.ts:33`
catches an ICU failure by dropping the whole sentence. `nights_covered` must
therefore be **injected at serialization time in the router** for every row,
aggregate and nightly alike — never read from persisted params — or a
historical row silently loses its explanation.

## Testing

**Backend** (`make test`, 534 today)
- `nights_covered` equals group size; **the existing reconciling-sum invariant
  still passes** — the regression that matters most
- single-night aggregate is the identity
- `preserve_overrides=True` skips `STATUS_OVERRIDDEN` and reports the count;
  `False` preserves today's behaviour
- router serializes per-night adjustments, params, `nights_covered`, decision,
  clamp, delta

**Frontend** (`cd apps/web && npm test`)
- toggle hidden when `nights === 1`
- selecting a night rescopes price and breakdown; button names the date
- unpriced night withdraws accept
- clash warning appears, button count drops, opt-in flips it
- strip selection changes outline only — bar height and colour untouched

`make lint` covers ruff plus the ICU/message-consistency check.

## Documentation

**D40** — bulk accept preserves hand-tuned nights by default, amending D36's
"overwrites without prompting". D36 anticipated this ("Protecting a prior manual
override stays a small change"), so it is a recorded amendment, not a reversal.

`ASSUMPTIONS.md` needs nothing: no new unvalidated threshold is introduced.

## Known risk

`RangeDrawer.tsx` is 465 lines before gaining a mode dimension. Threading
`mode ?` conditionals through all five sections would push it past 600 and make
every section dual-purpose. Splitting into a shared shell plus two mode bodies
is part of this work, not a follow-up.
