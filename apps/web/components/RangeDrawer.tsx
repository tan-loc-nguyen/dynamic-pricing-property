"use client";

// The drawer moved into its own directory when it gained a second scope: one
// shell around two bodies, rather than a mode conditional inside every
// section. This re-export keeps the import path every caller already uses.
export { RangeDrawer, type RangeSelection } from "./rangeDrawer/RangeDrawerShell";
