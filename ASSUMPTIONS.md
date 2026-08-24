# Business Assumptions

This file has two halves, and the split matters more than anything else in it.

**Part 1 — VALIDATED CLIENT INPUT.** Supplied by Luminous and confirmed by real
operation. The system treats this as fact and anchors on it.

**Part 2 — UNVALIDATED.** Chosen by the engineering team so the dynamic layer
could be built and demonstrated. None of it came from Luminous. Every item is
an interview question waiting to be asked.

> Source for Part 1: *Luminous Luxury Apartments — Business Assumptions*
> (client document, held in `private/`, not committed).

---

# Part 1 — VALIDATED CLIENT INPUT

## V1 — Portfolio size and room categories

| | |
|---|---|
| **Value** | 22 apartments across 3 room categories: **2BR Regular**, **2BR Premium**, **3BR** |
| **Status** | `CLIENT_VALIDATED` |
| **Where it lives** | `providers/pms/mock.py` (demo portfolio), `RoomType` / `PhysicalRoom` tables |
| **Still open** | The *split* of 22 units across the three categories is **not** stated in the client document — see U11. |

## V2 — Rates are NET, not OTA prices

| | |
|---|---|
| **Value** | The MIN/BASE/MAX table is **NET revenue to Luminous**, not the guest-facing OTA price |
| **Status** | `CLIENT_VALIDATED` — stated explicitly in the client document |
| **Consequence** | Every rate field in the system is named `*_net_rate`. A NET rate is never compared directly against an unnormalised competitor OTA price, and no commission/markup transformation is applied because none has been supplied (see U13). |

## V3 — Seasonal calendar

| Season | Months | Character (per the client) |
|---|---|---|
| Low Season 1 | May–Jun | Mostly business travel, little tourism |
| High Season 1 | Jul–Aug | Summer tourism — international and family |
| Low Season 2 | Sep–Oct | Predominantly business travel |
| **High Season 2** | **Nov–Dec–Jan** | Holiday season |
| Medium Season | Feb–Apr | — |

**Status:** `CLIENT_VALIDATED`.
**Note:** High Season 2 wraps the year end. **January belongs to the Nov–Jan
high season**, not to the start of the year. This is the single most
error-prone part of the table and is pinned by a dedicated test.

## V4 — Seasonal MIN / BASE / MAX NET rate table

All figures VND, NET. `CLIENT_VALIDATED`.

| Season | Category | MIN | BASE | MAX |
|---|---|---:|---:|---:|
| Low 1 (May–Jun) | 2BR Regular | 1,800,000 | 2,000,000 | 2,200,000 |
| Low 1 | 2BR Premium | 2,000,000 | 2,300,000 | 2,500,000 |
| Low 1 | 3BR | 2,700,000 | 2,800,000 | 3,200,000 |
| High 1 (Jul–Aug) | 2BR Regular | 2,100,000 | 2,300,000 | 2,600,000 |
| High 1 | 2BR Premium | 2,400,000 | 2,700,000 | 2,900,000 |
| High 1 | 3BR | 2,900,000 | 3,300,000 | 3,500,000 |
| Low 2 (Sep–Oct) | 2BR Regular | 1,800,000 | 2,100,000 | 2,300,000 |
| Low 2 | 2BR Premium | 2,000,000 | 2,400,000 | 2,700,000 |
| Low 2 | 3BR | 2,600,000 | 2,800,000 | 3,000,000 |
| High 2 (Nov–Jan) | 2BR Regular | 2,100,000 | 2,500,000 | 3,200,000 |
| High 2 | 2BR Premium | 2,500,000 | 3,000,000 | 3,500,000 |
| High 2 | 3BR | 3,200,000 | 3,800,000 | 4,300,000 |
| Medium (Feb–Apr) | 2BR Regular | 2,000,000 | 2,300,000 | 2,500,000 |
| Medium | 2BR Premium | 2,200,000 | 2,500,000 | 2,700,000 |
| Medium | 3BR | 2,700,000 | 3,200,000 | 3,500,000 |

**Where it lives:** `pricing/rate_book.py` (canonical) → `seasonal_rate_bands`
table → editable in the **Rate Book** screen.

## V5 — The base-rate layer does not need modelling

The client's own conclusion, translated:

> "The base-rate layer does not need modelling and does not need to be inferred
> from history. It already exists and has been validated by real operation.
> Load the rate table as a lookup table. What is needed is the dynamic layer on
> top: booking pace, lead time, events, competitor response."

