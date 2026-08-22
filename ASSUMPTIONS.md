# Business Assumptions

> **Every value in this document was invented by the engineering team.**
> None of it came from Luminous. Nothing here has been validated.
>
> This file is the **operator interview checklist**. Work down it with the
> Luminous revenue manager and replace guesses with facts.

**Status legend**

| Status | Meaning |
|---|---|
| `UNVALIDATED` | Placeholder chosen to make the demo legible. Needs operator confirmation. |
| `VALIDATED` | Confirmed by Luminous. Record who confirmed it and when. |
| `STRUCTURAL` | A modelling decision rather than a business rule — see `docs/DECISIONS.md`. |

**Where these live in code:** `apps/api/dynamic_pricing/pricing/defaults.py` is the single
source of truth. At runtime the active values come from the versioned
`PricingConfiguration` row and are editable from the **Pricing Rules** screen.
No pricing constant exists anywhere else in the codebase.

---

## A1 — Base price source

| | |
|---|---|
| **Current value** | Each room's `base_price` from the PMS (1,150,000–2,900,000 VND across the demo portfolio). A global override is available but unset. |
| **Status** | `UNVALIDATED` |
| **Why this value** | A per-room anchor is the only defensible starting point without knowing Luminous' rate structure. |
| **Ask the operator** | *"What is the 'normal' price for each room type, and where does that number live today — Blue Jay, a spreadsheet, or your head? Is there one base rate per room, or does it already vary by season/rate plan?"* |

## A2 — Minimum price (floor)

| | |
|---|---|
| **Current value** | Per room, 700,000–2,150,000 VND (roughly 60–90% of base). |
| **Status** | `UNVALIDATED` |
| **Why this value** | Every operator has a "never below this" number; the demo needs one to show the floor binding. |
| **Ask the operator** | *"Is there a price you would never go below for each room, even on an empty night? Does it come from the owner, from costs, or from brand positioning? Does it change by season?"* |

## A3 — Maximum price (ceiling)

| | |
|---|---|
| **Current value** | Per room, 2,600,000–6,500,000 VND. Two demo rooms carry a deliberately tight cap to demonstrate the constraint. |
| **Status** | `UNVALIDATED` |
| **Why this value** | Caps usually come from OTA rate-parity rules or owner instructions. |
| **Ask the operator** | *"Is there an upper limit you will not cross? Is it driven by OTA parity, by guest expectations, or by an owner agreement?"* |

## A4 — Rounding increment

| | |
|---|---|
| **Current value** | 10,000 VND, nearest. |
| **Status** | `UNVALIDATED` |
| **Why this value** | VND prices are conventionally quoted in round tens of thousands. |
| **Ask the operator** | *"What do your prices normally end in? Do you round to 10k, 50k, or 100k? Do you deliberately use charm pricing (e.g. 1,490,000 rather than 1,500,000)?"* |

## A5 — Compounding guardrail

| | |
|---|---|
| **Current value** | Total multiplier clamped to **0.70 – 1.60** of base price. |
| **Status** | `UNVALIDATED` |
| **Why this value** | Seven multiplicative factors can compound absurdly (e.g. 1.15 × 1.15 × 1.10 × 1.20 ≈ 1.75). A hard clamp is the crudest safe answer. |
| **Ask the operator** | *"What is the most you would ever move a price away from normal in a single day — up and down? Would you rather the system never move more than ±20%?"* |

## A6 — Minimum change worth surfacing

| | |
|---|---|
| **Current value** | 0.5% (config key exists; currently informational only). |
| **Status** | `UNVALIDATED` |
| **Ask the operator** | *"How small a price change is still worth your time to review? Should we hide anything under 2%?"* |

## A7 — Day-of-week multipliers

| | |
|---|---|
| **Current value** | Mon 0.95 · Tue 0.95 · Wed 0.96 · Thu 1.00 · **Fri 1.10** · **Sat 1.15** · Sun 1.00 |
| **Status** | `UNVALIDATED` |
| **Why this value** | Generic short-term-rental weekend shape. Purely illustrative. |
| **Ask the operator** | *"How much more do you charge on a Friday or Saturday than a Tuesday, as a percentage? Is Sunday a weekend or a weekday for you? Does this differ between the city apartments and Da Nang?"* |

## A8 — Occupancy bands and multipliers

