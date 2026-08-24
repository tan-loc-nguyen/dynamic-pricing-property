# Market Data

The engine turns competitor prices into a single **market factor**. Three
providers implement the same `MarketDataProvider` interface; the product works
fully with any of them, and works fine with none.

```
MarketDataProvider
├── MockMarketDataProvider      synthetic, deterministic  (default)
├── ManualMarketDataProvider    operator-entered          (always available)
└── PublicWebMarketDataProvider public pages prototype    (off by default)
```

## Confidence comes first

A competitor price is only useful if you know **what it is**. The same headline
number can be:

* a refundable OTA sell price, taxes included, for a 3-night stay; or
* a one-night NET rate, taxes excluded, on a promotional discount.

Only one of those is comparable to a Luminous NET rate. So every observation
carries its basis, and confidence is **derived** from that basis — never
asserted by the provider that produced it.

| Level | Means | Can move a rate? |
|---|---|---|
| `HIGH` | NET basis, comparable category, LOS, tax/fee and promotion all known | yes |
| `MEDIUM` | Known basis and category, minor gaps | yes (default gate) |
| `LOW` | Basis unknown — a generic headline price | **no** |
| `UNUSABLE` | No usable value | no |

Metadata captured per observation: `source`, `observed_at`, `stay_date`,
`room_category`, `length_of_stay`, `guests`, `price_basis`, `tax_inclusion`,
`fee_inclusion`, `promotion_status`, `is_refundable`, `confidence`,
`confidence_reason`, `notes`.

**Low-confidence evidence is shown, never applied.** It appears in the
recommendation breakdown as an explicitly *ignored* line with the reason, so the
operator can see it was considered. Silently dropping it would be just as
misleading as silently pricing on it.

## The comp set

Observations belong to a `Competitor` — a deliberately selected comparable
property, with location, comparable room category, source and active flag.
A comp set is a judgement about which properties a guest genuinely chooses
between; it is not a search result. Managed manually on the **Market** screen.

The demo comp set is invented (ASSUMPTIONS U12) and must be replaced with the
operator's real list.

## How the signal is computed

```
qualified              = observations at or above the confidence gate
market_reference_rate  = median(qualified for this room type + stay date)
market_baseline_rate   = median(qualified for this room type across the horizon)
market_price_index     = market_reference_rate / market_baseline_rate

adjustment_pct = sensitivity x (market_price_index - 1) x 100   [then capped]
```

Guards, all configurable from **Dynamic Rules**:

- observations below the confidence gate are excluded from both the reference
  *and* the baseline;
- fewer than `min_observations` qualified (default 2) → no adjustment;
- observations older than `observation_max_age_days` (default 14) → ignored;
- adjustment capped at ±5%;
- `sensitivity` (default 0.50) damps the signal deliberately.

Rationale for dividing by the market's own median rather than our BASE rate is
in `DECISIONS.md` D5: it keeps the signal independent of our own pricing.

## 1. Mock (default)

Deterministic synthetic observations for every room and stay date, with
scripted strong-market, weak-market and **deliberately missing** dates so the
neutral-factor path is visible in the demo.

## 2. Manual — the reliable fallback

The **Market Data** screen lets an operator record competitor/reference name,
stay date, observed price, source URL and notes. Every observation stores its
provenance and collection timestamp.

This is the mode to trust. Competitor prices that an operator has actually
looked at are worth more than anything a generic extractor produces.

```bash
curl -X POST http://127.0.0.1:8000/api/market/observations \
  -H 'Content-Type: application/json' \
  -d '{"stay_date":"2026-09-20","competitor_name":"Saigon Sky Apartments",
       "observed_price":1750000,"room_id":1,"source":"manual",
       "notes":"Comparable studio, same building line"}'
```

## 3. Public web — prototype only

**Disabled by default.** Enable with:

```bash
MARKET_PUBLIC_ENABLED=true
MARKET_PUBLIC_SOURCES=https://example-hotel-site.com/rooms
```

What it does:
- checks `robots.txt` **before** fetching and obeys a disallow
- identifies itself with a descriptive, contactable User-Agent
- extracts VND-shaped prices with a conservative regex, filtered to a plausible
  200,000–50,000,000 VND range
- records source URL and timestamp on every observation

What it will **not** do, by design:
- no CAPTCHA solving, no login bypass, no anti-bot evasion
- no IP or identity rotation
- **refuses Airbnb, Booking.com, Agoda, Expedia, Trip.com and TripAdvisor
  outright** — their terms prohibit automated access
- no retries on 401/403/429 — a refusal is treated as "do not collect"
- never a functional dependency

### You must supply the URLs — there is no discovery

`MARKET_PUBLIC_SOURCES` is a static, operator-curated list. The system never
searches for competitors, because automated discovery means scraping search
results or OTA listings — precisely the prohibited territory. Choosing a
comparable set is a judgement call anyway (see A22).

### Known limitation 1 — the URL is fetched verbatim, so the price is not date-specific

**This is the most important caveat.** The collector performs a plain GET on
each configured URL. It does **not** inject check-in/check-out dates into the
query string, because the parameter names differ per site and guessing them
would be inventing an API contract.

Consequence: the price extracted is "whatever that page displays by default",
and the `stay_date` you pass is applied as a *label* on the observation. Unless
the configured URL already encodes the dates you care about, a public-web
observation is a **rough level indicator, not a true rate for that night**.

Mitigations, in order of preference:
1. configure URLs that already pin the dates you want, if the site supports it;
2. use manual entry, where the operator has actually seen the correct date;
3. treat the public-web signal as low-confidence and keep `sensitivity` low.

Because of this, `MARKET_PROVIDER=public_web` is **not** recommended as the
standing provider. It exists to prove the adapter pipeline.

### Known limitation 2 — stated plainly

Most accommodation pages render prices client-side, and markup varies per site,
so a generic server-side extractor is unreliable. **This is not solved and
should not be.** When extraction fails, the collector returns a clear message
plus a remediation hint, the pricing engine applies a neutral market factor,
and manual entry remains available.

The prototype's purpose is to prove the pipeline —
`external source → normalization → market signal → pricing engine` — and to
establish the adapter boundary. Making it robust across arbitrary sites is a
separate project with its own legal review, and is explicitly out of scope.

### Recommended production path

Rather than scraping, prefer in this order:
1. a licensed market-data feed (STR, OTA Insight, Key Data, Transparent);
2. official partner APIs where Luminous has a commercial relationship;
3. operator-entered manual observations (already built);
4. public sources only where terms clearly permit it.
