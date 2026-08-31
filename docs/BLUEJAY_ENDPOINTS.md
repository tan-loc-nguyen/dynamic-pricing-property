# Blue Jay BE API — verified endpoint reference

**AUTHORITATIVE for endpoints.** Everything marked VERIFIED was observed against
the live API on **2026-08-27, 08:00–08:20 Vietnam time**, tenant `hotelId=1003`.
Where this contradicts the vendor document, the observation wins.

Anything marked UNVERIFIED comes from the vendor document only and has never
returned a response to us.

> Derived from Blue Jay's own `Tài liệu hướng dẫn sử dụng BLUE JAY BE API -
> Báo cáo.docx` (Vietnamese), which stays out of this repository — but every
> VERIFIED line below is our own observation against the live API, not a copy
> of it. Findings only: no credential appears here, and the tenant described is
> Blue Jay's **demo** property, not a customer's.

---

## 1. Connection

| | Value | Status |
|---|---|---|
| Base URL | `https://api1.bluejaypms.com/api/v2` | **VERIFIED** |
| Auth | header `apikey: <key>`, raw value | **VERIFIED** |
| Property selector | query `hotelId=<int>` | **VERIFIED** |
| Method | `GET` only. We never POST. | policy |

> ### The English translation had the wrong base URL
> It gave `api-test.bluejaypms.com`. That host **exists** and serves a
> different, booking-engine API (`/properties`, `/roomtypes`, header `apikey`,
> parameter `property`), so every documented endpoint 404s there and everything
> else returns a blanket `Unauthorized` identical for a missing key, an unknown
> property and a nonexistent route. It cost most of the first window.

**How the auth header was found:** of eight candidate headers, `apikey` was the
only one returning **404** instead of `200 Unauthorized`. A 404 means the
request got *past* the auth gate into routing.

---

## 2. Calling windows

Document: `8-8h30`, `16-16h59`, `24-24h59` Vietnam time. The third is not clock
notation and is UNCONFIRMED.

**VERIFIED and important:** the window applies to the **report** endpoints only.

| Endpoint group | 08:12 | 08:20 | 08:28 | **08:52** |
|---|---|---|---|---|
| Filters (`roomtype-list`, `roomdetail-list`, `source-*`) | OK | OK | OK | **OK** |
| Reports (`reservation`, `report-room-occupancy`, `extraservice-sumary`) | passed the window check | refused | refused | refused |

**VERIFIED: the filter endpoints are not window-gated at all.** They answered
normally at 08:52, twenty-two minutes after the documented window closed. Only
the report endpoints are restricted — so filter data can be refreshed any time,
and a window should be spent entirely on `reservation`.

### The precise evidence — a time window does NOT explain it

| VN time | `reservation` | `report-room-occupancy` | filters |
|---|---|---|---|
| 08:13:41 | **window error** | **date-range error** (so it PASSED the window check) | OK |
| 08:16:14 | — | — | OK |
| 08:19:48–51 | window error (×3 dateTypes) | window error | — |
| 08:20:27 | — | — | OK |
| 08:28:48 | window error | — | — |
| 08:52:35 | — | — | **OK** (22 min after the window closed) |

Two facts kill the "the report window is shorter than documented" theory:

1. **At 08:13:41, in the same second, occupancy passed the window check and
   reservation did not.** A shared time window cannot produce two different
   verdicts at one instant.
2. **We never saw `reservation` succeed at all.** The first api1 call to it was
   at 08:13:41 and it was already refused — we spent 08:01–08:12 on the wrong
   host, so we have NO evidence it ever worked earlier in the window.

What we can say: occupancy changed behaviour between 08:13:41 and 08:19:48;
reservation was refused on every attempt; filters were never restricted.

Candidate explanations, none confirmed: a per-endpoint call allowance, a
permission on the key that covers occupancy but not reservation, or a generic
message reused for several different refusals. **Ask Blue Jay rather than
guess** — an earlier version of this document asserted a ~15-minute window,
which the timestamps do not support.

