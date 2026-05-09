"use client";

import { useEffect, useRef, useState } from "react";

export type RecorderState = "idle" | "recording" | "processing";

export function RecordButton(props: {
  state: RecorderState;
  onToggle: () => void;
  getLevel: () => number | null;
}) {
  // Remount the inner shell every time we drop back to idle so any timer
  // state resets cleanly without an effect that resets state.
  return <RecordButtonInner key={props.state === "idle" ? "idle" : "active"} {...props} />;
}

function RecordButtonInner({
  state,
  onToggle,
  getLevel,
}: {
  state: RecorderState;
  onToggle: () => void;
  getLevel: () => number | null;
}) {
  const ringRef = useRef<HTMLSpanElement | null>(null);
  const ring2Ref = useRef<HTMLSpanElement | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    if (state !== "recording") return;
    const start = performance.now();
    let raf = 0;
    const tick = () => {
      const lvl = getLevel() ?? 0;
      ringRef.current?.style.setProperty("--lvl", String(lvl));
      ring2Ref.current?.style.setProperty("--lvl", String(lvl));
      setElapsedMs(performance.now() - start);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [state, getLevel]);

  const label =
    state === "recording" ? "Stop recording" :
    state === "processing" ? "Analyzing" :
    "Start recording";

  const helper =
    state === "recording" ? "Tap to finish" :
    state === "processing" ? "Listening to your audio…" :
    "Tap and read the phrase aloud";

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="relative">
        {state === "recording" ? (
          <>
            <span ref={ring2Ref} className="record-ring record-ring-2" aria-hidden />
            <span ref={ringRef} className="record-ring" aria-hidden />
          </>
        ) : null}
        {state === "idle" ? <span className="record-invite" aria-hidden /> : null}

        <button
          type="button"
          onClick={onToggle}
          disabled={state === "processing"}
          aria-label={label}
          aria-pressed={state === "recording"}
          data-state={state}
          className="record-btn relative grid h-[112px] w-[112px] cursor-pointer place-items-center rounded-full disabled:cursor-wait disabled:opacity-95"
        >
          <ButtonGlyph state={state} />
        </button>
      </div>

      <div className="flex min-h-[1.25rem] flex-col items-center gap-0.5">
        <p className="text-[13px] text-ink-2" aria-live="polite">
          {state === "recording" ? (
            <span className="inline-flex items-center gap-2 font-medium text-warn">
              <span className="rec-dot block h-1.5 w-1.5 rounded-full bg-warn" />
              Recording · <span className="tabular-nums">{formatTime(elapsedMs)}</span>
            </span>
          ) : (
            helper
          )}
        </p>
      </div>
    </div>
  );
}

function ButtonGlyph({ state }: { state: RecorderState }) {
  if (state === "recording") {
    return <span className="block h-7 w-7 rounded-[7px] bg-white/95" aria-hidden />;
  }
  if (state === "processing") {
    return (
      <svg width="30" height="30" viewBox="0 0 32 32" className="spin text-ink-2" aria-hidden>
        <circle cx="16" cy="16" r="12" stroke="currentColor" strokeWidth="2.5" fill="none" opacity="0.18" />
        <path
          d="M28 16a12 12 0 0 0-12-12"
          stroke="currentColor"
          strokeWidth="2.5"
          fill="none"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  return (
    <svg width="36" height="36" viewBox="0 0 36 36" className="text-bg" aria-hidden>
      <rect x="13" y="6" width="10" height="18" rx="5" fill="currentColor" />
      <path
        d="M9 18a9 9 0 0 0 18 0M18 27v4M14 31h8"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

function formatTime(ms: number) {
  const total = Math.max(0, Math.floor(ms));
  const sec = Math.floor(total / 1000);
  const cs = Math.floor((total % 1000) / 100);
  const ss = sec % 60;
  const mm = Math.floor(sec / 60);
  return `${pad(mm)}:${pad(ss)}.${cs}`;
}

function pad(n: number) {
  return n.toString().padStart(2, "0");
}
