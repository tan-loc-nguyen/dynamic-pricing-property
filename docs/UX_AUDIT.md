# UX Audit & Redesign

The product's intelligence is sound. Its **presentation assumes a revenue
manager**, and Luminous is an owner-operator. This audit covers what is wrong,
what is reusable, what data exists, and what had to change.

---

## Library Evaluation

The repository had **zero UI libraries** before this work — every table, drawer
and formatter was hand-built. That is the right instinct for product-specific
surfaces and the wrong one for solved infrastructure.

One hard constraint shapes every choice: **the app must stay statically
exportable** (`output: "export"`), because D32 packages it into a single
binary. Anything requiring a Node server at runtime is disqualified outright.

| Need | Options reviewed | Selected | Why | License |
|---|---|---|---|---|
| **Calendar / timeline** | FullCalendar Scheduler, Bryntum, DayPilot Pro/Lite, react-big-calendar, ilamy-calendar, **custom CSS Grid** | **Custom CSS Grid** | The need is a *price matrix* (room types × dates), not an event scheduler. Schedulers optimise for drag-drop event editing we do not want, and charge for the one view we need. 3 room-type rows × 60 date columns ≈ 180 cells — far below any virtualisation threshold. Sticky header + sticky first column is two CSS lines. | n/a (no dependency) |
| **Charts** | Recharts, ECharts, Nivo, visx, Chart.js, Tremor, Plotly | **Recharts 3.10** | Renders under static export (ECharts and Chart.js are client-only); React 19 ready; tree-shakeable; tooltips and responsive containers out of the box. Nivo is 500 kB+; visx is smallest but costs far more build time. **One** chart library, as required. | MIT |
| **Data grid** | AG Grid Community/Enterprise, TanStack Table, MUI Data Grid, **none** | **None (defer TanStack Table)** | Remaining tables are small and already work. Adding a grid now is dependency sprawl. TanStack Table (MIT, headless) is the documented choice *if* a real grid is ever needed. | n/a |
| **UI primitives** | Radix UI, Headless UI, shadcn/ui, custom | **Radix UI** | The existing drawer had **no focus trap, no escape handling, no restore-focus** — §33 requires all three. Radix is unstyled, so the Tailwind design system is untouched. | MIT |
| **Dates** | date-fns v4, Day.js, Luxon, hand-rolled | **date-fns 4.4** | Replaces hand-rolled `parseISODate` / `addDaysISO` / `todayISO`. Ships a `vi` locale, tree-shakes per function, and gives DST-safe arithmetic the manual version did not have. | MIT |

### Rejected for licensing — flagged explicitly

| Library | Problem |
|---|---|
| **FullCalendar Scheduler** | Resource timeline is **Premium**. The free tier is CC BY-NC-ND — *explicitly forbids commercial products*. Exactly the view we would have needed. |
| **Bryntum Scheduler** | Fully commercial, per-developer. |
| **DayPilot Pro** | Commercial; the Apache-2.0 "Lite" tier has no resource timeline. |
| **AG Grid Enterprise** | Row grouping — the feature that would justify it — is Enterprise, from **$999/developer**. Community (MIT) does not include it. |

Since this may become a commercial product, none of the above were adopted.
**Every dependency added is MIT.**

---

## 1. Problems in the previous interface

| Problem | Evidence |
|---|---|
| **Configuration sat beside daily work** | Rate Book, Dynamic Rules and History were four of six primary nav items. An owner prices rooms daily and edits thresholds ~never. |
| **KPI wall** | Six equally weighted cards, 116 px tall. One read "22 apartments" — a constant, re-read every session. |
| **The table was the product** | 14 columns × 45 rows, horizontally scrolling. Reading it required knowing what "pace gap −22pp" means. |
| **Insight arrived as data** | `70% kỳ vọng 92%` in a cell. The operator must do the subtraction *and* know the curve exists. |
| **Badge noise** | Up to 5 coloured chips per row plus 7 in the status banner. Everything shouted equally. |
| **Sidebar warnings never dismissed** | Two permanent blocks (Shadow Mode, unvalidated layer) consuming ~180 px of every screen forever. |
| **No sense of "where do I look?"** | 93 nights presented as a flat list. Nothing distinguished a date needing attention from one that did not. |
| **Availability was arithmetic** | `3/10` and `70%` as text. No visual sense of how full the month is. |
| **Market was a schema dump** | Confidence codes, price basis, tax inclusion — the collector's data model, shown to a host. |

