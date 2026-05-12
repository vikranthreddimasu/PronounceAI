"use client";

import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { PitchContour } from "@/lib/types";

type Props = {
  contour: PitchContour;
  /** Plays the native reference audio. Resolves when playback ends. */
  onPlayNative: () => Promise<void>;
  /** Plays the user recording. Resolves when playback ends. */
  onPlayUser: () => Promise<void> | void;
  hasUserAudio: boolean;
};

const VIEW_W = 480;
const VIEW_H = 120;
const PAD_X = 10;
const PAD_Y = 18;

/** SVG path; null = pen-up (unvoiced break). */
function buildPath(values: (number | null)[], yMin: number, yMax: number): string {
  const n = values.length;
  if (n === 0) return "";
  const stepX = (VIEW_W - PAD_X * 2) / (n - 1);
  const range = yMax - yMin || 1;
  let d = "";
  let penUp = true;
  for (let i = 0; i < n; i++) {
    const v = values[i];
    if (v == null) {
      penUp = true;
      continue;
    }
    const x = PAD_X + i * stepX;
    const y = PAD_Y + (VIEW_H - PAD_Y * 2) * (1 - (v - yMin) / range);
    d += `${penUp ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)} `;
    penUp = false;
  }
  return d.trim();
}

/** Area-fill path: same shape as curve, but closes to baseline so we can fill it. */
function buildAreaPath(values: (number | null)[], yMin: number, yMax: number): string {
  const n = values.length;
  if (n === 0) return "";
  const stepX = (VIEW_W - PAD_X * 2) / (n - 1);
  const range = yMax - yMin || 1;
  const baselineY = VIEW_H - PAD_Y;
  let d = "";
  let segStartX: number | null = null;
  let lastX = 0;
  let penUp = true;
  for (let i = 0; i < n; i++) {
    const v = values[i];
    if (v == null) {
      if (!penUp && segStartX != null) {
        d += `L${lastX.toFixed(2)} ${baselineY} L${segStartX.toFixed(2)} ${baselineY} Z `;
      }
      penUp = true;
      segStartX = null;
      continue;
    }
    const x = PAD_X + i * stepX;
    const y = PAD_Y + (VIEW_H - PAD_Y * 2) * (1 - (v - yMin) / range);
    if (penUp) {
      d += `M${x.toFixed(2)} ${baselineY} L${x.toFixed(2)} ${y.toFixed(2)} `;
      segStartX = x;
    } else {
      d += `L${x.toFixed(2)} ${y.toFixed(2)} `;
    }
    lastX = x;
    penUp = false;
  }
  if (!penUp && segStartX != null) {
    d += `L${lastX.toFixed(2)} ${baselineY} L${segStartX.toFixed(2)} ${baselineY} Z`;
  }
  return d.trim();
}

