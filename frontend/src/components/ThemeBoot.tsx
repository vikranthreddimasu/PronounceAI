"use client";

import { useEffect } from "react";
import { getProfile } from "@/lib/store";

/**
 * Applies the stored theme to <html data-theme="..."> on mount.
 * Runs once, no flicker because the default light palette is the SSR'd one.
 */
export default function ThemeBoot() {
  useEffect(() => {
    const p = getProfile();
    const root = document.documentElement;
    const resolved =
      p.theme === "system"
        ? window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light"
        : p.theme;
    root.setAttribute("data-theme", resolved);
  }, []);
  return null;
}
