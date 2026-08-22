"use client";

import { Chip } from "./ui";
import type { SystemStatus } from "@/lib/types";

/**
 * Honest integration status. If Blue Jay or market collection is degraded the
 * operator is told plainly, rather than being shown a silently-empty product.
 */
export function StatusBanner({ status }: { status: SystemStatus | null }) {
  if (!status) return null;

  const pmsDegraded = !status.pms.healthy;
  const marketDegraded = !status.market.healthy;

  return (
    <div className="flex flex-wrap items-center gap-2 text-[11.5px]">
      <Chip tone={status.demo_mode ? "info" : "up"}>
        {status.demo_mode ? "Demo data" : `PMS: ${status.pms.mode}`}
      </Chip>
      <Chip tone={pmsDegraded ? "warn" : "neutral"} title={status.pms.detail}>
        {status.pms.name.replace("PMSProvider", "")} {pmsDegraded ? "unavailable" : "connected"}
      </Chip>
      <Chip tone={marketDegraded ? "warn" : "neutral"} title={status.market.detail}>
        Market: {status.market.mode}
        {marketDegraded ? " (neutral factor)" : ""}
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