**Consequence:** season *selects* a band; it never *multiplies* one. There is
no seasonality factor anywhere in PricingEngineV2 — that would double-count a
seasonality the table already encodes.

## V6 — The current rate table is static, and that is the gap

A whole 2–3 month season carries only three price levels. Closing that gap —
varying rate by pace, lead time, events and market **within** the validated
band — is the product's entire purpose.

---

# Part 2 — UNVALIDATED / REQUIRES VALIDATION

> Everything below was invented by the engineering team.
> All of it is editable from **Dynamic Rules** without a code change.

## U1 — Booking curve (expected occupancy by lead time)

| | |
|---|---|
| **Current value** | Demo curve: ~82% expected on-the-books occupancy at D-0, ~40% at D-30, ~11% at D-90, scaled per season and category |
| **Status** | `UNVALIDATED` — **the weakest assumption in the system** |
| **Why** | Pace position is the primary demand signal, and it is only as good as the curve behind it. Luminous' real curves are not available: the client document states Blue Jay has no data retention, though history "can be extracted, given time". |
| **Ask the operator** | *"For a 2BR Regular 30 days out, how full would you normally expect to be? Does that differ between Da Nang-style leisure months and business-travel months?"* |
| **Fix** | Replace `DemoBookingCurveProvider` with `HistoricalBookingCurveProvider` once pickup history exists. The interface already exists. |

## U2 — Pace-position thresholds and adjustments

| | |
|---|---|
| **Current value** | gap < −20pp → −8% · < −8pp → −4% · ±8pp → 0% · > +8pp → +4% · > +20pp → +8% |
| **Status** | `UNVALIDATED` |
| **Ask the operator** | *"If a date is 20 points behind where it should be by now, how much would you cut? And if it were 20 points ahead, how much would you add?"* |

## U3 — Recent-pickup thresholds and adjustments

| | |
|---|---|
| **Current value** | delta < −1.0 → −3% · < −0.25 → −1.5% · ≤ +0.5 → 0% · ≤ +2 → +2% · > +2 → +4% (7-day window, 1.0 unit/week expected) |
| **Status** | `UNVALIDATED` |
| **Why deliberately small** | Pace and pickup must not double-count the same demand: pace is the level, pickup is the acceleration. |
| **Ask the operator** | *"Over what window do you judge whether bookings are coming in well? What counts as a normal week's pickup for one apartment?"* |

## U4 — Event impact sizes

| | |
|---|---|
| **Current value** | low +3% · medium +8% · high +15% |
| **Status** | `UNVALIDATED` |
| **Ask the operator** | *"Which events actually move your rates, and by how much? Does a big event lift the days either side of it too?"* |

## U5 — Market sensitivity and cap

| | |
|---|---|
| **Current value** | sensitivity 0.50, capped at ±5%, minimum 2 qualified observations, observations stale after 14 days |
| **Status** | `UNVALIDATED` |
| **Ask the operator** | *"When comparable properties move their rates, do you follow? Fully or partly? How quickly does a competitor price go stale?"* |

## U6 — Market confidence gate

| | |
|---|---|
| **Current value** | Only `MEDIUM`+ observations may move a rate. Confidence is derived from metadata completeness: a NET-basis price with category, LOS, tax/fee and promotion status scores HIGH; a generic web price scores LOW. |
| **Status** | `UNVALIDATED` (the policy, not the principle) |
| **Ask the operator** | *"What would you need to know about a competitor's price before you'd let it change yours?"* |

## U7 — Day-of-week behaviour

| | |
|---|---|
| **Current value** | **DISABLED.** All weekday adjustments are 0%. |
| **Status** | `UNVALIDATED` — deliberately off |
| **Why** | The client's rate table shows no weekday structure at all. Inventing one would be pure guesswork on top of validated data. |
| **Ask the operator** | *"Do you price Fridays and Saturdays differently from midweek? By how much? Is that already baked into the seasonal table?"* |

## U8 — Total dynamic adjustment bound

| | |
|---|---|
| **Current value** | ±15% of the BASE rate, applied before the band clamp |
| **Status** | `UNVALIDATED` |
| **Ask the operator** | *"What is the most you would move a rate away from your normal price in one go?"* |

## U9 — Are the seasonal MIN/MAX hard limits?

