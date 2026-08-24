"use client";

import { useTranslations } from "next-intl";

import { Chip } from "./ui";
import type { SystemStatus } from "@/lib/types";

/**
 * Honest status. Shows what is validated, what is not, and which integrations
 * are degraded — rather than a silently-empty product.
 */
export function StatusBanner({ status }: { status: SystemStatus | null }) {
  const t = useTranslations("banner");
  if (!status) return null;

  const pmsDegraded = !status.pms.healthy;
  const marketDegraded = !status.market.healthy;

  return (
    <div className="flex flex-wrap items-center gap-2 text-[11.5px]">
      <Chip tone="up" title={t("shadowTitle")}>
        {t("shadowMode")}
      </Chip>
      <Chip tone="up" title={t("rateBookTitle", { count: status.rate_book.bands })}>
        {t("rateBookValidated")}
      </Chip>
      <Chip
        tone="warn"
        title={status.booking_curve.note || t("demoCurve")}
      >
        {t("bookingCurveDemo")}
      </Chip>
      <Chip tone={status.demo_mode ? "info" : "neutral"} title={status.pms.detail}>
        {status.demo_mode ? t("demoData") : t("pms", { mode: status.pms.mode })}
      </Chip>
      {pmsDegraded && (
        <Chip tone="warn" title={status.pms.detail}>
          {t("blueJayUnavailable")}
        </Chip>
      )}
      <Chip tone={marketDegraded ? "warn" : "neutral"} title={status.market.detail}>
        {t("market", { mode: status.market.mode })}
      </Chip>
      <Chip tone="neutral">{t("engine", { version: status.engine.version })}</Chip>
      <Chip tone="neutral">{t("rules", { version: status.config_version })}</Chip>
      {/* Outcome readiness. Deliberately a status chip, not an analytics screen:
          the operator needs to know whether the evaluation dataset is real yet,
          and elaborate analytics is an explicit non-goal for this phase. */}
      <Chip
        tone={status.outcome_readiness?.ready_for_evaluation ? "up" : "warn"}
        title={String(status.outcome_readiness?.note || "")}
      >
        {t("outcomes", { real: status.outcome_readiness?.real_outcomes ?? 0 })}
        {(status.outcome_readiness?.synthetic_outcomes ?? 0) > 0 &&
          t("outcomesSynthetic", { count: status.outcome_readiness.synthetic_outcomes })}
      </Chip>
      {(pmsDegraded || marketDegraded) && (
        <span className="text-ink-400">
          {pmsDegraded ? status.pms.remediation : status.market.remediation}
        </span>
      )}
    </div>
  );
}
