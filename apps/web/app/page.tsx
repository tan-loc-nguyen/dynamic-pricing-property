import { redirect } from "next/navigation";
import { routing } from "@/i18n/routing";

/** Bare "/" has no locale segment; send it to the default one. */
export default function RootPage() {
  redirect(`/${routing.defaultLocale}`);
}
