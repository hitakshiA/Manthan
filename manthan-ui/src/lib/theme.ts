/**
 * Theme - dark | light, persisted in localStorage, applied via
 * `<html data-theme="…">`. No system-preference fallback: the user opts in
 * explicitly. Default is dark (the editorial direction).
 */

import { useEffect, useState } from "react";

export type Theme = "dark" | "light";

const STORAGE_KEY = "manthan.theme";

export function getStoredTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  const v = window.localStorage.getItem(STORAGE_KEY);
  return v === "light" ? "light" : "dark";
}

export function applyTheme(theme: Theme): void {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", theme);
  window.localStorage.setItem(STORAGE_KEY, theme);
}

/** Apply the persisted theme as early as possible during boot. */
export function bootTheme(): void {
  applyTheme(getStoredTheme());
}

/** React hook - read + set theme. */
export function useTheme(): [Theme, (next: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(getStoredTheme);
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);
  return [theme, setTheme];
}

/**
 * Force a specific theme while a component is mounted, without touching
 * the user's stored preference. Used by Landing / Login / Signup which
 * are designed around dark only - if the operator switched the
 * workspace to light, we still want the marketing + auth pages to look
 * the way they were designed.
 *
 * On unmount, restores whatever `data-theme` was on the document before
 * we touched it (NOT the stored preference - so if the user toggles
 * theme inside `/app`, leaving `/app` and coming back keeps the toggle).
 */
export function useLockedTheme(theme: Theme): void {
  useEffect(() => {
    if (typeof document === "undefined") return;
    const root = document.documentElement;
    const previous = root.getAttribute("data-theme") ?? "dark";
    root.setAttribute("data-theme", theme);
    return () => {
      root.setAttribute("data-theme", previous);
    };
  }, [theme]);
}
