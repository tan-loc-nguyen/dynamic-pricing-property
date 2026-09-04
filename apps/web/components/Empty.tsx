import { Inbox } from "lucide-react";
import {
  Empty as ShadEmpty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
} from "@/components/ui/empty";

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <ShadEmpty>
      <EmptyHeader>
        {/* One consistent icon for every empty state in the app, rather than a
            different glyph per context -- restraint over per-case decoration. */}
        <EmptyMedia variant="icon">
          <Inbox aria-hidden size={18} strokeWidth={1.5} />
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        {hint && <EmptyDescription>{hint}</EmptyDescription>}
      </EmptyHeader>
    </ShadEmpty>
  );
}
