// Light/dark mode: follows the system setting until the user picks one with the toggle;
// the pick is saved in localStorage and wins from then on.

import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

function savedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null; // storage can be blocked (for example in some private windows)
  }
}

function systemTheme(): Theme {
  return window.matchMedia?.(DARK_QUERY).matches ? "dark" : "light";
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => savedTheme() ?? systemTheme());

  // Every time the theme changes, put it on <html>; tokens.css swaps the colors.
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  // While the user has not chosen, follow the system when it switches (e.g. at sunset).
  useEffect(() => {
    const media = window.matchMedia?.(DARK_QUERY);
    if (!media) return;
    const onChange = () => {
      if (!savedTheme()) setTheme(media.matches ? "dark" : "light");
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange); // clean up when unmounted
  }, []);

  function toggleTheme() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // not saved, but the switch still works for this visit
    }
    setTheme(next);
  }

  return { theme, toggleTheme };
}