---

## 2. Data actually available

| Need | Status |
|---|---|
| Recommended / current NET, band MIN–BASE–MAX, clamp flag | ✅ on every recommendation |
| Occupancy, expected occupancy, pace gap, days to arrival | ✅ |
| Adjustment breakdown with `label_key` + `params` | ✅ — already localisable (D30) |
| Season key, room category code, event name, market confidence | ✅ |
| Per-room-type units total/sold/available | ✅ |
| **Booking records with a date range** | ⚠️ exists in `bookings` (1,629 rows, `stay_date` + `nights`) but **was not exposed over the API** |
| **Which physical unit a booking occupies** | ❌ `physical_room_id` is **NULL on all 1,629 rows** |
| Market observations, competitors, confidence codes | ✅ |
| Booking-curve shape for a pace chart | ✅ derivable from `occupancy` + `expected_occupancy` per date |

### The one honest gap

§6 and §9 ask for **per-unit booking bars** — "Căn 101, Căn 102…". That data
does not exist: no booking is assigned to a unit, which is ASSUMPTIONS **U11**
and one of the two Blue Jay hard blockers surfacing in the UI.

Inventing assignments would have made a convincing demo out of a fabrication,
which §36 forbids. Instead:

- room-type rows carry pricing and aggregate availability (unchanged grain, per §6);
- expanding a room type shows the **real bookings** covering those nights as
  bars, stacked into lanes, labelled as bookings rather than as units;
- the empty state says plainly that unit-level assignment needs Blue Jay.

The timeline is real. The unit labels would not have been.

---

## 3. New information architecture

```
BEFORE (6 primary)                    AFTER (2 primary + settings)
  Duyệt giá        ← daily              Lịch giá          ← daily, default route
  Bảng giá mùa     ← config             Thị trường & Sự kiện
  Quy tắc động     ← config               ├── Tổng quan
  Thị trường       ← intelligence         ├── Đối thủ
  Sự kiện          ← intelligence         ├── Sự kiện
  Lịch sử          ← audit                └── Dữ liệu gốc
                                        ⚙ Cài đặt
                                          ├── Khung giá theo mùa
                                          ├── Chiến lược giá  (+ Nâng cao)
                                          ├── Kết nối & Dữ liệu
                                          └── Nhật ký hoạt động
```

Old routes redirect; no bookmark breaks.

---

## 4. Purely frontend vs. backend change

**Frontend only:** navigation, calendar, drawer redesign, rate-book matrix,
strategy summary, market overview, event inbox grouping, activity relocation,
attention scoring (derived from fields already present).

**Backend — one additive endpoint:**
`GET /api/bookings?start_date&end_date` → the booking rows that already exist.
No model change, no pricing change, no migration. It exposes data the seed has
always written and nothing could read.

---

## 5. Components reused vs. replaced

**Reused:** `useAdjustmentText` / `useBandLabel` (the D30 renderer — the drawer
and calendar both go through it), `useFormat`, `lib/api.ts`, `Chip`/`Button`/
`Card`, the whole message-catalogue architecture, `lib/search.ts`.

**Replaced:** `RecommendationTable` (→ `PricingCalendar`), `SummaryCards`
(→ `DecisionSummary`, 3 metrics), `StatusBanner` (→ `DataSourceStatus`, one
header dot), the hand-rolled drawer (→ Radix `Dialog` with real focus
management).

**Retained behind Settings:** rate-book editing, dynamic rules, decision
history, raw observations — same functionality, moved.