| | |
|---|---|
| **Current value** | <30% → 0.92 · <50% → 0.97 · <70% → 1.00 · <85% → 1.08 · ≥85% → 1.15 |
| **Status** | `UNVALIDATED` |
| **Why this value** | Standard "raise as you fill" revenue-management shape. Thresholds are round numbers, not measured ones. |
| **Ask the operator** | *"At what occupancy do you start pushing prices up? Is there a level where you stop discounting entirely? Do you think in occupancy percentage at all, or in 'units left'?"* |
| **Note** | Occupancy is computed per **room type**, not per property — see `docs/DECISIONS.md` D2. Confirm this matches how Luminous thinks about availability. |

## A9 — Lead-time bands and multipliers

| | |
|---|---|
| **Current value** | 0–3 days → 0.95 · 4–7 → 0.98 · 8–30 → 1.00 · 31–60 → 1.02 · 60+ → 1.00 |
| **Status** | `UNVALIDATED` |
| **Why this value** | Mild last-minute discounting with a small early-booking premium. |
| **Ask the operator** | *"As a date gets closer and is still unsold, do you drop the price, hold it, or raise it? How many days out does your behaviour change? Do you ever raise last-minute prices because you know late bookers pay more?"* |

## A10 — Urgency (distressed-inventory) discount

| | |
|---|---|
| **Current value** | Within **7 days** and occupancy below **50%** → extra **×0.92**. |
| **Status** | `UNVALIDATED` |
| **Why this value** | Lead time alone can't express "close AND empty", which is the situation operators actually react to. Modelled explicitly rather than hidden inside the lead-time factor. |
| **Ask the operator** | *"When a date is a few days away and still half empty, what do you actually do? How big a discount, and how late do you leave it?"* |

## A11 — Booking-pace bands

| | |
|---|---|
| **Current value** | index <0.4 → 0.94 · <0.8 → 0.98 · <1.3 → 1.00 · <2.0 → 1.05 · ≥2.0 → 1.10 |
| **Status** | `UNVALIDATED` |
| **Ask the operator** | *"Do you track how fast a date is filling compared to normal? If a date is selling unusually fast, do you raise the price — and by how much?"* |

## A12 — Booking-pace observation window

| | |
|---|---|
| **Current value** | 7 days. |
| **Status** | `UNVALIDATED` |
| **Ask the operator** | *"Over what period do you judge whether bookings are coming in well — the last week, the last two weeks?"* |

## A13 — Expected pickup ("on pace")

| | |
|---|---|
| **Current value** | 1.0 unit per week per room type is considered exactly on pace. |
| **Status** | `UNVALIDATED` — **weakest assumption in the model.** |
| **Why this value** | A flat constant is a poor proxy: real expected pickup varies by room, season and how far out the date is. Used only because no historical baseline exists yet. |
| **Ask the operator** | *"For a given apartment, how many bookings a week would you consider normal 30 days out? Does that change close to the date?"* |
| **Recommended fix** | Replace with a pickup curve derived from Luminous' own booking history once Blue Jay data is available. |

## A14 — Seasonality (month multipliers)

| | |
|---|---|
| **Current value** | Jan 1.10 · Feb 1.08 · Mar 1.00 · Apr 1.02 · May 0.98 · Jun 0.96 · Jul 1.00 · Aug 1.00 · Sep 0.96 · Oct 0.98 · Nov 1.02 · **Dec 1.12** |
| **Status** | `UNVALIDATED` |
| **Why this value** | Generic Vietnam peak/shoulder/low shape, applied uniformly to all properties. |
| **Ask the operator** | *"Which months are your strongest and weakest? Is the pattern the same in Ho Chi Minh City and Da Nang?"* (It almost certainly is not — Da Nang is far more seasonal.) |
| **Known weakness** | Seasonality is currently global, not per-property. Tet is not modelled at all and moves every year. |

## A15 — Event multiplier

| | |
|---|---|
| **Current value** | ×1.20 flat for any date flagged as an event. |
| **Status** | `UNVALIDATED` |
| **Why this value** | A single uplift keeps the demo simple. Real events differ enormously in impact. |
| **Ask the operator** | *"Which events actually move your prices? How much do you add for a big one versus a minor one? Where do you find out about them — and should the system track a calendar?"* |
| **Known weakness** | One multiplier for all events. Likely needs per-event magnitude, plus shoulder-day effects. |