## 3. Response envelopes

### Success — VERIFIED
```json
{"status": "Success", "message": "Get list roomtypes successful", "data": [ ... ]}
```
`status` is **capitalised**. `data` is a **bare array** for the filter endpoints.

### Errors — VERIFIED. Two grammars, and which one you get is the diagnosis.

| Shape | Layer | Seen for |
|---|---|---|
| `{"errors":{"code","title"}}` | auth gate | **missing** `apikey` header |
| `{"errors":{"status","message"}}` | application | unknown `hotelId`, closed window, range too wide |
| **HTTP 500, HTML** (ASP.NET page) | unhandled | **wrong** `apikey`; `hotelId` empty or non-numeric |

**Both JSON error shapes arrive with HTTP 200.** Neither a status-code check nor
a `status`-key check detects them.

`message` is in Vietnamese and is the only real diagnosis:
- `"hotelId is not found"`
- `"Api chỉ được gọi trong các khung giờ cho phép"` — outside the allowed windows
- `"khoảng cách giữa ngày from và to không được quá 1 tháng"` — from/to must be ≤ 1 month

Reducing these to "Unauthorized" sends the reader to check their API key when
the real complaint was a date range.

---

## 4. Filter endpoints — VERIFIED

### `GET /roomtype-list?hotelId=`
15 rows on tenant 1003.
```json
{"id": 6153, "name": "Căn hộ 02 phòng ngủ", "code": "TPL"}
```
| Field | Type | Note |
|---|---|---|
| `id` | int | the roomtypeId used elsewhere |
| `name` | str | **the document calls this `roomtypeName`. It does not exist.** |
| `code` | str | short code |

There is **no unit count** on a room type. See below for how to get it.

### `GET /roomdetail-list?hotelId=[&roomtypeId=]`
67 rows unfiltered on tenant 1003.
```json
{"id": 1, "roomName": "R - 401"}
```
**A row carries NO `roomtypeId`.** Rooms cannot be grouped by type from one
call — you must call once per room type. Verified: the 15 per-type counts sum
exactly to the 67 unfiltered rows. **This is how units-per-room-type is
obtained** (ASSUMPTIONS U11), at a cost of one call per type.

> #### DANGEROUS — a filter that is ignored rather than rejected
> | `roomtypeId` | Result |
> |---|---|
> | `6153` | 4 rows — correct |
> | `999999` (unknown, numeric) | 0 rows — correct |
> | `-1` (negative, numeric) | 0 rows — correct |
> | `abc` (non-numeric) | **all 67 rows**, `status: Success` |
> | `6153,6154` (the documented comma syntax) | **all 67 rows**, `status: Success` |
> | `` (empty) | all 67 rows — reasonable, no filter supplied |
>
> **The rule: parseable as an integer → the filter applies (possibly to zero
> rows). Not parseable → the filter is silently ignored and you get everything.**
>
> Attributing every room to one type inflates `units_total`, which understates
> occupancy, understates pace, and pushes that category's price **DOWN** —
> silently. `normalize.filter_looks_ignored()` guards this.

### `GET /source-list?hotelId=[&categorySource=]`
30 rows unfiltered; `categorySource=2` → 14; `=0` → 7; `=99` → 0 rows, still Success.
```json
{"id": 28, "sourceName": "Agoda", "code": "3", "commiission": 0,
 "isActive": true, "isDelete": false}
```
**`commiission` (sic, misspelled) is a per-source commission PERCENTAGE** — the
field ASSUMPTIONS U13 needs for a NET↔OTA transformation.

Observed values across 30 sources: `0` (27 sources, including Agoda,
Booking.com, Airbnb and Expedia), `5` (VƯỢNG GPT), `10` (Viettravel), `15`
(Saigon Tours). **5/10/15 can only be percentages** — an absolute VND amount of
5 would be meaningless.

