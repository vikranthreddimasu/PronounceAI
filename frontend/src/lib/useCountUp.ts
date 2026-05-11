"use client";

import { useEffect, useState } from "react";

/**
 * Count from 0 to `value` over `durationMs` using easeOutCubic.
 * Respects prefers-reduced-motion (jumps straight to value).
 */
export function useCountUp(value: number, durationMs = 900, delayMs = 0): number {
  const [current, setCurrent] = useState(0);

  useEffect(() => {
    if (typeof window !== "undefined") {
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        setCurrent(value);
        return;
      }
    }
    let rafId: number;
    let cancelled = false;
    const startTimer = setTimeout(() => {
      const start = performance.now();
      const tick = (now: number) => {
        if (cancelled) return;
        const t = Math.min(1, (now - start) / durationMs);
        const eased = 1 - Math.pow(1 - t, 3);
        setCurrent(value * eased);
        if (t < 1) rafId = requestAnimationFrame(tick);
      };
      rafId = requestAnimationFrame(tick);
    }, delayMs);

    return () => {
      cancelled = true;
      clearTimeout(startTimer);
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, [value, durationMs, delayMs]);

  return current;
}
