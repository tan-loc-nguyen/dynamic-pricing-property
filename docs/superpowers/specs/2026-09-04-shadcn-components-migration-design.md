# shadcn/ui components library migration — design

Status: approved by user, ready for implementation planning
Date: 2026-09-04
Scope: `apps/web` only

## Why

`apps/web/components/ui.tsx` is a single hand-rolled file of shared UI
primitives (Card, Button, Chip, StatusBadge, Field, Empty, Spinner,
PageHeader, `inputClass`), imported by 16 files. Three other files import
Radix primitives directly (`@radix-ui/react-tabs`, `-dialog`, `-popover`)
with no shared wrapper. There is no `cn` helper, no `class-variance-authority`,
no shadcn CLI config. This spec re-platforms that layer onto shadcn/ui so new
UI work builds on a documented, regenerable component set instead of one-off
hand-written primitives.

**This is a pure plumbing migration.** Visual redesign (retinting the app's
`ink-*`/`brand-*` palette, restyling `viz.tsx`/`MarketOverview.tsx` charts) is
an explicitly separate, later task. Where this migration changes visual
appearance as a side effect (see Tokens below), that is accepted now and will
be reconciled in the redesign pass — not solved here.

## Current stack facts (verified in-repo)

- Next.js 15.5.4, React 19.1.0, TypeScript 5.7 (`strict`, `noUnusedLocals`,
  `noUnusedParameters`), App Router with `[locale]` routing via next-intl.
- Tailwind CSS v4.1.13, **CSS-first config** — no `tailwind.config.*` file;
  tokens are declared via `@theme` directly in `apps/web/app/globals.css`
  (`--color-ink-50..950`, `--color-brand-50..700`, `--font-sans`).
- Path alias: `@/*` → `apps/web/*` (tsconfig `paths`).
- No `components.json`, no `clsx`/`tailwind-merge`/`class-variance-authority`/
  `lucide-react` in `package.json`.
- Radix packages already installed: `@radix-ui/react-dialog`,
  `-popover`, `-tabs`, `-tooltip` (tooltip currently unused anywhere).
- No test framework in `apps/web` (no jest/vitest/playwright, no
  `.test.`/`.spec.` files). Verification is `next build` (type-checking) plus
  manual browser QA.
- 350 raw `ink-*`/`brand-*` Tailwind class occurrences across 21 files
  **outside** `components/ui.tsx` — those files are **out of scope** for this
  migration (see Out of scope).

## Tokens

shadcn init runs in Tailwind v4 mode with the **Zinc** stock base color/theme
(closest to the current cool-gray `ink-*` scale without attempting to match it
exactly — no attempt is made to match it, since redesign is deferred).

- Adds shadcn's standard semantic CSS variables (`--background`,
  `--foreground`, `--primary`, `--primary-foreground`, `--secondary`, `--muted`,
  `--muted-foreground`, `--accent`, `--destructive`, `--border`, `--input`,
  `--ring`) to `app/globals.css` via `@theme inline`, using shadcn's stock
  values (not seeded from `ink-*`/`brand-*`).
- The existing `@theme` block (`--color-ink-*`, `--color-brand-*`,
  `--font-sans`) is left **untouched** — still consumed by the 21 out-of-scope
  files.
- Dark mode variables/toggle: **not** added (app is light-mode only today; no
  `next-themes` dependency, no `.dark` usage anywhere).
- **Known consequence, accepted**: migrated components (Button, Card, Badge)
  will render in shadcn's stock zinc/blue against surrounding chrome still
  styled with `ink-*`/`brand-600` indigo. This seam is deliberate and
  temporary — reconciled in the later redesign pass, not this one.

## Setup & tooling

1. `npx shadcn@latest init` — Tailwind v4 mode, Zinc base color, **default**
   style (not "new-york" — no stated preference, default keeps closer to
   plain/no-extra-shadow conventions already in use). Creates
   `components.json` and appends the semantic tokens above to `globals.css`.
   Registry flavor: **Radix**, not Base UI or React Aria — the project
   already depends on `@radix-ui/react-{dialog,popover,tabs,tooltip}`
   directly, so pulling Radix-backed shadcn components keeps one underlying
   primitive library instead of mixing two.
2. New dependencies (added by the CLI as components are pulled in):
   `clsx`, `tailwind-merge`, `class-variance-authority`, `lucide-react`,
   `tw-animate-css`.
3. `lib/utils.ts` — the standard shadcn `cn()` helper (`clsx` +
   `tailwind-merge`).