| | |
|---|---|
| **Current behaviour** | Treated as **hard**. The engine never recommends outside the band; an operator override may go outside, and is recorded as such. |
| **Status** | `UNVALIDATED` — an important open question |
| **Ask the operator** | *"On New Year's Eve or during a major event, would you ever go above your seasonal MAX? Is MIN ever breachable to fill a date?"* |

## U10 — Rounding

| | |
|---|---|
| **Current value** | Nearest 10,000 VND |
| **Status** | `UNVALIDATED` |
| **Ask the operator** | *"What do your rates normally end in — 10k, 50k, 100k? Do you use charm pricing?"* |

## U11 — Unit split across room categories

| | |
|---|---|
| **Current value** | 10 × 2BR Regular, 8 × 2BR Premium, 4 × 3BR = 22 |
| **Status** | `UNVALIDATED` — total is validated, split is a guess |
| **Why it matters** | Occupancy is computed per room category, so a wrong split distorts every pace signal. |
| **Ask the operator** | *"How many of the 22 apartments are in each category?"* |

## U12 — Comp set

| | |
|---|---|
| **Current value** | Three invented comparable properties |
| **Status** | `UNVALIDATED` |
| **Ask the operator** | *"Which specific properties do guests choose between you and? What makes them comparable — location, size, service level?"* |

## U13 — Channel / commission transformation (NET → OTA sell)

| | |
|---|---|
| **Current value** | **Not implemented.** No commission, markup or promotion rules exist. |
| **Status** | `UNVALIDATED` — deliberately not invented |
| **Why** | Turning a NET rate into an OTA sell price needs real per-channel commission and promotion rules. Guessing them would produce plausible, wrong guest-facing prices. |
| **Ask the operator** | *"What commission does each OTA take? Do you mark up differently per channel? Who sets the guest-facing price today — you or the channel?"* |

## U14 — "Current NET rate" definition in Blue Jay

| | |
|---|---|
| **Current value** | Demo data uses the seasonal BASE as the current rate. |
| **Status** | `UNVALIDATED` |
| **Ask the operator / Blue Jay** | *"Which Blue Jay field is the rate Luminous actually receives, net of commission and taxes? Is there more than one rate plan per date?"* |

## U15 — Historical booking data availability

| | |
|---|---|
| **What the client says** | Blue Jay has **no data retention**, but history and NET booking revenue **can be extracted, given time**. The contact appeared hesitant about this. |
| **Status** | `UNVALIDATED` / blocked |
| **Why it matters** | This is the single biggest unlock. Without it there is no real booking curve (U1) and no outcome evaluation. |
| **Ask** | *"How far back can reservation history be exported, and in what format? Does each booking carry a creation timestamp?"* |

## U16 — Booking-created timestamp availability

| | |
|---|---|
| **Status** | `UNVALIDATED` / blocked on Blue Jay |
| **Why it matters** | Hard requirement for the recent-pickup signal AND for fitting historical booking curves. Without it, pickup goes permanently neutral. |

---

## Structural decisions (engineering, not business)

Documented fully in `docs/DECISIONS.md`, but worth an operator sanity-check:

| ID | Decision | Why it matters |
|---|---|---|
| S1 | Pricing grain is **RoomType × StayDate** | Individual apartments do not get their own rate. Unit-level overrides are possible later but not enabled. |
| S2 | Dynamic layer is **additive percentages**, not stacked multipliers | Bounded and hand-checkable. |
| S3 | Occupancy and lead time are **not** independent factors | Both are folded into pace position, so one demand condition is not paid for three times. |
| S4 | The engine anchors on **BASE**, not on the current rate | A mispriced date is corrected in one step rather than drifting. |
| S5 | **Shadow Mode only** — nothing is pushed to Blue Jay or any OTA | Blue Jay stays the system of record and the execution layer. |
| S6 | No cost, tax or margin modelling | The engine optimises NET rate, not profit. |

---

## The ten questions worth asking first

1. **U11** — How are the 22 apartments split across the three categories?
2. **U1** — How full would you expect a 2BR Regular to be 30 days out?
3. **U2** — A date 20 points behind pace: how much would you cut?
4. **U15/U16** — Can we export booking history, and does it include creation timestamps?
5. **U9** — Would you ever price above the seasonal MAX for a major event?
6. **U4** — Which events actually move your rates, and by how much?
7. **U12** — Who are your real comparable properties?
8. **U7** — Do you price weekends differently, or is that already in the table?
9. **U14** — Which Blue Jay field is the true NET rate?
10. **U13** — What commission does each OTA take?
