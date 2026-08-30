# Blue Jay PMS Integration

## Status: VERIFIED against the live API, on a demo tenant

> **Called successfully on 2026-08-27**, both testing windows. Every documented
> endpoint answered, and the adapter is wired to what they actually return —
> replayed end to end against the real captures: 67 units across 3 categories
> matching the property exactly, 66 unit-nights from 22 reservations, no
> warnings.
>
> **The English translation of the API document had the wrong base URL.** It
> gives `api-test.bluejaypms.com`; the original Vietnamese says
> `api1.bluejaypms.com`. The `api-test` host exists and serves a DIFFERENT
> booking-engine API, so every documented endpoint 404s there. That cost most of
> the first window.
>
> **But it is a DEMO tenant** (`hotelId=1003`, 15 room types, 67 rooms), not
> Luminous. See "What is still unresolved".
>
> Three data modes are interchangeable: **LIVE**, **SNAPSHOT** (sanitized real
> data, the preferred demo source) and **MOCK**. Switch in Settings → Data.

What exists:

- `BlueJayPMSProvider` normalises Blue Jay JSON into vendor-neutral DTOs.
  Nothing downstream knows the vendor.
- **Read-only by construction.** `BlueJayClient` exposes no verb but `GET`.
- **Window-gated.** A request outside a confirmed Vietnam-time window is refused
  before it leaves the process. Note the FILTER endpoints turned out not to be
  window-restricted at all — only the reports are.
- **Paged.** `meta.total` is capped at `limit`, so the adapter pages until a
  page comes back short.
- Credentials come from the environment only; the key is never logged, captured
  or rendered.
- An unreadable response **raises rather than returning nothing**: zero bookings
  would mean 0% occupancy across the horizon, the strongest discount signal the
  engine has.

## How to enable it

```bash
# .env
BLUEJAY_BASE_URL=https://api-test.bluejaypms.com/api/v2
BLUEJAY_API_KEY=<secret — never commit this>
BLUEJAY_HOTEL_ID=<Luminous' hotelId — 1003 in the doc is a DIFFERENT property>
BLUEJAY_PSEUDONYM_SALT=<set before capturing anything real>
BLUEJAY_SNAPSHOT_DIR=<path to a captured snapshot>
```

The data source itself is switched in **Settings → Data**, not in `.env` — the
environment only seeds the initial value. Then map each Blue Jay room type to a
pricing category on the same screen; anything unmapped is not priced.

Nothing else in the codebase changes: the sync layer, feature engine, pricing
engine, database, API and UI all consume vendor-neutral DTOs.

If Blue Jay is misconfigured or unreachable, `POST /api/sync` automatically
falls back to the mock provider and reports `pms_fallback_to_mock: true`, so a
demo can never be broken by an integration outage.

---

## Status of the two hard blockers — BOTH UNBLOCKED

| | Was | Now |
|---|---|---|
| **U11** units per room category | hard blocker; occupancy undefined without it | `roomdetail-list?roomtypeId=` returns one type's rooms. Verified on a demo tenant: 15 types, 67 rooms, per-type counts summing exactly to the unfiltered list. Costs N+1 calls. |
| **U16** booking creation timestamp | hard blocker; pickup permanently neutral | `reservation.bookDate` carries `YYYY-MM-DD HH:MM:SS` with real clock times. Pickup and a fitted booking curve are both possible. |

Neither is verified against **Luminous'** data — see below.

---

## What is still unresolved

Surfaced in the UI (`GET /api/status` → `pms.unresolved_mappings`) so they are
visible rather than buried, and kept short on purpose: a list that keeps asking
settled questions teaches the reader to skip the panel.

1. **Luminous' own `hotelId`.** Everything verified is tenant 1003, a DEMO
   property of 15 room types and 67 rooms. Luminous is 22 apartments across 3
   categories. **Nothing has been checked against their data.** This is now the
   largest gap in the integration.
2. **Why report endpoints were refused during the 08:00 window** while filters
   answered normally. Every client-side explanation eliminated. Decisive test:
   call `reservation` FIRST in the next 08:00 window.
3. **Is `roomPrice` NET or gross?** We infer gross from two independent angles;
   no OTA booking exists on this tenant to confirm directly (U14).
4. **Why `report-room-occupancy` and `reservation` disagree on ~3% of
   room-nights.** Narrowed to a per-reservation attribute the payload does not
   expose.
5. **What `24:00-24:59` means.** Never trusted, never called.
6. **Whether `commiission` carries real values on a live tenant** (U13).
7. **Whether any endpoint publishes a forward-looking rate.** None found, so
   `current_net_rate` is reconstructed. Probably permanent.
8. **Whether Blue Jay's Yield Management is active on the Luminous tenant.** If
   it already moves rates, the two systems would fight.
9. **How far back reservation history can be exported** (U15).

The full endpoint contract — every verified field, every query parameter, both
error grammars, and a table of what the vendor document gets wrong — is in
**[BLUEJAY_CONTRACT.md](BLUEJAY_CONTRACT.md)**.

---

## Security

- Blue Jay is only ever reached through `BlueJayPMSProvider`; no other module
  knows the vendor exists.
- No credential is ever written to source. `Settings.redacted()` exposes only
  `bluejay_api_key_present: true|false`, never the value.
- `.env` is gitignored; `.env.example` contains empty placeholders.
- The adapter never logs the key, including in error paths.
- **No credentials were found committed anywhere in this repository.**
