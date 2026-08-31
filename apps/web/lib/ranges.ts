import type { Granularity } from "./buckets";

/**
 * The time spans an owner thinks in, defined once.
 *
 * The calendar and the market overview both offer these. Duplicating the list
 * would let them drift into offering different periods for the same question,
 * which is the sort of inconsistency nobody files a bug about and everybody
 * notices.
 */
export const RANGES = [
  { key: "twoWeeks", days: 14 },
  { key: "oneMonth", days: 30 },
  { key: "threeMonths", days: 91 },
  { key: "sixMonths", days: 182 },
] as const;

export type RangeKey = (typeof RANGES)[number]["key"];

/** Longest span that still reads night-by-night. Beyond it, weeks. */
export const DAY_RESOLUTION_LIMIT = 35;

export function granularityFor(days: number): Granularity {
  return days > DAY_RESOLUTION_LIMIT ? "week" : "day";
}

export function daysFor(key: string): number {
  return RANGES.find((r) => r.key === key)?.days ?? 30;
}
