# Blue Jay — contract, part VERIFIED as of 2026-08-27

> **FIRST LIVE WINDOW: 2026-08-27, 08:00–08:30 Vietnam time.** Everything under
> "Verified" below was observed against the real API. Where it contradicts the
> API document, the observation wins.
>
> **The base URL in the ENGLISH TRANSLATION IS WRONG.** It gives
> `api-test.bluejaypms.com`; the original Vietnamese says
> `api1.bluejaypms.com`. `api-test` exists and serves a DIFFERENT
> (booking-engine) API — `/properties`, `/roomtypes`, auth header `apikey`,
> parameter `property` — so every documented endpoint 404s there and every
> other call returns a blanket `Unauthorized` that carries no diagnosis. That
> cost most of the first window.

## VERIFIED against api1.bluejaypms.com

| Thing | Value | Note |
|---|---|---|
| Base URL | `https://api1.bluejaypms.com/api/v2` | NOT `api-test` |
| Auth header | `apikey`, raw value | the document only said "the Header" |
| Property parameter | `hotelId` | as documented |
| `roomtype-list` | `{status, message, data:[{id, name, code}]}` | field is `name`, NOT `roomtypeName` |
| `roomdetail-list` | `{status, message, data:[{id, roomName}]}` | **no roomtypeId in the row** |
| `roomdetail-list?roomtypeId=` | filters correctly | **this is the U11 unlock** |
| `source-list` | `[{id, sourceName, code, commiission, isActive, isDelete}]` | note the misspelling; `commiission` is ASSUMPTIONS U13 |
| `source-category` | `[{id, sourceName, isActive, isDelete}]` | |
| Success envelope | `status: "Success"` | capitalised |

Measured on tenant 1003: **15 room types, 67 rooms**, and the per-type counts
sum exactly to the unfiltered list. So units per room type is now real data,
not the seeded 10/8/4 guess.

### Two error grammars, and which one you get is the diagnosis

| Shape | Meaning | Example |
|---|---|---|
| `{errors:{code, title}}` | the AUTH GATE rejected you | missing or wrong `apikey` |
| `{errors:{status, message}}` | the APPLICATION rejected you | `hotelId is not found`; `Api chỉ được gọi trong các khung giờ cho phép`; `khoảng cách giữa ngày from và to không được quá 1 tháng` |

Both arrive with **HTTP 200**. Neither a status-code check nor a `status`-key
check sees them. `message` carries the only real diagnosis and it is in
Vietnamese — reducing it to "Unauthorized" sends the reader to check their key
when the actual problem was a date range.

Omitting `hotelId` entirely returns an **ASP.NET HTML error page**, not JSON.

### Undocumented constraints

- **`report-room-occupancy` rejects a range wider than one month.** Requests
  must be chunked. Nothing in the document says so.
- **A malformed `roomtypeId` is IGNORED, not rejected.**
  `roomdetail-list?roomtypeId=abc` returns EVERY room with `status: Success`.
  Attributing all 67 rooms to one type inflates `units_total`, understates
  occupancy, understates pace, and pushes the price DOWN for that category.
  `normalize.filter_looks_ignored()` exists for this.

### STILL BLOCKED — the reports

`reservation` and `report-room-occupancy` returned
*"Api chỉ được gọi trong các khung giờ cho phép"* throughout, while the filter
endpoints worked at the same instant, with the server's own `Date` header
agreeing with our clock to the second. `report-room-occupancy` passed the
window check once (it answered with the one-month error) and refused
afterwards, which points at a **per-window call allowance for the report
endpoints** rather than a clock problem — we had made roughly a dozen calls by
then.

**U16 therefore remains blocked.** No `bookDate`, no pickup, no fitted booking
curve. Ask Blue Jay: is there a call quota per window, and does it differ
between the filter and report endpoints?

---

# Original provisional notes, from the document only

**Every statement in this file is PROVISIONAL.** It is derived from Blue Jay's
API document (see `BLUEJAY_ENDPOINTS.md`), not from an
observed response. The document is internally inconsistent in several places,
and those places are named below rather than quietly resolved.

**Real API behaviour becomes authoritative the moment it is observed.** When a
capture disagrees with this file, this file is wrong.

---

## Testing windows — `Asia/Ho_Chi_Minh`

| Window | Status | Our reading |
|---|---|---|
| `08:00-08:30` | confirmed | `08:00:00–08:29:59` |
| `16:00-16:59` | confirmed | `16:00:00–16:59:59` |
| `24:00-24:59` | **UNCONFIRMED** | never treated as open |

