// Runs before every test file (see vite.config.ts): adds the jest-dom matchers such as
// toBeInTheDocument(), stubs what the fake browser lacks, and cleans up after each test.

import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom (the fake browser) has no scrolling; ChatView calls this to scroll to the newest message.
Element.prototype.scrollIntoView = vi.fn();

afterEach(() => {
  cleanup(); // remove what the test rendered
  vi.restoreAllMocks(); // put the real api functions back
  localStorage.clear();
});
