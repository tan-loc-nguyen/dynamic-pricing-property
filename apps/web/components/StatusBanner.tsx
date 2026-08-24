"use client";

import { Chip } from "./ui";
import type { SystemStatus } from "@/lib/types";

/**
 * Honest status. Shows what is validated, what is not, and which integrations
 * are degraded — rather than a silently-empty product.
 */
export function StatusBanner({ status }: { status: SystemStatus | null }) {
  if (!status) return null;

  const pmsDegraded = !status.pms.healthy;
  const marketDegraded = !status.market.healthy;

  return (
    <div className="flex flex-wrap items-center gap-2 text-[11.5px]">
      <Chip tone="up" title="Recommendations only — nothing is written to Blue Jay or any OTA.">
        Shadow Mode
      </Chip>
      <Chip tone="up" title={`${status.rate_book.bands} seasonal NET bands supplied by Luminous.`}>
        Rate book: client-validated
      </Chip>
      <Chip
        tone="warn"
        title={status.booking_curve.note || "Demo booking curve — not Luminous data."}
      >
        Booking curve: demo
      </Chip>
      <Chip tone={status.demo_mode ? "info" : "neutral"} title={status.pms.detail}>
        {status.demo_mode ? "Demo data" : `PMS: ${status.pms.mode}`}
      </Chip>
      {pmsDegraded && (
        <Chip tone="warn" title={status.pms.detail}>
          Blue Jay unavailable
        </Chip>
      )}
      <Chip tone={marketDegraded ? "warn" : "neutral"} title={status.market.detail}>
        Market: {status.market.mode}
      </Chip>
      <Chip tone="neutral">Engine {status.engine.version}</Chip>
      <Chip tone="neutral">Rules v{status.config_version}</Chip>
      {(pmsDegraded || marketDegraded) && (
        <span className="text-ink-400">
          {pmsDegraded ? status.pms.remediation : status.market.remediation}
        </span>
      )}
    </div>
  );
}