The two confirmed strings use *different notations*: `16:00-16:59` names the
last included minute, `08:00-08:30` names the end instant. Reading both the
same way would make the morning window 31 minutes long, which nothing would
specify. Each is therefore read at its **narrower** interpretation — being a
minute short never causes a rejected call; being a minute long does.

`24:00-24:59` is not clock notation. `00:00-00:59` of the following day is the
likely reading, but no automated call is ever made on a guess.

`BlueJayClient` refuses to send outside a confirmed window, and refuses before
the request leaves the process. **Verify the windows on the first call.**

---

## Endpoints we depend on

| Endpoint | Why | Response schema |
|---|---|---|
| `roomtype-list` | room types + the ids the category map keys on | **undocumented** — no sample given |
| `roomdetail-list` | physical rooms → `units_total` (**unblocks U11**) | **undocumented** |
| `reservation` | bookings, occupancy AND derived rate, in one call | documented, with a sample |
| `report-room-occupancy` | cross-check only | documented, sample is inconsistent |
| `extraservice-sumary` | **not used, not captured** | — |

`extraservice-sumary` is deliberately never fetched. Pricing does not use it,
and the cheapest way to protect data is not to request it.

### Why `reservation` carries most of the load

`dateType=3` ("stay night") returns the reservations covering a date range.
Expanded to unit-nights that yields **bookings, on-the-books occupancy, and a
derived rate from one call** — which matters when the window is thirty minutes.

`report-room-occupancy` is a *report*, and reports are usually backward
looking. If it does not project forward, pace breaks entirely — pace needs
on-the-books occupancy for **future** dates. Deriving occupancy from
reservations removes that dependency.

---

## Documented inconsistencies — do not "fix" these locally, confirm them

1. **The occupancy sample fails its own arithmetic at the detail level.**
   `TotalRoom 3003 − RoomOccupied 73 − Blocked 0 = 2930`, but `RoomEmpty` says
   `2970`. The same figures repeat at grand-total, room-type and daily level,
   which is the signature of placeholder data.
   **However, the GRAND TOTAL is correct**: `30849 − 781 − 36 = 30032`, matching
   `GrandTotalRoomEmpty`. So `total − occupied − blocked == empty` *is* the
   vendor's intended invariant — that is positive evidence, not our inference.
   Only the detail rows are placeholder.
2. **The occupancy examples call `/reservation`,** not
   `/report-room-occupancy`. The endpoint definition and its own example
   disagree.
3. **The occupancy example's prose says 20/6–27/6 while the query says
   `from=2026-5&to=2026-6`.**
4. **`extraservice-sumary` and `report-room-occupancy` are both described as
   "retrieve the reservation list".**
5. **Two response envelopes coexist**: `reservation` returns
   `{meta, data:{type, attributes}}`; the others return
   `{status, message, data}`.

---

## Field mapping — VERIFIED against live responses

### `reservation` → `BookingDTO` (one row per **occupied unit-night**)

| Blue Jay | Our field | Note |
|---|---|---|
| `checkInTime` … `checkOutTime` | `stay_date` × N | checkout day is **not** an occupied night. `night` equalled the span on 22/22 rows |
| `bookDate` | `booked_at` | `YYYY-MM-DD HH:MM:SS` with real clock times — **U16 unblocked** |
| `roomType` (name) | `room_type_external_id` | resolved through `roomtypeId`; the vocabularies DO intersect |
| `roomPrice` ÷ nights × (1 − commission) | `net_rate` | **VERIFIED stay total, and GROSS.** See below |
| `source` | `channel` | commission looked up in `/source-list` |
| `status` | `status` | **VERIFIED mapping**, see below |
| `roomName` | `physical_room_external_id` | `"Unassigned"` is a placeholder → `None` |
| — | `nights` | **always 1**; Blue Jay's `night` is a stay length |
| — | `guests` | not present in the payload |

`bookingCode` is **not unique per row** — one booking spanned 22 rows across 6
room types — and `(bookingCode, roomName, checkInTime)` collided 7 times in 100
real rows via `"Unassigned"`. The row index is part of `external_id`.

### `roomPrice` is a GROSS, guest-facing amount

