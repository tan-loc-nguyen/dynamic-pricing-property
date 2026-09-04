import {
  Empty as ShadEmpty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
} from "@/components/ui/empty";

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <ShadEmpty>
      <EmptyHeader>
        <EmptyTitle>{title}</EmptyTitle>
        {hint && <EmptyDescription>{hint}</EmptyDescription>}
      </EmptyHeader>
    </ShadEmpty>
  );
}