/** Approx the path length used for stroke-dashoffset draw-in (no DOM measure). */
function approxPathLength(values: (number | null)[]): number {
  const stepX = (VIEW_W - PAD_X * 2) / (values.length - 1 || 1);
  let len = 0;
  for (let i = 1; i < values.length; i++) {
    if (values[i] != null && values[i - 1] != null) len += stepX;
  }
  return Math.max(len, 80);
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export default function PitchContourOverlay({
  contour,
  onPlayNative,
  onPlayUser,
  hasUserAudio,
}: Props) {
  const [playing, setPlaying] = useState<"none" | "native" | "user">("none");
  const [playhead, setPlayhead] = useState(0); // 0..1
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const rafRef = useRef<number | null>(null);
  const startedAtRef = useRef<number>(0);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const gradId = useId();

  // Shared y-axis so the curves are comparable.
  const { yMin, yMax } = useMemo(() => {
    const all: number[] = [];
    for (const v of contour.native) if (v != null) all.push(v);
    for (const v of contour.user) if (v != null) all.push(v);
    if (all.length === 0) return { yMin: -1, yMax: 1 };
    const lo = Math.min(...all);
    const hi = Math.max(...all);
    const pad = (hi - lo) * 0.15 || 0.5;
    return { yMin: lo - pad, yMax: hi + pad };
  }, [contour]);

  const nativePath = useMemo(
    () => buildPath(contour.native, yMin, yMax),
    [contour.native, yMin, yMax]
  );
  const userPath = useMemo(
    () => buildPath(contour.user, yMin, yMax),
    [contour.user, yMin, yMax]
  );
  const nativeArea = useMemo(
    () => buildAreaPath(contour.native, yMin, yMax),
    [contour.native, yMin, yMax]
  );
  const userArea = useMemo(
    () => buildAreaPath(contour.user, yMin, yMax),
    [contour.user, yMin, yMax]
  );

  // ── Draw-in animation ──────────────────────────────────────────────────
  const [drawProgress, setDrawProgress] = useState(0); // 0..1
  const nativeLen = useMemo(() => approxPathLength(contour.native), [contour.native]);
  const userLen = useMemo(() => approxPathLength(contour.user), [contour.user]);

  useLayoutEffect(() => {
    if (prefersReducedMotion()) {
      setDrawProgress(1);
      return;
    }
    setDrawProgress(0);
    const start = performance.now();
    const duration = 900;
    let rafId: number;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - t, 3);
      setDrawProgress(eased);
      if (t < 1) rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [nativePath, userPath]);

  // ── Playhead RAF ───────────────────────────────────────────────────────
  const playbackMs = Math.max(800, contour.duration_ms);

  function startPlayhead() {
    startedAtRef.current = performance.now();
    const tick = () => {
      const elapsed = performance.now() - startedAtRef.current;
      const t = Math.min(1, elapsed / playbackMs);
      setPlayhead(t);
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }
  function stopPlayhead() {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    setPlayhead(0);
  }
  useEffect(() => () => { if (rafRef.current != null) cancelAnimationFrame(rafRef.current); }, []);

  async function play(which: "native" | "user") {
    if (playing !== "none") return;
    setPlaying(which);
    startPlayhead();
    try {
      if (which === "native") await onPlayNative();
      else await onPlayUser();
    } finally {
      stopPlayhead();
      setPlaying("none");
    }
  }

  // ── Hover ──────────────────────────────────────────────────────────────
  function handleMove(e: React.PointerEvent<SVGSVGElement>) {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const xNorm = (e.clientX - rect.left) / rect.width;
    const idx = Math.round(xNorm * (contour.native.length - 1));
    if (idx >= 0 && idx < contour.native.length) setHoverIdx(idx);
  }
  function handleLeave() { setHoverIdx(null); }

  const headX = PAD_X + (VIEW_W - PAD_X * 2) * playhead;
  const hoverX =
    hoverIdx == null
      ? 0
      : PAD_X + ((VIEW_W - PAD_X * 2) / (contour.native.length - 1)) * hoverIdx;
  const hoverNative = hoverIdx != null ? contour.native[hoverIdx] : null;
  const hoverUser = hoverIdx != null ? contour.user[hoverIdx] : null;
  const hoverTimeMs = hoverIdx != null
    ? Math.round((hoverIdx / (contour.native.length - 1)) * contour.duration_ms)
    : 0;

  // 3 grid lines: -1σ, 0, +1σ (z-score)
  const gridYs = useMemo(() => {
    const range = yMax - yMin || 1;
    return [-1, 0, 1].map((z) => PAD_Y + (VIEW_H - PAD_Y * 2) * (1 - (z - yMin) / range));
  }, [yMin, yMax]);

  return (
    <div className="result-enter w-full">
      <p
        className="mb-3 text-xs font-medium uppercase tracking-widest"
        style={{ color: "var(--ink-4)" }}
      >
        Pitch contour
      </p>

      <div
        style={{
          padding: "16px 0",
          borderRadius: 0,
          background: "transparent",
          borderTop: "1px solid var(--rule)",
          borderBottom: "1px solid var(--rule)",
          position: "relative",
          overflow: "hidden",
        }}
      >
        <svg
          ref={svgRef}
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          width="100%"
          height={VIEW_H + 8}
          preserveAspectRatio="none"
          style={{ display: "block", touchAction: "none" }}
          onPointerMove={handleMove}
          onPointerLeave={handleLeave}
          aria-label="Native pitch contour overlaid with your pitch contour"
        >
          <defs>
            <linearGradient id={`${gradId}-jade`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--jade)" stopOpacity="0.32" />
              <stop offset="100%" stopColor="var(--jade)" stopOpacity="0" />
            </linearGradient>
            <linearGradient id={`${gradId}-rose`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--rose)" stopOpacity="0.28" />
              <stop offset="100%" stopColor="var(--rose)" stopOpacity="0" />
            </linearGradient>
            <filter id={`${gradId}-glow`} x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="2.5" />
            </filter>
          </defs>

          {/* Grid (z-score reference lines) */}
          {gridYs.map((y, i) => (
            <line
              key={i}
              x1={PAD_X}
              x2={VIEW_W - PAD_X}
              y1={y}
              y2={y}
              stroke="var(--line)"
              strokeWidth={0.7}
              strokeDasharray={i === 1 ? "0" : "2 5"}
              opacity={i === 1 ? 0.5 : 0.32}
            />
          ))}

          {/* Area fills fade in with the draw. */}
          <g opacity={drawProgress}>
            <path d={nativeArea} fill={`url(#${gradId}-jade)`} />
            <path d={userArea} fill={`url(#${gradId}-rose)`} />
          </g>

          {/* Native contour draws in first. */}
          <path
            d={nativePath}
            fill="none"
            stroke="var(--jade)"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity={0.96}
            strokeDasharray={nativeLen}
            strokeDashoffset={nativeLen * (1 - drawProgress)}
          />

          {/* User contour draws in slightly behind. */}
          <path
            d={userPath}
            fill="none"
            stroke="var(--rose)"
            strokeWidth={1.8}
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity={0.93}
            strokeDasharray={userLen}
            strokeDashoffset={userLen * (1 - Math.max(0, drawProgress * 1.15 - 0.15))}
          />

          {/* Hover crosshair */}
          {hoverIdx != null && playing === "none" && (
            <g pointerEvents="none">
              <line
                x1={hoverX}
                x2={hoverX}
                y1={PAD_Y - 4}
                y2={VIEW_H - PAD_Y + 4}
                stroke="var(--ink-4)"
                strokeWidth={0.8}
                opacity={0.4}
              />
              {hoverNative != null && (
                <circle
                  cx={hoverX}
                  cy={PAD_Y + (VIEW_H - PAD_Y * 2) * (1 - (hoverNative - yMin) / (yMax - yMin))}
                  r={3}
                  fill="var(--jade)"
                />
              )}
              {hoverUser != null && (
                <circle
                  cx={hoverX}
                  cy={PAD_Y + (VIEW_H - PAD_Y * 2) * (1 - (hoverUser - yMin) / (yMax - yMin))}
                  r={3}
                  fill="var(--rose)"
                />
              )}
            </g>
          )}

          {/* Playhead line and dot at the active curve. */}
          {playing !== "none" && (() => {
            const idx = Math.round(playhead * (contour.native.length - 1));
            const series = playing === "native" ? contour.native : contour.user;
            const v = series[idx];
            const tone = playing === "native" ? "var(--jade)" : "var(--rose)";
            const dotY =
              v == null
                ? null
                : PAD_Y + (VIEW_H - PAD_Y * 2) * (1 - (v - yMin) / (yMax - yMin));
            return (
              <g pointerEvents="none">
                <line
                  x1={headX}
                  x2={headX}
                  y1={PAD_Y - 4}
                  y2={VIEW_H - PAD_Y + 4}
                  stroke={tone}
                  strokeWidth={1.6}
                  opacity={0.55}
                />
                {dotY != null && (
                  <>
                    <circle cx={headX} cy={dotY} r={7} fill={tone} opacity={0.22} filter={`url(#${gradId}-glow)`} />
                    <circle cx={headX} cy={dotY} r={3.4} fill={tone} />
                  </>
                )}
              </g>
            );
          })()}
        </svg>

        {/* Hover tooltip positioned over the SVG. */}
        {hoverIdx != null && playing === "none" && (
          <div
            style={{
              position: "absolute",
              top: 8,
              right: 12,
              fontSize: 10,
              color: "var(--ink-3)",
              background: "var(--bg)",
              border: "1px solid var(--line)",
              borderRadius: 0,
              padding: "4px 8px",
              fontVariantNumeric: "tabular-nums",
              pointerEvents: "none",
            }}
          >
            {hoverTimeMs}ms ·{" "}
            <span style={{ color: "var(--jade)" }}>
              {hoverNative == null ? "n/a" : hoverNative.toFixed(2)}σ
            </span>{" "}
            ·{" "}
            <span style={{ color: "var(--rose)" }}>
              {hoverUser == null ? "n/a" : hoverUser.toFixed(2)}σ
            </span>
          </div>
        )}

        {/* Legend + actions */}
        <div className="flex items-center justify-between" style={{ marginTop: 8 }}>
          <div className="flex gap-3" style={{ fontSize: 10, color: "var(--ink-4)" }}>
            <span className="flex items-center gap-1.5">
              <span style={{ width: 12, height: 2, background: "var(--jade)", borderRadius: 2 }} />
              Native
            </span>
            <span className="flex items-center gap-1.5">
              <span style={{ width: 12, height: 2, background: "var(--rose)", borderRadius: 2 }} />
              You
            </span>
          </div>

          <div className="flex gap-1">
            <ContourPlayBtn
              label="Native"
              active={playing === "native"}
              disabled={playing !== "none"}
              tone="jade"
              onClick={() => play("native")}
            />
            <ContourPlayBtn
              label="You"
              active={playing === "user"}
              disabled={playing !== "none" || !hasUserAudio}
              tone="rose"
              onClick={() => play("user")}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function ContourPlayBtn({
  label,
  active,
  disabled,
  tone,
  onClick,
}: {
  label: string;
  active: boolean;
  disabled: boolean;
  tone: "jade" | "rose";
  onClick: () => void;
}) {
  const color = tone === "jade" ? "var(--jade)" : "var(--rose)";
  return (
    <button
      className="press"
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "6px 12px",
        borderRadius: 0,
        fontFamily: "var(--type-sans)",
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: "0.14em",
        textTransform: "uppercase",
        background: active ? color : "transparent",
        border: `1px solid ${active ? color : "var(--rule)"}`,
        color: active ? "var(--paper)" : "var(--ink)",
        opacity: disabled && !active ? 0.4 : 1,
        cursor: disabled ? "default" : "pointer",
        transition: "background-color 180ms var(--ease-out), color 180ms var(--ease-out), border-color 180ms var(--ease-out), opacity 180ms var(--ease-out)",
        position: "relative",
      }}
    >
      <span
        aria-hidden
        style={{
          width: 0,
          height: 0,
          borderLeft: `6px solid ${active ? color : "var(--ink-4)"}`,
          borderTop: "4px solid transparent",
          borderBottom: "4px solid transparent",
          marginRight: 6,
          display: "inline-block",
          animation: active ? "contour-pulse 1.4s ease-in-out infinite" : undefined,
        }}
      />
      {label}
      <style jsx>{`
        @keyframes contour-pulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.25); opacity: 0.7; }
        }
      `}</style>
    </button>
  );
}
