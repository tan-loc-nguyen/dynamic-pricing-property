import type { Recommendation } from "./types";

/**
 * Which dates are worth looking at.
 *
 * The previous UI showed 93 nights as a flat list and left the operator to
 * find the interesting ones. This answers "where do I look first?".
 *
 * Every reason is DERIVED from fields the engine already publishes — nothing
 * here re-implements pricing, and nothing invents a signal. A date with no
 * reason is genuinely unremarkable, which is the point: if everything is
 * flagged, nothing is.
 */

export type AttentionReason = "bigChange" | "wellBehind" | "surging";

/**
 * Percentage move in the recommended rate that is worth a second look.
 *
 * Calibrated against the actual distribution rather than picked: at 5% this
 * fired on 154 of 270 rows — 57% of the calendar, which is the same as
 * flagging nothing. At 8% it is 39 rows. An alert every operator learns to
 * ignore is worse than no alert.
 */
const MATERIAL_CHANGE_PCT = 8;
/** Pace gap, in fractions of occupancy, that counts as badly behind. */
const BADLY_BEHIND_GAP = -0.2;

export function attentionReasons(rec: Recommendation): AttentionReason[] {
  const reasons: AttentionReason[] = [];

  if (Math.abs(rec.change_pct ?? 0) >= MATERIAL_CHANGE_PCT) reasons.push("bigChange");
  if ((rec.pace_gap ?? 0) <= BADLY_BEHIND_GAP) reasons.push("wellBehind");
  // The engine names the band; this does not re-derive it from thresholds (D28).
  if (rec.pickup_label_key?.endsWith("surging")) reasons.push("surging");
  // Deliberately NOT reasons to flag a night:
  //   - an event, which already carries its own marker on the cell and has
  //     usually been priced in rather than left for the operator to fix;
  //   - market evidence found and ignored for low confidence, explained in the
  //     drawer and needing no action;
  //   - a CLAMP. The dynamic layer tried to leave the validated band and the
  //     band stopped it: that is the design working, it is already explained by
  //     its own row in the breakdown, and there is nothing to do about it. It
  //     was also the largest single reason (40 of 81), and the density that
  //     matters is per COLUMN, not per row — a column flags if any of three
  //     room types does. Including clamps put an amber dot on 53% of the
  //     calendar; without them it is 37%.

  return reasons;
}

export function needsAttention(rec: Recommendation): boolean {
  return attentionReasons(rec).length > 0;
}

/** Ranked, so "7 nights need attention" opens the most urgent one first. */
const WEIGHT: Record<AttentionReason, number> = {
  wellBehind: 4,
  bigChange: 3,
  surging: 2,
};

export function attentionScore(rec: Recommendation): number {
  return attentionReasons(rec).reduce((total, r) => total + WEIGHT[r], 0);
}