`balance == totalPrice − payment` on **122/122** rows, and a refunded booking
reads `total=0, payment=600,000, balance=−600,000`: `balance` is a guest ledger,
so `totalPrice` is what the **guest owes**, not the hotel's receipt. And
`commiission` lives on the SOURCE, which only has something to act on if the
amount is gross.

We price in NET, so `net = roomPrice / nights × (1 − commiission/100)`, with an
**unknown** commission reported rather than assumed zero — assuming zero
overstates achieved rate and biases recommendations up.

### Status vocabulary — VERIFIED

Derived by filtering on each documented integer and reading back the string:

| code | string | occupies? |
|---|---|---|
| 0 | `Đã xác nhận` | yes |
| 1 | `Đang giữ phòng` | **yes** — a held room cannot be sold to anyone else |
| 2 | `Không đến` | no |
| 3 | `Đã nhận phòng` | yes |
| 4 | `Đã trả phòng` | yes |
| 5 | `Đã huỷ` | no |
| -1 | no rows over 8 months | deleted rows appear to be withheld |

`đã đặt` and `giữ chỗ` were both invented and neither exists — code 1 returns
ONE string, so the firm-versus-tentative split encoded a distinction this API
does not make.

### Occupancy comes from `report-room-occupancy`, not from reservations

The two disagree on ~3% of room-nights (406/420) and the rule could not be
determined — some holds are counted, some are not, and two bookings made 96
seconds apart fall on opposite sides. Re-fetched back to back, unpaginated:
identical disagreement, so it is not drift.

The PMS's own answer wins for occupancy; reservations supply `bookDate`, pickup
and the derived rate. Blocked rooms leave the sellable denominator.

### Units come from ONE CALL PER ROOM TYPE

A `roomdetail-list` row is `{id, roomName}` with **no `roomtypeId`**, so an
unfiltered list cannot be grouped — an earlier version tried and produced ZERO
units for every category. `roomdetail-list?roomtypeId=` filters correctly:
15 types, 67 rooms, per-type counts summing exactly to the unfiltered list.
**That is the U11 unblock**, and it costs N+1 calls.

A non-integer or comma-separated `roomtypeId` is **silently ignored** and
returns the whole property, so a response matching the unfiltered count is
refused rather than counted.

---

## What is still unverified

- [ ] **Why report endpoints were refused in the 08:00 window.** Every
      client-side explanation eliminated. **Decisive test: call `reservation`
      FIRST in the next 08:00 window, before anything else.**
- [ ] **`roomPrice` NET vs gross** — inferred from two independent angles, but
      no OTA booking exists on this tenant to confirm directly.
- [ ] **The occupancy/reservation disagreement** — narrowed to a per-reservation
      attribute the payload does not expose.
- [ ] **`24:00-24:59`** — never trusted, never called.
- [ ] **`commiission` on a real tenant** — the field is a percentage (5/10/15
      observed) but every OTA source reads 0 here.
- [ ] **Luminous' own `hotelId`.** Everything above is tenant 1003, a demo
      property of 15 room types and 67 rooms. Luminous is 22 apartments across
      3 categories. **Nothing has been verified against their data.**
- [ ] **Is Blue Jay's Yield Management active on the Luminous tenant?** If it
      already moves rates, the two systems would fight.
- [ ] **Forward-looking rates.** No endpoint publishes one, so
      `current_net_rate` stays derived. Probably permanent.

Full endpoint reference, including every query parameter verified to work and a
table of what the vendor document gets wrong, is in
[`BLUEJAY_ENDPOINTS.md`](BLUEJAY_ENDPOINTS.md).

---

## Security

- Blue Jay is **read-only**. `BlueJayClient` exposes no verb but `GET`, so
  there is no write path to reach for. Whether Blue Jay operates a
  zero-data-retention policy is unknown, so a write is treated as potentially
  irreversible.
- **`captures/` and `snapshots/` are gitignored and this repo is public.** The
  test tenant is a third party's hotel; sanitisation removes personal data, not
  commercial confidentiality. Move snapshots to a demo machine out of band.
- Sanitisation is an **allowlist**. A denylist would ship whatever field Blue
  Jay adds next, and the payload carries `guestImagepaper` — a guest identity
  document.
- **Set `BLUEJAY_PSEUDONYM_SALT` before capturing anything real.** Booking codes
  are 6-digit numerics; with the public fixture salt a full rainbow table is
  built in about a second. `meta.json` records `salt_is_private` and the UI
  surfaces it.
- The API key is never logged, never written to a capture, and never rendered
  in a client `repr`.
