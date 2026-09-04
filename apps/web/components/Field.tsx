import type { ReactNode } from "react";
import {
  Field as ShadField,
  FieldLabel,
  FieldDescription,
} from "@/components/ui/field";

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <ShadField>
      {/* The label wraps the control (rather than sibling + htmlFor/id, shadcn's
          documented pattern) so every call site keeps its native label<->control
          association for free, with no per-field id to plumb through. */}
      <FieldLabel className="w-full flex-col items-start gap-1.5">
        {label}
        {children}
      </FieldLabel>
      {hint && <FieldDescription>{hint}</FieldDescription>}
    </ShadField>
  );
}
