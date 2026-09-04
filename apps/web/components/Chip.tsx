import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const TONE_CLASSES: Record<string, string> = {
  neutral: "bg-ink-100 text-ink-600",
  up: "bg-emerald-50 text-emerald-700",
  down: "bg-rose-50 text-rose-700",
  warn: "bg-amber-50 text-amber-700",
  info: "bg-sky-50 text-sky-700",
};

export function Chip({
  children,
  tone = "neutral",
  title,
}: {
  children: ReactNode;
  tone?: "neutral" | "up" | "down" | "warn" | "info";
  title?: string;
}) {
  return (
    <Badge
      variant="secondary"
      size="sm"
      title={title}
      data-tone={tone}
      className={cn("rounded-md", TONE_CLASSES[tone])}
    >
      {children}
    </Badge>
  );
}
