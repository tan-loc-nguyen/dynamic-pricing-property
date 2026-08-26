# Blue Jay — provisional contract and verification checklist

**Every statement in this file is PROVISIONAL.** It is derived from Blue Jay's
API document (`private/BLUE_JAY_BE_API_Report_EN.md`, gitignored), not from an
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

## Field mapping, as currently implemented

### `reservation` → `BookingDTO` (one row per **occupied unit-night**)

| Blue Jay | Our field | Note |
|---|---|---|
| `checkInTime` … `checkOutTime` | `stay_date` × N | checkout day is **not** an occupied night |
| `bookDate` | `booked_at` | **unblocks U16** — pickup and booking curves |
| `roomType` (name) | `room_type_external_id` | resolved via `roomtypeId`, see below |
| `roomPrice` ÷ nights | `net_rate` | **UNVERIFIED**, see U17 |
| `source` | `channel` | |
| `status` | `status` | **mostly guessed**, see U18 |
| `roomName` | `physical_room_external_id` | |
| — | `nights` | **always 1**; Blue Jay's `night` is a stay length |
| — | `guests` | not present in the payload |

### Why the category map is keyed on `roomtypeId`

The reservation payload references room types by **localised display name
only**. Those names are editable in Blue Jay's UI, and the document's own
two-row sample already uses two conventions at once ("Holo Ben Thanh - 1 PN"
beside "Căn hộ 3 phòng ngủ"). Worse, the reservation payload and the filter
endpoint may not even use the same vocabulary — the one place the document
pairs an id with a name gives `6153 = "Apartment Double VIP"`, which matches
neither reservation sample.

So the persisted map is `roomtypeId → category`, and `name → category` is
rebuilt from `roomtype-list` on **every sync**. A rename cannot unmap a
category.

---

## Verification checklist — work down this during the next window

Run `python scripts/bluejay_probe.py` first. It makes **no calls** and prints
the window status. Then `--probe` (shapes only, no values), then `--capture`.

- [ ] **Status vocabulary.** The single highest-value output. We have ONE
      observed value (`Đã huỷ`) and nine inferences. A wrong inference does not
      raise — it silently miscounts occupancy. `--capture` prints every distinct
      status seen and flags any not in our vocabulary.
- [ ] **`roomPrice`: stay total or nightly rate?** Both samples are `night: 1`,
      where those are the same number. Find any multi-night reservation.
- [ ] **`roomPrice`: NET or gross of OTA commission?** (U14)
- [ ] **Is a reservation row one physical room, or a group booking?**
      `roomName` is documented as "Physical room", which suggests one room.
- [ ] **`roomtype-list` / `roomdetail-list` field names.** Entirely inferred.
- [ ] **Do the reservation payload and `roomtype-list` use the SAME room-type
      names?** Keying the map on `roomtypeId` protects against a rename, but a
      reservation still joins to its room type by NAME, so two different
      vocabularies would break every row. The one place the document pairs an
      id with a name gives `6153 = "Apartment Double VIP"`, which matches
      neither reservation sample — so this is a live risk, not a hypothetical.
      It fails LOUDLY today (`UnmappedValue`), never silently.
      **If they diverge**, the fix is to stop name-joining: query `reservation`
      once per room type using the documented `roomTypes=<id>` filter, so each
      response is known to belong to that id. That is 3 calls instead of 1 for
      Luminous — affordable even in a 30-minute window.
- [ ] **Does `report-room-occupancy` project forward?** If not, occupancy must
      come from reservations, as it currently does.
- [ ] **Which endpoint publishes a forward rate?** None is documented. If none
      exists, `current_net_rate` stays derived and that is permanent.
- [ ] **Pagination.** The documented default is 20 rows. We send `limit=5000`.
      Confirm the maximum and whether `meta.total` requires paging.
- [ ] **Rate limits and quota.**
- [ ] **The `24:00-24:59` window.**
- [ ] **Luminous' own `hotelId`.** `1003` is a different property.
- [ ] **Is Blue Jay's built-in Yield Management active on this tenant?** If it
      already moves rates, the two systems would fight.

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
