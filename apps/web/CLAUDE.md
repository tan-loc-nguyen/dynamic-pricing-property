# apps/web — frontend conventions

This file is scoped to `apps/web`. Read `../CLAUDE.md` first for the whole-repo picture (the pricing pipeline, D10 — no pricing logic here, the i18n contract with the backend). This file covers conventions established during the shadcn/ui migration and visual redesign that aren't derivable from a quick read of the code.

## Commands

```bash
npm run dev              # dev server on :3000
npm test                 # full Vitest + React Testing Library suite
npx vitest run path/to/File.test.tsx   # a single test file
npm run build             # next build (static export — see output: "export" below)
npm run check:messages    # ICU-parses messages/{en,vi}.json and checks they describe the same keys
```

Next.js is configured with `output: "export"` and `trailingSlash: true` (`next.config.mjs`) because the desktop build serves this app as static files from a single Python-packaged binary (root `CLAUDE.md`, D32). Consequences that look like bugs but aren't:
- Hard-navigating to a route without a trailing slash (`/en/market`) can 404 in dev; `/en/market/` or client-side `<Link>` navigation works. Don't "fix" this by removing `trailingSlash`.
- Nothing here can rely on a Next.js server runtime (middleware, server actions, ISR) — there is no server at runtime, only static files.

## Component architecture

- `components/ui/` — shadcn-owned. Generated via `npx shadcn add <name>`. Extending one with a genuinely new variant (we added a `size` variant to `badge.tsx` and a `flush` size to `card.tsx`) is normal shadcn usage — that's what "you own this code" means. What to avoid is silently re-running `add` over a file you've customized; check the diff first.
- `components/*.tsx` (flat, top level) — domain wrapper components: `Chip`, `StatusBadge`, `Spinner`, `Empty`, `Field`, `PageHeader`. These exist because either (a) they carry domain logic a generic shadcn primitive shouldn't (i18n lookups, a closed `Status`/`tone` vocabulary — `Chip`/`StatusBadge`), or (b) the shadcn primitive's documented API doesn't fit without a deliberate deviation. `Field` is the example of (b): it nests its child *inside* `FieldLabel` instead of shadcn's documented sibling-plus-`htmlFor`/`id` pattern, specifically to keep native label↔control association without plumbing an id through ~35 call sites — see the comment in `Field.tsx` before "fixing" this to match shadcn's docs.
- `components/{market,customisation}/` — feature-scoped components, not shared.
- Prefer extending an existing shadcn primitive (a new variant) over reaching for a raw Tailwind class when the same visual need will recur — that's the DRY lesson from the Card `border`/`py-0` cleanup (both became a `variant`/`size` on `Card` itself instead of a repeated className at every call site).
- Three components (`RangeDrawer`'s Dialog, `DataSourceStatus`'s Popover, the customisation Tabs) import primitives directly from the unified `radix-ui` package rather than through `components/ui/`. This was deliberate: all three are fully custom-styled with no benefit from shadcn's opinionated wrapper, and in Dialog's case the wrapper's centered-modal positioning actively conflicts with the drawer's slide-in-from-the-right layout. The unified `radix-ui` package's exports are confirmed byte-identical re-exports of the individual `@radix-ui/react-*` packages (checked in `node_modules` directly) — treat this as the sanctioned pattern for a bespoke overlay, not a one-off exception.

## Design tokens

All colors are custom `@theme` tokens in `app/globals.css`, on a warm "quiet luxury hospitality" palette (not the generic indigo-on-cool-gray SaaS default). **The important non-obvious thing**: Tailwind's own built-in color scales are redefined, not just the custom `ink`/`brand` ones —

| Tailwind class | Actually renders as | Role |
|---|---|---|
| `ink-*` | warm charcoal (limestone→walnut) | neutral text/structure — not literal "ink" navy |
| `brand-*` | antique brass | primary accent — not indigo |
| `emerald-*` | forest green | positive / accepted / on-pace |
| `amber-*` | clay/ochre | warning / unvalidated / pending |
| `rose-*` | oxblood | negative / error / destructive |
| `sky-*` | slate blue | market/info — the one deliberate cool counterpoint |
| `violet-*` | muted plum | `StatusBadge` "overridden" only |

