import { useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";

const STATUS_CLASSES: Record<string, string> = {
  pending: "bg-amber-50 text-amber-700 border-amber-200",
  accepted: "bg-emerald-50 text-emerald-700 border-emerald-200",
  overridden: "bg-violet-50 text-violet-700 border-violet-200",
  error: "bg-rose-50 text-rose-700 border-rose-200",
};
// status -> message key. The English used to live here; it lives in the
// message files now, so the badge reads the same word the rest of the UI does.
const STATUS_LABELS: Record<string, string> = {
  pending: "pending",
  accepted: "accepted",
  overridden: "overridden",
  error: "error",
};

export function StatusBadge({ status }: { status: string }) {
  // vocab.status, which is the canonical set. A separate top-level `status`
  // namespace held a duplicate of these AND the data-source strings, so the two
  // unrelated ideas shared a prefix and neither owned it.
  const t = useTranslations("vocab.status");
  return (
    <Badge
      variant="outline"
      data-status={status}
      className={STATUS_CLASSES[status] || "bg-ink-100 text-ink-600 border-ink-200"}
    >
      {STATUS_LABELS[status] ? t(STATUS_LABELS[status]) : status}
    </Badge>
  );
}
