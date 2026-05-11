"use client";

import { useEffect, useRef } from "react";

type Props = {
  state: "idle" | "recording" | "processing";
  onRecord: () => void;
  onStop: () => void;
  getLevel: () => number | null;
};

const SIZE = 88;

export default function RecordButton({ state, onRecord, onStop, getLevel }: Props) {
  const ringRef  = useRef<HTMLSpanElement>(null);
  const ring2Ref = useRef<HTMLSpanElement>(null);
  const rafRef   = useRef<number>(0);

  useEffect(() => {
    if (state !== "recording") {
      cancelAnimationFrame(rafRef.current);
      ringRef.current?.style.setProperty("--lvl", "0");
      ring2Ref.current?.style.setProperty("--lvl", "0");
      return;
    }
    const tick = () => {
      const lvl = getLevel() ?? 0;
      ringRef.current?.style.setProperty("--lvl", String(lvl));
      ring2Ref.current?.style.setProperty("--lvl", String(lvl));
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [state, getLevel]);

  return (
    <div className="relative flex items-center justify-center" style={{ width: SIZE + 44, height: SIZE + 44 }}>
      {/* Outer voice rings — recording only */}
      {state === "recording" && (
        <>
          <span
            ref={ringRef}
            className="record-ring"
            style={{ "--lvl": "0", inset: -14 } as React.CSSProperties}
          />
          <span
            ref={ring2Ref}
            className="record-ring record-ring-2"
            style={{ "--lvl": "0", inset: -26 } as React.CSSProperties}
          />
        </>
      )}

      {/* Idle invitation pulse */}
      {state === "idle" && (
        <span className="record-invite" style={{ inset: -4 }} />
      )}

      <button
        data-state={state}
        className="record-btn relative flex flex-col items-center justify-center gap-1.5"
        style={{
          width: SIZE,
          height: SIZE,
          borderRadius: "50%",
          color: state === "processing" ? "var(--ink-4)" : "var(--bg)",
          flexShrink: 0,
        }}
        onClick={state === "idle" ? onRecord : state === "recording" ? onStop : undefined}
        disabled={state === "processing"}
        aria-label={
          state === "idle" ? "Start recording" :
          state === "recording" ? "Stop recording" :
          "Analyzing…"
        }
      >
        {/* Icon */}
        {state === "idle" && <MicIcon />}
        {state === "recording" && <StopIcon />}
        {state === "processing" && (
          <span
            className="spin"
            style={{
              display: "block",
              width: 20, height: 20,
              borderRadius: "50%",
              border: "2.5px solid var(--line-2)",
              borderTopColor: "var(--ink-3)",
            }}
          />
        )}

        {/* Label */}
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", lineHeight: 1 }}>
          {state === "idle" && "Record"}
          {state === "recording" && "Stop"}
          {state === "processing" && ""}
        </span>
      </button>
    </div>
  );
}

function MicIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="2" width="6" height="11" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0" />
      <line x1="12" y1="19" x2="12" y2="22" />
      <line x1="8"  y1="22" x2="16" y2="22" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
      <rect x="4" y="4" width="16" height="16" rx="3" />
    </svg>
  );
}
