// The sidebar's width and whether it is collapsed, on wide screens.
// Both are saved in localStorage, so the layout is the same after a reload.
// (Narrow screens ignore both: there the sidebar is a drawer.)

import { useState } from "react";

export const SIDEBAR_MIN = 220;
export const SIDEBAR_MAX = 480;
export const SIDEBAR_DEFAULT = 288; // the same as --sidebar-width in tokens.css

const WIDTH_KEY = "sidebar-width";
const COLLAPSED_KEY = "sidebar-collapsed";

/** Keep a width between the minimum and the maximum, in whole pixels. */
export function clampWidth(width: number): number {
  return Math.round(Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, width)));
}

// Storage can be blocked or broken (some private windows, full storage), and then
// every access throws. The layout still works; it is just not remembered.
function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // not saved, but the change still works for this visit
  }
}

function savedWidth(): number {
  const value = Number(read(WIDTH_KEY));
  return Number.isFinite(value) && value > 0 ? clampWidth(value) : SIDEBAR_DEFAULT;
}

export function useSidebarLayout() {
  const [width, setWidthState] = useState(savedWidth);
  const [collapsed, setCollapsedState] = useState(() => read(COLLAPSED_KEY) === "true");

  function setWidth(next: number) {
    const clamped = clampWidth(next);
    setWidthState(clamped);
    write(WIDTH_KEY, String(clamped));
  }

  function setCollapsed(next: boolean) {
    setCollapsedState(next);
    write(COLLAPSED_KEY, String(next));
  }

  return { width, setWidth, collapsed, setCollapsed };
}
