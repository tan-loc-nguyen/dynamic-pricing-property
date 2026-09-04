import type { ReactElement } from "react";
import { NextIntlClientProvider } from "next-intl";
import { render } from "@testing-library/react";
import en from "@/messages/en.json";

export function renderWithIntl(ui: ReactElement) {
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      {ui}
    </NextIntlClientProvider>
  );
}