Caveat worth stating: every *OTA* source reads `0`, which for a demo tenant more
likely means "not configured" than "no commission". So the FIELD is understood;
the VALUES for this tenant are not trustworthy.

### `GET /source-category?hotelId=`
7 rows: `{"id": 0, "sourceName": "Direct", "isActive": true, "isDelete": false}`.
Ids seen: 0 Direct, 1 Travel Agency (TA), 2 OTA, …

---

## 5. Report endpoints — VERIFIED in the 16:00 window

All three answered normally at 16:03–16:20. The morning refusals remain
unexplained; Blue Jay states there is no rate limit inside a slot.

### `GET /reservation` — VERIFIED

Envelope `{meta:{limit,page,total}, data:{type,attributes:{reservations:[…]}}}`.

**`meta.total` IS CAPPED AT `limit`, NOT the row count.** With `limit=100` it
reported `total: 100` and page 2 returned 100 more rows. Treating it as the
count silently truncates — which understates occupancy and pushes prices down.
**Page until a page returns fewer rows than `limit`.**

| Field | Type | Verified note |
|---|---|---|
| `bookingCode` | str | **NOT unique per row** — one booking spanned 22 rows across 6 room types |
| `roomType` | str | matches `roomtype-list.name` exactly — the vocabularies DO intersect |
| `roomName` | str | matches `roomdetail-list.roomName`; can be the placeholder **`"Unassigned"`** (29 of 100 rows) |
| `status` | str | Vietnamese; see the verified table below |
| `bookDate` | str | **`YYYY-MM-DD HH:MM:SS` with real clock times** — ASSUMPTIONS U16 unlocked |
| `night` | int | **equalled the check-in→check-out span in all 22 rows** |
| `roomPrice` | int/float | **STAY TOTAL, not per night** — proven internally: 1 night = 500,000, 4 nights = 2,000,000, 3 nights = 1,500,000. ASSUMPTIONS U17 answered |
| `payment`, `balance`, `deposit`, `note`, `guestName`, `guestImagepaper` | — | stripped by the sanitiser |

#### `roomPrice` is a GROSS, guest-facing amount — ANSWERED from the data

Two independent lines of evidence, both from real rows:

1. **`balance == totalPrice - payment` on 122/122 reservations**, and a refunded
   booking reads `total=0, payment=600,000, balance=-600,000`. `balance` is a
   **guest ledger**, so `totalPrice` (= `roomPrice + servicePrice`, exact on
   122/122) is what the **guest owes** — not the hotel's receipt. A NET figure
   could not sit in that identity.
2. **`commiission` lives on the SOURCE, not the booking.** A per-channel
   commission percentage only has something to act on if the booking amount is
   gross. Were `roomPrice` already NET, the field would be inert.

**Consequence for this product, which prices in NET (V2):** a booking through a
commissioned channel must have its commission removed —
`net = roomPrice / nights * (1 - commiission/100)`. Implemented, with an unknown
commission REPORTED rather than defaulted to zero, because assuming 0%
overstates the achieved rate and biases recommendations upward.

Caveat, stated plainly: every observed booking came from `BE` at 0%, so this is
inference from structure rather than a vendor statement or a worked OTA example.
Worth confirming, but not worth blocking on.

**A row is ONE ROOM within a booking.** `(bookingCode, roomName, checkInTime)`
is not unique: seven groups collided in 100 real rows, up to five deep, all via
`"Unassigned"`. Row index is now part of our `external_id`.

### Status vocabulary — VERIFIED, derived ourselves

Filtered on each documented integer and read back the string:

| code | doc meaning | **actual string** | our earlier guess |
|---|---|---|---|
| 0 | confirmed | `Đã xác nhận` | correct |
| 1 | reserved/held | **`Đang giữ phòng`** | **WRONG** — we had `đã đặt` *and* `giữ chỗ`; neither exists |
| 2 | no show | `Không đến` | correct |
| 3 | check-in | `Đã nhận phòng` | correct |
| 4 | check-out | `Đã trả phòng` | correct |
| 5 | canceled | `Đã huỷ` | correct |
| -1 | deleted | **no rows over 8 months** | unconfirmed — deleted rows appear to be withheld |

