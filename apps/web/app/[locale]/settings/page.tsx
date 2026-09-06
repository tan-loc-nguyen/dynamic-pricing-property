"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/PageHeader";
import { api } from "@/lib/api";

/**
 * Plumbing, and the only place an owner has to be deliberate to reach.
 *
 * The pricing inputs an operator tunes -- seasonal bands, strategy, events --
 * moved to Customisation. What is left here is setup and the audit trail.
 * Each entry says what it is FOR, not what it contains.
 *
 * "Connections & data" is ours, not theirs: which provider is wired up and
 * whether it answered is a question the operator has no way to act on. It
 * appears only when the SERVER says developer mode is on. That answer is
 * served rather than compiled in because the desktop build ships one static
 * bundle to every install (D32) -- a build-time flag would freeze it at
 * package time, and flipping it would mean shipping a different binary.
 */
const SECTIONS = [
  { href: "/settings/data", key: "data", devOnly: true },
  { href: "/settings/activity", key: "activity", devOnly: false },
] as const;

export default function SettingsPage() {
  const t = useTranslations("settingsHub");
  const locale = useLocale();
  const [devMode, setDevMode] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .status()
      .then((s) => alive && setDevMode(Boolean(s.dev_mode)))
      // Unreachable API means the developer section stays hidden. Failing
      // closed is the only safe direction for a surface the operator is not
      // meant to see.
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const visible = SECTIONS.filter((s) => !s.devOnly || devMode);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl">
        <PageHeader title={t("title")} subtitle={t("subtitle")} />

        <div className="mt-4 space-y-2">
          {visible.map((s) => (
            <Link
              key={s.href}
              href={`/${locale}${s.href}`}
              className="block rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            >
              <Card className="px-4 py-3 transition-colors hover:bg-ink-50">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[13.5px] font-medium text-ink-900">
                      {t(`${s.key}.title`)}
                    </div>
                    <div className="mt-0.5 text-[11.5px] text-ink-500">
                      {t(`${s.key}.hint`)}
                    </div>
                  </div>
                  <span className="shrink-0 rounded-full bg-amber-50 px-2 py-0.5 text-[10.5px] font-medium text-amber-700">
                    {t("experimental")}
                  </span>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