4. `components/ui/` becomes the shadcn-owned directory — files written by
   `shadcn add <name>` and not hand-edited beyond what the CLI generates.

## Component mapping

Locked mapping from `components/ui.tsx` (and the 3 raw-Radix sites) to
shadcn, confirmed via context7 against the current shadcn/ui docs:

| Old | New | CLI command | Notes |
|---|---|---|---|
| `Card` | `components/ui/card.tsx` | `add card` | Direct replacement. |
| `Button` | `components/ui/button.tsx` | `add button` | Variant rename: `primary → default`, `danger → destructive`, `secondary`/`ghost` unchanged. Size rename: `md → default`, `sm` unchanged. |
| `inputClass` | `components/ui/input.tsx` | `add input` | Callers switch from `<input className={inputClass} .../>` to `<Input .../>`. |
| `Field` | `components/ui/field.tsx` (`Field`, `FieldLabel`, `FieldDescription`) | `add field` | shadcn ships a real Field primitive now — drop the custom wrapper. `{label, hint, children}` → `FieldLabel` + `FieldDescription` + children. |
| `Empty` | `components/ui/empty.tsx` (`Empty`, `EmptyHeader`, `EmptyTitle`, `EmptyDescription`) | `add empty` | shadcn ships this now — drop the custom wrapper. `{title, hint}` → `EmptyTitle` + `EmptyDescription`. `EmptyMedia`/icon not used (current usage has no icon). |
| `Spinner` | `components/ui/spinner.tsx` (shadcn) + thin `components/Spinner.tsx` wrapper | `add spinner` | shadcn's Spinner is icon-only (`lucide-react` `LoaderIcon` + `animate-spin`). Current component also renders an i18n "loading" label (`useTranslations("common")`), so keep a 2-line wrapper: shadcn's `<Spinner />` icon + the translated label text next to it. |
| `Chip` | `components/Chip.tsx`, built on `components/ui/badge.tsx` | `add badge` | Badge's own `variant` enum (`default/secondary/destructive/outline/ghost/link`) has no tone semantics. shadcn's docs officially sanction custom soft-tone colors via plain `className` (`bg-emerald-50 text-emerald-700`, etc.) — exactly the existing tone pattern. Keep `Chip` as a small `cva` wrapper over `Badge` for the 5 tones (`neutral/up/down/warn/info`). Stays outside `components/ui/`. |
| `StatusBadge` | `components/StatusBadge.tsx`, built on `components/ui/badge.tsx` | (reuses `add badge`) | Same reasoning as Chip — domain `Status` union + `useTranslations("vocab.status")` stays in a dedicated wrapper, not a shadcn-owned file. |
| `PageHeader` | `components/PageHeader.tsx` | — | No shadcn equivalent (pure layout convenience). Stays fully custom, unchanged, just relocated out of `ui.tsx`. |

Plus the 3 existing raw-Radix usage sites move onto shadcn's wrappers instead
of importing `@radix-ui/react-*` directly:

| File | Raw import today | New import |
|---|---|---|
| `app/[locale]/customisation/page.tsx` | `import * as Tabs from "@radix-ui/react-tabs"` | `components/ui/tabs.tsx` (`add tabs`) |
| `components/RangeDrawer.tsx` | `import * as Dialog from "@radix-ui/react-dialog"` | `components/ui/dialog.tsx` (`add dialog`) |
| `components/DataSourceStatus.tsx` | `import * as Popover from "@radix-ui/react-popover"` | `components/ui/popover.tsx` (`add popover`) |

`@radix-ui/react-tooltip` is installed but has no current usage site — not
pulled in via `add tooltip` unless/until something needs it.

`components/ui.tsx` is deleted once all 9 exports have moved.

## Consumer migration

16 files currently import from `components/ui.tsx` (15 via the `@/components/ui`
alias, one — `components/RangeDrawer.tsx` — via the relative `./ui` path):

