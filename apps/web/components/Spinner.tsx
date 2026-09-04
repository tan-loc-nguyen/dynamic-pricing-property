import { useTranslations } from "next-intl";
import { Spinner as SpinnerIcon } from "@/components/ui/spinner";

export function Spinner({ label }: { label?: string }) {
  const t = useTranslations("common");
  return (
    <div className="py-16 text-center text-[13px] text-ink-400">
      <SpinnerIcon className="mr-2 inline-block align-middle" />
      {label ?? t("loading")}
    </div>
  );
}
