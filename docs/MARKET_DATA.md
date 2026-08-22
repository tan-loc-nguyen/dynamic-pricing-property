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

## How the signal is computed

```
market_reference_price = median competitor price for this room + stay date
market_baseline_price  = median competitor price for this room across the horizon
market_price_index     = market_reference_price / market_baseline_price

market_factor = 1 + sensitivity × (market_price_index − 1)     [then clamped]
```

Guards, all configurable from **Pricing Rules**:

- fewer than `min_observations` (default 2) → neutral factor, and the UI says so
- observations older than `observation_max_age_days` (default 14) → ignored
- factor clamped to 0.90–1.15 so a thin or noisy sample cannot dominate
- `sensitivity` (default 0.50) damps the signal deliberately — see A16

Rationale for dividing by the market's own median rather than our base price is
in `DECISIONS.md` D5.

---

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