```
app/[locale]/settings/page.tsx                    (Card, PageHeader)
app/[locale]/settings/activity/page.tsx           (Card, Empty, PageHeader, Spinner, StatusBadge, inputClass)
app/[locale]/settings/market-sources/page.tsx     (PageHeader)
app/[locale]/settings/data/page.tsx               (Card, Chip, PageHeader, Spinner)
app/[locale]/rate/page.tsx                        (Card, Empty, PageHeader, Spinner, inputClass)
app/[locale]/customisation/page.tsx               (PageHeader) — also raw Tabs import
app/[locale]/market/page.tsx                      (PageHeader)
components/RoomTypeMapPanel.tsx                   (Button, Card)
components/DataSourcePanel.tsx                    (Card, Chip)
components/RangeDrawer.tsx                        (Button) — also raw Dialog import
components/customisation/StrategyPanel.tsx        (Button, Card, Chip, Field, PageHeader, Spinner, inputClass)
components/market/EventsPanel.tsx                 (Button, Card, Chip, Empty, Field, PageHeader, Spinner, inputClass)
components/customisation/SeasonalPanel.tsx        (Button, Card, Chip, Spinner, inputClass)
components/market/MarketOverview.tsx              (Card, Spinner)
components/market/RawObservations.tsx             (Button, Card, Chip, Empty, Field, PageHeader, Spinner, inputClass)
components/market/CompetitorList.tsx              (Button, Card, Chip, Empty, Field, Spinner, inputClass)
```

`components/DataSourceStatus.tsx` has no `ui.tsx` import but needs its raw
Popover import migrated.

Each consumer needs, per import used:
- **Card**: import path change only (`@/components/ui/card`), same simple
  usage (`<Card className>{children}</Card>` — shadcn's Card accepts
  `className` and children directly; no compound `CardHeader`/`CardContent`
  restructuring required since current usage doesn't use them).
- **Button**: import path change + `variant`/`size` prop value rename per the
  mapping table (`primary→default`, `danger→destructive`, `md→default`).
- **inputClass**: replace `<input className={inputClass} .../>` with
  `<Input .../>` from `@/components/ui/input` (JSX element change, not just
  an import rename).
- **Field**: replace `<Field label={..} hint={..}>{children}</Field>` with
  `<Field><FieldLabel>{..}</FieldLabel>{children}<FieldDescription>{..}</FieldDescription></Field>` from `@/components/ui/field` (structural JSX
  change).
- **Empty**: replace `<Empty title={..} hint={..} />` with
  `<Empty><EmptyHeader><EmptyTitle>{..}</EmptyTitle><EmptyDescription>{..}</EmptyDescription></EmptyHeader></Empty>` from `@/components/ui/empty`
  (structural JSX change).
- **Spinner**: import path change to the new `@/components/Spinner` wrapper;
  call-site usage (`<Spinner label={..} />`) unchanged.
- **Chip**, **StatusBadge**, **PageHeader**: import path change only
  (`@/components/Chip`, `@/components/StatusBadge`, `@/components/PageHeader`)
  — same props, same call sites.

This means the migration is **not a pure find-and-replace on imports** —
`Button`, `inputClass`→`Input`, `Field`, and `Empty` call sites need their JSX
updated to the new shapes. `Card`, `Chip`, `StatusBadge`, `PageHeader`,
`Spinner` are import-path-only changes.

## Out of scope (explicitly deferred)

- Retinting the 21 files (350 occurrences) that use `ink-*`/`brand-*`
  Tailwind classes directly — untouched, will look visually inconsistent
  against the newly-migrated stock-themed components until the later
  redesign pass.
- `components/viz.tsx` (`PaceChart` and friends) and
  `components/market/MarketOverview.tsx` — both use Recharts directly with
  hand-coded colors/tooltips. shadcn's `chart` component (`ChartContainer`,
  `ChartTooltipContent`, `ChartConfig`) is a compatible wrapper around the
  same Recharts primitives already in use, and is the natural target for the
  later redesign — but re-theming those charts now would be redesign work,
  not plumbing.
- shadcn **blocks** (login/dashboard/sidebar page assemblies) — not
  applicable; every route here already has a bespoke domain layout, blocks
  are for scaffolding generic new pages.
- Dark mode.
- `@radix-ui/react-tooltip` — installed, unused, not pulled into
  `components/ui/` unless a future consumer needs it.

## Testing / verification plan

No test framework exists in `apps/web`. Verification is:

1. `npm run build` (`next build`) — catches TypeScript errors across every
   touched file (strict mode, `noUnusedLocals`/`noUnusedParameters` will flag
   stale imports left behind by the `ui.tsx` deletion).
2. Manual browser pass over every route that consumes a migrated component:
   `/[locale]/rate`, `/[locale]/market`, `/[locale]/customisation`,
   `/[locale]/settings`, `/[locale]/settings/activity`,
   `/[locale]/settings/data`, `/[locale]/settings/market-sources` — confirm
   buttons, cards, badges/chips, empty states, spinners, the customisation
   Tabs, the Rate page's range Dialog, and the Nav's DataSourceStatus Popover
   all render and function. The stock-palette visual seam (noted above) is
   expected, not a bug.
