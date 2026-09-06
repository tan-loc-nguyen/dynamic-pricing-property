import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithIntl } from "../test-utils";
import { SeasonalPanel } from "./SeasonalPanel";
import type { RateBand, SeasonDef } from "@/lib/types";

const season = (key: string, label: string, months: number[]): SeasonDef => ({
  key,
  label,
  months,
});

const band = (id: number, seasonKey: string): RateBand =>
  ({
    id,
    season_key: seasonKey,
    season_label: seasonKey,
    room_category: "2br_regular",
    min_net_rate: 1_800_000,
    base_net_rate: 2_100_000,
    max_net_rate: 2_300_000,
    currency: "VND",
    rate_basis: "NET",
    source: "CLIENT_VALIDATED",
  }) as RateBand;

let seasons: SeasonDef[];
const saveSeasons = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    seasons: () => Promise.resolve({ seasons }),
    // Mirrors the server: every season has a band per room category,
    // including one just added — which is what _seed_bands_for_new_seasons
    // guarantees.
    rateBook: () => Promise.resolve(seasons.map((s, i) => band(i + 1, s.key))),
    saveSeasons: (next: SeasonDef[]) => {
      saveSeasons(next);
      seasons = next;
      // The server answers with the calendar it stored, and the panel reloads
      // from it — the same round trip the real one makes.
      return Promise.resolve({ seasons: next });
    },
    updateRateBand: () => Promise.resolve({}),
    resetRateBook: () => Promise.resolve({}),
  },
}));

describe("SeasonalPanel", () => {
  beforeEach(() => {
    seasons = [
      season("low_1", "Low 1", [5, 6]),
      season("high_1", "High 1", [7, 8, 9, 10, 11, 12, 1, 2, 3, 4]),
    ];
    saveSeasons.mockClear();
  });

  it("keeps the seasons on screen while a save refreshes", async () => {
    // The panel used to swap its whole body for a spinner on every refetch,
    // which unmounted the list and threw the reader back to the top of the
    // page mid-edit.
    renderWithIntl(<SeasonalPanel />);
    const add = await screen.findByRole("button", { name: /add a season/i });
    const rateFields = screen.getAllByRole("textbox").length;
    await userEvent.click(add);
    // The list must never blank out mid-save: the fields stay mounted right
    // through the reload that follows.
    expect(screen.getAllByRole("textbox").length).toBeGreaterThanOrEqual(rateFields);
    await waitFor(() => expect(saveSeasons).toHaveBeenCalled());
    expect(screen.getAllByRole("textbox").length).toBeGreaterThanOrEqual(rateFields);
  });

  it("focuses a rate field of the season it just added", async () => {
    // A new season arrives with rates carried over from the one it split, so
    // the next thing to do is type over them. Landing the caret there is the
    // difference between that and hunting for the card after a re-render.
    renderWithIntl(<SeasonalPanel />);
    await userEvent.click(await screen.findByRole("button", { name: /add a season/i }));
    await waitFor(() => {
      expect(document.activeElement).toBeInstanceOf(HTMLInputElement);
      expect((document.activeElement as HTMLInputElement).inputMode).toBe("numeric");
    });
  });
});