Code 1 maps to ONE string, so the firm-vs-tentative split we had encoded does
not exist in this API.

### `GET /report-room-occupancy` — VERIFIED

**Field names differ from the document again:** `EmptyRoom` (not `RoomEmpty`),
`RoomTypeTotalRoomOccupied`, `RoomTypeTotalRoomEmpty`, `RoomTypeTotalOccupancyRate`,
and a `RoomTypeTotalBooked` the document never mentions.

- `TotalRoom − RoomOccupied − Blocked == EmptyRoom` holds on **420/420** real
  daily rows, and on the grand total. The document's failing sample was
  placeholder data.
- `OccupancyRate` is a **percentage (0–100)**, not a fraction.
- `Date` is `dd/MM/yyyy`.
- **Cross-check passed:** `TotalRoom` per room type matches the unit counts we
  derived from `roomdetail-list?roomtypeId=`.
- Constraint: `from`–`to` must not exceed one month.

> #### The report and the reservation list DISAGREE, and we do not know the rule
> Counting reservations by room-night reproduces the report on **406/420**
> room-nights including holds, **401/420** excluding them. Neither is exact, and
> the residue is not explained by status, by de-duplicating rooms, or by
> multi-room bookings. Some holds are counted, some are not.
>
> #### Narrowed as far as the API allows
> Re-fetched BACK TO BACK, one second apart, with `limit=500` so nothing was
> truncated: **identical mismatch, 406/420.** So it is not drift on a shared
> test tenant, and not pagination.
>
> Ruled out by inspection of the 14 mismatching room-nights:
> - **not status** — CT002133 is `Đang giữ phòng` and IS counted; CT002168 is
>   `Đang giữ phòng` and is NOT
> - **not double-counted rooms** — every room name is distinct and belongs to
>   the room type it claims, checked against `roomdetail-list?roomtypeId=`
> - **not payment state** — `payment`/`deposit` are 0 in both groups
> - **not booking age** — CT002168 (10:01:31) is excluded and CT002169
>   (10:03:07) is included, booked 96 seconds apart, both 1-night holds on
>   2026-09-01
>
> And the report is internally exact: `Căn hộ 02 phòng ngủ` totals 19
> room-nights = CT002133's 18 in-window nights + CT001984's 1. It is not
> approximating; it is deliberately excluding specific reservations.
>
> **Conclusion: the report is filtering on a per-reservation attribute that the
> `reservation` payload does not expose** — a hold expiry is the obvious
> candidate. That is now a precise question for Blue Jay with exact booking
> codes attached, rather than "the numbers don't match".
>
> **Therefore: use `report-room-occupancy` as the source for occupancy**, and
> reservations for `bookDate`, pickup and derived rate. Do not treat them as
> interchangeable, and do not silently prefer one.

### `GET /extraservice-sumary` — VERIFIED empty, still not used

Returns `{status, message, data: []}` for this tenant. Pricing does not need it.

---

## 6. Query parameters — what is VERIFIED to work

Everything below was exercised against the live API. A parameter not listed was
never tested; absence here means unknown, not unsupported.

### `/reservation`

| Parameter | Verified | Notes |
|---|---|---|
| `hotelId` | **yes** | required; empty or non-numeric → **HTTP 500 HTML** |
| `dateType=0` | **yes** | check-in date |
| `dateType=2` | **yes** | BOOKING date — this is how booking history is retrieved |
| `dateType=3` | **yes** | STAY NIGHT — bookings, occupancy and derived rate in one call |
| `dateType=1` | no | check-out; never tested |
| `from` / `to` | **yes** | `YYYY-MM-DD`. No range limit hit — 90 days worked |
| `limit` | **yes** | tested at 5, 10, 20, 100, 500. Documented default 20 |
| `page` | **yes** | 1-based; a page returning FEWER rows than `limit` is the end |
| `status=<int>` | **yes** | filters by the documented integer codes — see below |
| `sources=<int>` | **yes** | accepted; returns 0 rows when no booking matches |
| `roomTypes`, `roomdetails`, `search` | no | documented, never tested |

