import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach } from "vitest";
import { stopRestartWaits } from "../lib/restartWait";
import { resetSessionDrafts } from "../studio/storage";

beforeAll(() => {
  // jsdom lacks the pointer and scroll APIs that Radix Select calls.
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => undefined;
  Element.prototype.releasePointerCapture = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

beforeEach(() => {
  resetSessionDrafts();
  window.localStorage.clear();
  window.history.replaceState(null, "", "/");
  delete document.documentElement.dataset.theme;
});

afterEach(() => {
  cleanup();
  // A restart wait polls for up to 90 s; it must not outlive its test page.
  stopRestartWaits();
});
