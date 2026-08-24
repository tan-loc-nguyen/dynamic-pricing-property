/**
 * Pass-through root layout.
 *
 * The real <html>/<body> live in `[locale]/layout.tsx`, because the `lang`
 * attribute depends on the locale segment. Next still requires a root layout to
 * exist for the bare "/" route, and next-intl's documented shape for that is a
 * layout that renders nothing but its children.
 */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}