> #### How the status vocabulary was derived — reusable technique
> The response `status` is Vietnamese prose; the input `status` is an integer.
> The document maps neither to the other. Filtering on each integer in turn and
> reading back the string it returns produces the mapping without needing the
> vendor at all. Seven calls settled a question we had been about to email about.
>
> The same trick applies to any enum this API filters on but documents only on
> one side.

### `/roomdetail-list`

| `roomtypeId` | Result |
|---|---|
| valid integer | filters correctly |
| unknown integer (`999999`, `-1`) | 0 rows, `status: Success` |
| **non-integer (`abc`)** | **ALL rows** — filter silently ignored |
| **comma list (`6153,6154`)** | **ALL rows** — filter silently ignored |
| omitted or empty | all rows (reasonable: no filter) |

Rule: parseable as an integer → filters; otherwise ignored.

### `/source-list`

`categorySource=<int>` filters; an unknown category returns 0 rows with
`status: Success`. Observed: `2` → 14 rows, `0` → 7 rows, `99` → 0 rows.

### `/report-room-occupancy`

| Parameter | Verified | Notes |
|---|---|---|
| `dateType=1` | **yes** | daily detail |
| `dateType=2` | **yes** | monthly; `from`/`to` as `YYYY-MM` |
| `from` / `to` | **yes** | **must not span more than one month** — undocumented |

Extra unknown parameters are ignored rather than rejected (`roomtype-list` with
a bogus parameter answered normally).

---

## 7. What the vendor document gets WRONG

Kept as a list because it is the reason nothing here should be trusted without
observation.

| Document says | Reality |
|---|---|
| base URL `api-test.bluejaypms.com` *(English translation only)* | `api1.bluejaypms.com` — the original Vietnamese is correct |
| key goes in "the Header" (unnamed) | header is `apikey`, raw |
| `roomtypeName` | `name` |
| `RoomEmpty` | **`EmptyRoom`** |
| `RoomTypeRoomOccupied` / `RoomTypeBlocked` / `RoomTypeOccupancyRate` | `RoomTypeTotalRoomOccupied` / `RoomTypeTotalBooked` / `RoomTypeTotalOccupancyRate` |
| occupancy sample arithmetic | the sample's detail rows are placeholder and inconsistent; real rows hold 420/420 |
| `meta.total` implies a row count | capped at `limit` |
| nothing about a date-range limit | occupancy rejects ranges over one month |
| nothing about filters being ignored | a non-integer `roomtypeId` returns the whole property |
| `roomdetail-list` implies rows carry their room type | they do not; one call per type is required |

---

## 8. Still open — genuinely needs Blue Jay

1. **Why were report endpoints refused during the 08:00 window?** Every
   client-side explanation has been eliminated (§2). Decisive test: call
   `reservation` FIRST in the next 08:00 window, before anything else.
2. **Is `roomPrice` NET or gross?** We infer GROSS from two independent angles
   (§5), but no OTA booking exists on this tenant to confirm it directly.
3. **Why do `report-room-occupancy` and `reservation` disagree on ~3% of
   room-nights?** Narrowed to a per-reservation attribute the payload does not
   expose — a hold expiry is the obvious candidate. Exact booking codes in §5.
4. **What does `24-24h59` mean?** Never trusted, never called.
5. **Are `commiission` values meaningful on a real tenant?** The field is a
   percentage (5/10/15 observed), but every OTA source reads 0 here, which for a
   demo tenant more likely means "not configured".
6. **Luminous' own `hotelId`.** Everything above is tenant 1003, a demo
   property with 15 room types and 67 rooms. Luminous is 22 apartments across 3
   categories, and NOTHING has been verified against their data.