## A16 — Market sensitivity

| | |
|---|---|
| **Current value** | 0.50 — the price moves half as much as the market does. |
| **Status** | `UNVALIDATED` |
| **Why this value** | Deliberately damped: competitor data in this MVP is synthetic and thin, so tracking it one-for-one would be reckless. |
| **Ask the operator** | *"When competitors raise prices, do you follow? Fully, or partly? Which properties do you actually watch?"* |

## A17 — Market factor clamp

| | |
|---|---|
| **Current value** | 0.90 – 1.15. |
| **Status** | `UNVALIDATED` |
| **Ask the operator** | *"How far would you let a competitor's pricing move your own price?"* |

## A18 — Minimum market observations

| | |
|---|---|
| **Current value** | 2. Below this the market factor is neutral and the UI says so. |
| **Status** | `UNVALIDATED` |
| **Ask the operator** | *"How many competitor prices would you want to see before trusting a market signal?"* |

## A19 — Market observation freshness

| | |
|---|---|
| **Current value** | Observations older than 14 days are ignored. |
| **Status** | `UNVALIDATED` |
| **Ask the operator** | *"How quickly does competitor pricing go stale in your market?"* |

## A20 — Weekend definition

| | |
|---|---|
| **Current value** | Friday, Saturday and Sunday are flagged as weekend. |
| **Status** | `UNVALIDATED` |
| **Why this value** | Short-stay demand in Vietnam typically lifts from Friday night. |
| **Ask the operator** | *"Does your weekend start Friday or Saturday? Is Sunday night priced like a weekend or a weekday?"* |
| **Note** | The flag is informational; actual pricing uses the per-day multipliers in A7. |

## A21 — Market baseline for the price index

| | |
|---|---|
| **Current value** | `market_price_index = median competitor price for the stay date ÷ median competitor price for that room across the whole horizon`. |
| **Status** | `STRUCTURAL` + `UNVALIDATED` |
| **Why this value** | Comparing the market to *itself* keeps the signal independent of our own pricing. Dividing by our base price instead would make the factor partly circular. |
| **Ask the operator** | *"When you say the market is 'expensive' for a date, expensive compared to what — other dates, or your own price?"* |

## A22 — Competitor set

| | |
|---|---|
| **Current value** | Three invented competitor names per property. |
| **Status** | `UNVALIDATED` |
| **Ask the operator** | *"Which specific properties do you consider your real competitors, per building? How do you pick them — location, size, star rating, or guest overlap?"* |

---

## Structural assumptions (modelling, not business rules)

These are engineering choices that shape what the model can express. They are
documented in full in `docs/DECISIONS.md` but need operator sanity-checking.

| ID | Assumption | Why it matters |
|---|---|---|
| S1 | Pricing is per **room type per night** | If Luminous prices per physical unit or per length-of-stay, the model needs reshaping. |
| S2 | Factors combine **multiplicatively** | Additive or rule-priority logic would behave differently at the extremes. |
| S3 | Recommendation is anchored to **base price**, not current price | Means the system corrects a mispriced date in one step rather than drifting. Confirm this is wanted. |
| S4 | One price per night, no **rate plans / LOS / channel** differentiation | Real OTA pricing usually varies by channel and length of stay. |
| S5 | No **cost, tax or commission** modelling | The engine optimises headline rate, not margin. |
| S6 | Accepting a price updates the local record only — **nothing is pushed to any OTA** | Deliberate: autonomous OTA updates are an explicit non-goal. |

---

## Highest-priority questions

If there is time for only ten minutes with the operator, ask these:

1. **A1** — Where does today's "normal" price for each apartment actually come from?
2. **A2 / A3** — What are the real floor and ceiling per apartment, and who sets them?
3. **A7** — How much more is a Saturday worth than a Tuesday?
4. **A8** — At what occupancy do you start pushing price up?
5. **A9 / A10** — What do you do with a date that is close and still empty?
6. **A13** — What does a "normal" booking pace look like for one apartment?
7. **A15** — Which events actually move your prices, and by how much?
8. **A22** — Who are your real competitors, building by building?
9. **A14** — How different is Da Nang's season from Ho Chi Minh City's?
10. **S3** — When a date is priced wrong today, do you want a single correction or a gradual move?
