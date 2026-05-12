"use client";

import { useEffect, useRef, useState } from "react";
import type { WordTiming } from "@/lib/voiceProfile";

type Props = {
  words: WordTiming[];
  /** The HTMLAudioElement currently playing (or paused / not yet started). */
  audio: HTMLAudioElement | null;
  /** Whether audio is currently playing. Drives the RAF loop. */
  playing: boolean;
  /** Sizing hint: "lg" for hero phrase, "md" default. */
  size?: "md" | "lg";
};

/**
 * Renders `words` as inline spans synced to `audio.currentTime`.
 *
 * - Unspoken words: muted (var(--ink-4)).
 * - Active word: accent color, bold, slight scale.
 * - Spoken words: ink color (normal weight).
 * - Progress bar underneath traces playback through the text span.
 */
export default function SpokenText({ words, audio, playing, size = "md" }: Props) {
  const [activeIdx, setActiveIdx] = useState(-1);
  const [progress, setProgress] = useState(0);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (!audio || !playing || words.length === 0) {
      cancelAnimationFrame(rafRef.current ?? 0);
      // Snap progress to full when ended, reset when stopped
      if (!playing) {
        if (audio && audio.currentTime > 0 && audio.duration && audio.currentTime >= audio.duration - 0.05) {
          setProgress(1);
        } else if (audio && audio.paused && audio.currentTime === 0) {
          setActiveIdx(-1);
          setProgress(0);
        }
      }
      return;
    }

    const totalMs = words[words.length - 1].end_ms;
    let lastIdx = -1;

    const tick = () => {
      if (!audio) return;
      const t = audio.currentTime * 1000;
      // Advance from lastIdx for amortized O(1) word lookup.
      let idx = lastIdx;
      while (idx + 1 < words.length && t >= words[idx + 1].start_ms) {
        idx++;
      }
      if (idx >= 0 && t > words[idx].end_ms + 50 && idx + 1 < words.length && t < words[idx + 1].start_ms) {
        // Between words: keep highlighting the just-spoken one
        // (looks better than a flicker to "nothing").
      }
      if (idx !== lastIdx) {
        lastIdx = idx;
        setActiveIdx(idx);
      }
      setProgress(totalMs > 0 ? Math.min(1, t / totalMs) : 0);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current ?? 0);
  }, [audio, playing, words]);

  // Reset when words change (new synthesis)
  useEffect(() => {
    setActiveIdx(-1);
    setProgress(0);
  }, [words]);

  if (words.length === 0) return null;

  const fontSize = size === "lg" ? 22 : 17;
  const lineHeight = size === "lg" ? 1.35 : 1.5;

  return (
    <div>
      <p
        className="font-display"
        style={{
          fontSize,
          fontWeight: 500,
          color: "var(--ink-4)",
          lineHeight,
          letterSpacing: 0,
          margin: 0,
        }}
        aria-live="polite"
      >
        {words.map((w, i) => {
          const isActive = i === activeIdx;
          const isSpoken = i < activeIdx;
          const color = isActive
            ? "var(--accent)"
            : isSpoken
            ? "var(--ink)"
            : "var(--ink-4)";
          const weight = isActive ? 700 : isSpoken ? 500 : 400;
          return (
            <span
              key={`${i}-${w.start_ms}`}
              style={{
                color,
                fontWeight: weight,
                transition: "color 100ms var(--ease-out), font-weight 100ms var(--ease-out)",
                display: "inline",
              }}
            >
              {w.word}
            </span>
          );
        })}
      </p>
      <div
        className="dim-track"
        style={{ height: 3, marginTop: 14 }}
        aria-hidden
      >
        <div
          style={{
            width: `${progress * 100}%`,
            height: "100%",
            background: "var(--accent)",
            borderRadius: 9999,
            transition: "width 80ms linear",
          }}
        />
      </div>
    </div>
  );
}
