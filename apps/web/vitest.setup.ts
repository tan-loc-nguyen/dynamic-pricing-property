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

// jsdom implements no media queries, so anything asking whether it is on a
// small screen -- shadcn's Sidebar does, to decide between the rail and a
// mobile sheet -- gets no matchMedia at all. Answering "not mobile" keeps the
// desktop path under test, which is the only path this product supports.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

afterEach(() => {
  cleanup();
});
