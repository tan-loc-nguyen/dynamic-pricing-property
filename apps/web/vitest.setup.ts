import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

// jsdom has no layout engine, so it implements no scrolling at all and leaves
// `scrollIntoView` undefined. A component that keeps the selected item on
// screen would otherwise have to guard against the test environment in its own
// source, which is the wrong place for that knowledge.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

afterEach(() => {
  cleanup();
});
