"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Rate Review", hint: "Recommendations to action" },
  { href: "/rate-book", label: "Rate Book", hint: "Validated seasonal rates" },
  { href: "/settings", label: "Dynamic Rules", hint: "Experimental layer" },
  { href: "/market", label: "Market", hint: "Comp set & evidence" },
  { href: "/events", label: "Events", hint: "Demand calendar" },
  { href: "/history", label: "History", hint: "Past decisions" },
];

export function Nav() {
  const pathname = usePathname();

  return (
    <aside className="w-60 shrink-0 border-r border-ink-200 bg-white flex flex-col">
      <div className="px-5 py-5 border-b border-ink-100">
        <div className="flex items-center gap-2.5">
          <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 grid place-items-center text-white text-sm font-semibold">
            D
          </div>
          <div className="min-w-0">
            <div className="text-[13px] font-semibold leading-tight text-ink-900">Dynamic Pricing</div>
            {/* The operator whose portfolio is being priced. */}
            <div className="text-[11px] text-ink-500 leading-tight">Luminous Luxury Apartments</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 p-3 space-y-0.5">
        {LINKS.map((link) => {
          const active = pathname === link.href;
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`block rounded-lg px-3 py-2 transition-colors ${
                active ? "bg-brand-50 text-brand-700" : "text-ink-600 hover:bg-ink-50 hover:text-ink-900"
              }`}
            >
              <div className="text-[13px] font-medium leading-tight">{link.label}</div>
              <div className={`text-[11px] leading-tight mt-0.5 ${active ? "text-brand-500" : "text-ink-400"}`}>
                {link.hint}
              </div>
            </Link>
          );
        })}
      </nav>

      <div className="p-3 border-t border-ink-100 space-y-2">
        <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2.5">
          <div className="text-[11px] font-semibold text-emerald-900 leading-tight">Shadow Mode</div>
          <div className="text-[11px] text-emerald-700 leading-snug mt-1">
            Recommendations only. Nothing is pushed to Blue Jay or any OTA.
          </div>
        </div>
        <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2.5">
          <div className="text-[11px] font-semibold text-amber-900 leading-tight">
            Dynamic layer unvalidated
          </div>
          <div className="text-[11px] text-amber-700 leading-snug mt-1">
            Seasonal NET rates are client-validated. Pace, pickup, event and market settings are not.
          </div>
        </div>
      </div>
    </aside>
  );
}