So `bg-emerald-50 text-emerald-700` in a `.tsx` file is correct and intentional — it is **not** rendering literal emerald green. Don't "fix" a color that looks off by reasoning from the Tailwind class name; check the actual compiled value in `globals.css`. shadcn's own semantic tokens (`--background`, `--primary`, `--muted-foreground`, etc.) reference these same `--color-ink-*`/`--color-brand-*` variables via `var()` rather than duplicating hex — if you need a new semantic token, reference the existing scale, don't hand-copy a hex value (that's exactly the drift `lib/formControls.ts`'s `selectClass` used to have against `Input`, now fixed by importing `inputClassName` from `components/ui/input.tsx`).

`ink-400` and darker are tuned to clear 4.5:1 contrast (WCAG AA, normal text) against both the page background and white cards — this was hand-verified with actual relative-luminance math after the first pass of the redesign shipped a value that measured 2.5:1. If you change any `ink-*` or `brand-*` value, recompute contrast rather than eyeballing it; the comment above the ramp in `globals.css` has the reasoning.

## Typography

Two typefaces, loaded via `next/font/google` in `app/[locale]/layout.tsx` (not the pass-through root `app/layout.tsx`, which has no `<html>`/`<body>` to attach a font class to):
- **Fraunces** (`font-serif`/`font-heading`) — identity moments only: page titles (`PageHeader`), the brand mark, shadcn's own `CardTitle`/`EmptyTitle` (which already default to `font-heading`).
- **Karla** (`font-sans`) — everything functional: body text, labels, data, forms. This is the default; you don't need to apply it explicitly.

Do not add a third typeface or use Fraunces for body/data text — legibility in dense tables was a deliberate reason to keep the serif restricted to headline moments.

**Gotcha already hit once**: `--font-sans` and `--font-heading` are theme-level CSS custom properties in `@theme inline`. If a font variable (`--font-karla`, `--font-fraunces`) isn't actually in scope where `--font-sans` is evaluated, the reference is a *guaranteed-invalid* custom property, not a graceful fallback — the whole site silently falls back to the browser default serif with no error. This happened for most of a session before being caught. Put font `variable` classes on `<html>`, not a nested element, and if you ever see the app rendering in an unexpected serif, check `getComputedStyle(document.documentElement).fontFamily` and the compiled `--font-sans` value in `.next/static/css/*.css` before assuming it's a Tailwind/Next issue elsewhere.

## Icons

`lucide-react` (already a dependency via shadcn). Thin-line style — pass `strokeWidth={1.5}` or `{2}` explicitly, size 12–18px depending on context. Used for: navigation (one icon per section, recognition-based), status/trend direction (pace ahead/behind, tile change %), and one shared `Inbox` icon on the `Empty` component (added once there, applies to every empty state app-wide — don't add a different icon per call site, that was a deliberate restraint decision, not an oversight). Don't add decorative icons to elements that don't need one — the design direction explicitly avoids icon-soup.

## i18n / copy conventions

- Never render an ALL-CAPS label via a translation string or CSS (`uppercase tracking-wide`) for emphasis — this reads as generic AI-generated-design chrome. The one legitimate exception is a `<th>` table header in a dense data grid (a real, functional convention, not decoration) — those stay as-is.
- Don't capitalize a single word inside an otherwise sentence-case string for emphasis either (e.g. `"Event impact sizes are UNVALIDATED"`) — same tell, just hidden in message content instead of a CSS class. Fix in both `messages/en.json` and `messages/vi.json`; check for the same pattern in both locales, they've drifted independently before.
- Every key the engine can emit needs both an English and Vietnamese string, or a backend test fails (see root `CLAUDE.md`). Run `npm run check:messages` after editing translation files.

## Testing

Vitest + React Testing Library, colocated as `ComponentName.test.tsx`. Convention: domain wrapper components in `components/*.tsx` get tests (they carry real logic — tone maps, i18n fallback, the `Field` label-association behavior). Vendored primitives in `components/ui/` don't get dedicated tests — they're shadcn's own generated code, not logic this project authored. `components/test-utils.tsx` exports `renderWithIntl` for components that call `useTranslations`.

## Known limitation

Mobile responsiveness is out of scope by explicit decision, not an oversight — the sidebar is a fixed `w-[212px]` with no breakpoint and breaks badly under ~400px wide. This is a working tool for a revenue manager at a desk (same category of decision as "no dark mode"), and fixing it properly is a full mobile-nav-pattern undertaking, not a quick patch. Don't attempt a partial fix (e.g. just hiding the sidebar) without raising it as its own piece of work.
