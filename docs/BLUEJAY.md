# Blue Jay PMS Integration

## Status: boundary implemented, **not wired to a live API**

The Blue Jay API documentation is **not yet available**. The client document
states plainly that API access has been requested and Luminous is *awaiting
confirmation from Blue Jay*. Nothing was found on the build machine either.

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

### Properties, room types & units
4. Endpoint listing properties, and its pagination contract.
5. Endpoint listing **room types**, and how the category (2BR Regular / 2BR
   Premium / 3BR) is keyed.
6. Endpoint listing **physical rooms**, and how many of the 22 units belong to
   each room type. **HARD BLOCKER** — occupancy is computed per room type, so
   without the unit split the pace signal is wrong (see ASSUMPTIONS U11).

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
12. **Is a booking creation timestamp available? HARD BLOCKER.** Required twice
    over: for the recent-pickup signal, and to fit real booking curves to
    replace the demo curve (ASSUMPTIONS U1/U16). Without it, pickup is
    permanently neutral and pace position rests on invented curves.
12b. **How far back can reservation history be exported?** The client reports
    Blue Jay has no data retention but that history *can* be extracted with
    time. This is the single biggest unlock in the project (ASSUMPTIONS U15).
13. Is the OTA/channel recorded per booking?
14. How are cancellations represented — status change, or deletion?

### Rates
15. Which field carries the **NET revenue to Luminous**, versus the guest-facing
    OTA sell price? The seasonal rate book is NET, so this determines whether
    'current rate' is comparable at all (ASSUMPTIONS U14).
16. Do rate plans / length-of-stay pricing exist, and how do they collapse to a
    single nightly rate?
17. **Is Blue Jay's built-in rule-based Yield Management active?** If it is
    already moving rates by remaining inventory, its behaviour must be
    understood before this system's recommendations are applied, or the two
    will fight each other.

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
| `RoomType.external_id` | str | | |
| `RoomType.category` | str | | 2br_regular / 2br_premium / 3br |
| `RoomType.units_total` | int | | **HARD BLOCKER — required for occupancy** |
| `PhysicalRoom.unit_label` | str | | the 22 individual apartments |
| `StayDateInventory.current_net_rate` | float | | **NET to Luminous**, not OTA sell |
| `StayDateInventory.current_ota_price` | float | | only if genuinely available |
| `StayDateInventory.stay_date` | date | | |
| `StayDateInventory.units_sold` | int | | or derive from units remaining |

| `Booking.booked_at` | date | | **HARD BLOCKER — pickup + booking curves** |
| `Booking.net_rate` | float | | NET revenue received |
| `Booking.stay_date` | date | | expand multi-night stays? |
| `Booking.channel` | str | | |
| `Booking.status` | str | | cancellation representation |

---

## Security

- Blue Jay is only ever reached through `BlueJayPMSProvider`; no other module
  knows the vendor exists.
- No credential is ever written to source. `Settings.redacted()` exposes only
  `bluejay_api_key_present: true|false`, never the value.
- `.env` is gitignored; `.env.example` contains empty placeholders.
- The adapter never logs the key, including in error paths.
- **No credentials were found committed anywhere in this repository.**
