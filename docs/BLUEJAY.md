# Blue Jay PMS Integration

## Status: boundary implemented, **not wired to a live API**

The project brief stated that Blue Jay API documentation and credentials would
be available locally. **They were not present** in this repository, or anywhere
on the build machine (the whole workspace was searched for `blue jay`,
`bluejay`, and `luminous`).

Per the brief's explicit instruction — *"do not invent endpoints, do not invent
request schemas, do not invent field mappings"* — **nothing has been assumed**.

What exists instead:

- `BlueJayPMSProvider` fully conforms to the `PMSProvider` contract, so
  switching to it is a `.env` change and nothing else.
- Credentials are read from environment variables only; none are committed.
- An authenticated `httpx` client is constructed as soon as a base URL and key
  are present, with the auth *style* configurable because the real scheme is
  unconfirmed.
- Every fetch raises `ProviderUnavailable` carrying an actionable remediation
  message, which the API surfaces as a status banner before falling back to
  demo data.

**Demo mode is completely unaffected.** The product is fully usable today.

---

## How to enable it once the docs arrive

```bash
# .env
DATA_PROVIDER=bluejay
BLUEJAY_BASE_URL=https://<tenant>.bluejay.example/api
BLUEJAY_API_KEY=<secret — never commit this>
BLUEJAY_AUTH_STYLE=bearer          # or "header"
BLUEJAY_AUTH_HEADER=Authorization  # e.g. X-API-Key when style=header
BLUEJAY_PROPERTY_IDS=<comma-separated ids>
```

Then implement the four `TODO(bluejay)` markers in
`apps/api/dynamic_pricing/providers/pms/bluejay.py`. Nothing else in the codebase
needs to change: the sync layer, feature engine, pricing engine, database, API
and UI all consume vendor-neutral DTOs.

If Blue Jay is misconfigured or unreachable, `POST /api/sync` automatically
falls back to the mock provider and reports `pms_fallback_to_mock: true`, so a
demo can never be broken by an integration outage.

---

## Unresolved mappings — questions for the Blue Jay integration call

These are surfaced in the UI (`GET /api/status` → `pms.unresolved_mappings`) so
they are visible rather than buried.

### Authentication & transport
1. Base URL and API version prefix for the Luminous tenant.
2. Authentication scheme — Bearer token, `X-API-Key` header, or OAuth2 client
   credentials? Do tokens expire, and is there a refresh flow?
3. Rate limits and quota policy. Is bulk/date-range fetching supported, or must
   we page per date?

### Properties & rooms
4. Endpoint listing properties, and its pagination contract.
5. Endpoint listing room types.
6. **Does Blue Jay expose "number of physical units" per room type?** This is
   required for the occupancy signal. If it only exposes individual units, the
   grain decision in `DECISIONS.md` D2 needs revisiting.

### Availability / inventory
7. Endpoint for per-date availability.
8. Does it return **units sold** or **units remaining**? (Either works; we need
   to know which.)
9. Which field carries the **currently published nightly rate**, and is it net
   or gross of taxes, fees and OTA commission?
10. Do **rate plans** exist? If a date has several, which one is "the" price —
    and does length-of-stay pricing apply?

### Bookings
11. Endpoint for reservations.
12. **Is a booking creation timestamp available?** This is a hard requirement
    for the booking-pace signal (A11–A13). Without a `created_at`, booking pace
    cannot be computed and the engine will apply a neutral factor.
13. Is the OTA/channel recorded per booking?
14. How are cancellations represented — status change, or deletion?

### Pricing guardrails
15. Do min/max price constraints already exist in Blue Jay, or are they
    Luminous-side policy that this system should own? (See A2/A3.)

### Write-back (future, explicitly out of scope for the MVP)
16. Is there a rate-update endpoint, and what are its idempotency semantics?
17. Does a price update propagate to OTAs automatically, or is a separate
    channel-manager push required?

---

## Field-mapping worksheet

Fill this in during the integration call. The left column is what the domain
model needs; the right is what Blue Jay actually calls it.

| Internal field | Type | Blue Jay field | Notes |
|---|---|---|---|
| `Property.external_id` | str | | |
| `Property.name` | str | | |
| `Property.currency` | str | | assume VND? |
| `Room.external_id` | str | | |
| `Room.units_total` | int | | **required for occupancy** |
| `Room.base_price` | float | | net or gross? |
| `Room.min_price` / `max_price` | float | | may not exist in Blue Jay |
| `StayDateInventory.stay_date` | date | | |
| `StayDateInventory.units_sold` | int | | or derive from units remaining |
| `StayDateInventory.current_price` | float | | which rate plan? |
| `Booking.booked_at` | date | | **required for booking pace** |
| `Booking.stay_date` | date | | expand multi-night stays? |
| `Booking.channel` | str | | |
| `Booking.status` | str | | cancellation representation |

---

## Security

- No credential is ever written to source. `Settings.redacted()` exposes only
  `bluejay_api_key_present: true|false`, never the value.
- `.env` is gitignored; `.env.example` contains empty placeholders.
- The adapter never logs the key, including in error paths.
- **No credentials were found committed anywhere in this repository.**
