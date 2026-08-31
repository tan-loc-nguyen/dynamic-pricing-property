# Running this project

Everything below runs on **generated demo data**. No credentials, no network,
no `.env` — the app is fully usable before anyone has Blue Jay access.

Vietnamese is the default language; English is one click away in the sidebar.

---

## The short version

```bash
make demo
```

Installs dependencies, rebuilds the demo database, and starts both servers.
Then open **<http://localhost:3000>**.

That is the whole thing. The rest of this page is what to do when it does not
work, and how to build the double-clickable version.

---

## What `make demo` actually does

| Step | Why it is there |
|---|---|
| `make setup` | Creates the Python venv and installs both dependency sets. Idempotent. |
| `make reseed` | Rebuilds the demo database **from scratch**, schema included. |
| `make dev` | API on `:8000`, web on `:3000`. |

The reseed runs **every time, unconditionally**. That is deliberate: a database
left over from before a schema change is the single most likely thing to stop
you, and it fails in a way that reads like the application is broken rather
than the data being old. Rebuilding takes a couple of seconds and removes the
whole class of problem.

Prerequisites are **Python 3.10+** and **Node 18+**. `make check` reports what
is missing without installing anything; `AUTO_INSTALL=1 make setup` installs
them for you.

---

## Confirming it works

Not "the servers started" — that is not the same as working. Open
<http://localhost:3000> and check:

1. **Rate** lists three room tiers, each with a suggested NET price and a line
   about how many units still have a free night.
2. Clicking a tile opens a drawer on the right. The price breakdown inside it
   should **add up** to the total above it — the lines are the real
   arithmetic, not a summary of it.
3. The left nav reads **Rate · Market · Customisation**, with the language
   switch and Settings pinned to the bottom.

`make test` should report **527 passed**. If it does not, stop there — a
failing suite means the demo data is not trustworthy either.

---

## The desktop build

For handing someone a file to double-click, or demoing without a terminal:

```bash
make bundle              # a few minutes
./dist/DynamicPricingProperty
```

One ~23MB executable. It serves the API and the web app from a single process
on the first free port, then opens your browser.

**Do not run `make bundle` while `make dev` is running.** The build deletes
`apps/web/.next`, which the dev server is using, and dev dies with a 500. Stop
dev first.

**PyInstaller cannot cross-compile.** A Windows `.exe` must be built on
Windows, a macOS binary on macOS. `.github/workflows/release.yml` builds both
on a tag.

---

## When something is wrong

**"table … has no column named …", or the app errors on first use**

Your database predates a schema change. Run `make reseed` — it drops and
recreates the schema, not just the rows.

**The same error, but in the packaged app**

The desktop build keeps its **own** database, separate from the repository's:

| Platform | Location |
|---|---|
| macOS | `~/Library/Application Support/DynamicPricingProperty/` |
| Windows | `%APPDATA%\DynamicPricingProperty\` |

There is no reseed command inside the packaged app, so **delete that file and
relaunch**. It seeds itself on startup. This only affects people who ran an
earlier build; a first run creates it fresh.

**macOS refuses to open the binary**

One you built yourself opens normally. One that was *sent* to you is
quarantined and unsigned: right-click → Open. Windows shows "Unknown
Publisher" for the same reason. The binaries are deliberately unsigned — note
that EV certificates stopped bypassing SmartScreen in 2024, so buying one would
not remove the warning.

**Port 3000 or 8000 is taken**

`make dev` expects them. The packaged binary does not — it takes whatever is
free and tells you which.

---

## What you are looking at

The demo portfolio is the real shape of the client's property: **22 apartments
across 3 categories**, ~91 forward nights, ~1,600 bookings with realistic
creation times, 15 validated rate bands, and ~1,200 market observations.

It is seeded deterministically, so everyone on the team sees the same numbers.

Nothing is ever pushed anywhere. The product recommends NET rates and records
what the operator decided; Blue Jay stays the system of record. See
[DECISIONS.md](DECISIONS.md) for why, and [../ASSUMPTIONS.md](../ASSUMPTIONS.md)
for which numbers are the client's real data and which the engineering team
invented.
