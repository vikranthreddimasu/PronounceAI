"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PhonemeResult } from "@/lib/types";

type Props = {
  phonemes: PhonemeResult[];
  /** Plays the full native reference. Resolves when ended. */
  onPlayNative: () => Promise<void>;
  /** Plays the user's full recording. Resolves when ended. */
  onPlayUser: () => Promise<void> | void;
  hasUserAudio: boolean;
};

type Step = "idle" | "native-1" | "user" | "native-2";

/**
 * Pick the worst phoneme: lowest gop among incorrect, else lowest gop overall.
 * Returns null if there's nothing meaningfully wrong.
 */
function pickWorst(phonemes: PhonemeResult[]): PhonemeResult | null {
  if (phonemes.length === 0) return null;
  const errs = phonemes.filter((p) => !p.correct);
  const pool = errs.length > 0 ? errs : phonemes;
  let worst = pool[0];
  for (const p of pool) if (p.gop < worst.gop) worst = p;
  // If nothing is even marginal, skip the panel.
  if (worst.gop > -0.6) return null;
  return worst;
}

function totalDurationMs(phonemes: PhonemeResult[]): number {
  const last = phonemes[phonemes.length - 1];
  const first = phonemes[0];
  if (!last || !first) return 1500;
  return Math.max(800, last.end_ms - first.start_ms + 200);
}

export default function PhonemeABDiff({
  phonemes,
  onPlayNative,
  onPlayUser,
  hasUserAudio,
}: Props) {
  const worst = useMemo(() => pickWorst(phonemes), [phonemes]);
  const [step, setStep] = useState<Step>("idle");
  const cancelledRef = useRef(false);

  useEffect(() => () => { cancelledRef.current = true; }, []);

  const runLoop = useCallback(async () => {
    if (step !== "idle") return;
    cancelledRef.current = false;
    setStep("native-1");
    await onPlayNative();
    if (cancelledRef.current) return;
    if (hasUserAudio) {
      setStep("user");
      await onPlayUser();
      if (cancelledRef.current) return;
    }
    setStep("native-2");
    await onPlayNative();
    if (cancelledRef.current) return;
    setStep("idle");
  }, [step, onPlayNative, onPlayUser, hasUserAudio]);

  const playOnce = useCallback(
    async (which: "native" | "user") => {
      if (step !== "idle") return;
      setStep(which === "native" ? "native-1" : "user");
      try {
        if (which === "native") await onPlayNative();
        else await onPlayUser();
      } finally {
        if (!cancelledRef.current) setStep("idle");
      }
    },
    [step, onPlayNative, onPlayUser]
  );

  if (!worst) return null;

  const duration = totalDurationMs(phonemes);
  const startPct = Math.max(0, (worst.start_ms - phonemes[0].start_ms) / duration);
  const widthPct = Math.max(0.03, (worst.end_ms - worst.start_ms) / duration);

  const subFrom = worst.substitution?.split("→")[0];
  const subTo = worst.expected;

  return (
    <div className="result-enter w-full">
      <p
        className="mb-3 text-xs font-medium uppercase tracking-widest"
        style={{ color: "var(--ink-4)" }}
      >
        Hear the gap
      </p>

      <div
        style={{
          padding: "18px 0",
          borderRadius: 0,
          background: "transparent",
          borderTop: "1px solid var(--rule)",
          borderBottom: "1px solid var(--rule)",
        }}
      >
        {/* Worst phoneme IPA glyphs */}
        <div className="flex items-center gap-3" style={{ marginBottom: 14 }}>
          {subFrom ? (
            <>
              <PhonemeGlyph ipa={subFrom} tone="rose" label="you" />
              <span style={{ fontSize: 10, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                to
              </span>
              <PhonemeGlyph ipa={subTo} tone="jade" label="target" />
            </>
          ) : (
            <PhonemeGlyph ipa={worst.expected} tone="rose" label="weak" />
          )}
          <p
            style={{
              fontSize: 12,
              color: "var(--ink-3)",
              marginLeft: "auto",
              fontVariantNumeric: "tabular-nums",
            }}
          >
            at {(worst.start_ms / 1000).toFixed(1)}s
          </p>
        </div>

        {/* Zone track showing where the phoneme sits in the utterance. */}
        <div
          style={{
            position: "relative",
            height: 4,
            background: "var(--paper-3)",
            borderRadius: 0,
            overflow: "hidden",
            marginBottom: 14,
          }}
          aria-hidden
        >
          <div
            className="zone-pop"
            style={{
              position: "absolute",
              left: `${startPct * 100}%`,
              width: `${widthPct * 100}%`,
              top: 0,
              bottom: 0,
              background: "var(--accent)",
              opacity: 0.9,
              borderRadius: 0,
            }}
          />
        </div>

        {/* Three-step A/B/A row */}
        <div className="flex gap-2">
          <ABStepBtn
            label="Native"
            active={step === "native-1"}
            disabled={step !== "idle" && step !== "native-1"}
            tone="jade"
            index={1}
            onClick={() => playOnce("native")}
          />
          <ABStepBtn
            label="You"
            active={step === "user"}
            disabled={(step !== "idle" && step !== "user") || !hasUserAudio}
            tone="rose"
            index={2}
            onClick={() => playOnce("user")}
          />
          <ABStepBtn
            label="Native"
            active={step === "native-2"}
            disabled={step !== "idle" && step !== "native-2"}
            tone="jade"
            index={3}
            onClick={() => playOnce("native")}
          />
        </div>

        {/* Auto loop */}
        <button
          className="press hover-accent"
          onClick={runLoop}
          disabled={step !== "idle"}
          style={{
            marginTop: 10,
            width: "100%",
            padding: "9px 0",
            borderRadius: 0,
            background: "transparent",
            border: "1px solid var(--rule)",
            color: "var(--ink-3)",
            fontFamily: "var(--type-sans)",
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            opacity: step !== "idle" ? 0.5 : 1,
            transition: "background-color 180ms var(--ease-out), color 180ms var(--ease-out), border-color 180ms var(--ease-out), opacity 180ms var(--ease-out)",
          }}
        >
          {step === "idle" ? "Play native, you, native" : "Playing..."}
        </button>
      </div>
    </div>
  );
}

function PhonemeGlyph({
  ipa,
  tone,
  label,
}: {
  ipa: string;
  tone: "rose" | "jade";
  label: string;
}) {
  const color = tone === "rose" ? "var(--rose)" : "var(--jade)";
  return (
    <div className="flex flex-col items-center fade-pop" style={{ gap: 3 }}>
      <span
        style={{
          width: 44,
          height: 44,
          borderRadius: 0,
          background: "transparent",
          border: `1px solid ${color}`,
          color,
          fontFamily: "var(--type-mono)",
          fontSize: 20,
          fontWeight: 500,
          lineHeight: "42px",
          textAlign: "center",
          letterSpacing: 0,
        }}
      >
        {ipa}
      </span>
      <span
        style={{
          fontSize: 9,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--ink-4)",
        }}
      >
        {label}
      </span>
    </div>
  );
}

function ABStepBtn({
  label,
  active,
  disabled,
  tone,
  index,
  onClick,
}: {
  label: string;
  active: boolean;
  disabled: boolean;
  tone: "jade" | "rose";
  index: number;
  onClick: () => void;
}) {
  const color = tone === "jade" ? "var(--jade)" : "var(--rose)";
  return (
    <button
      className="press"
      onClick={onClick}
      disabled={disabled}
      style={{
        flex: 1,
        padding: "10px 0",
        borderRadius: 0,
        background: active ? color : "transparent",
        border: `1px solid ${active ? color : "var(--rule)"}`,
        color: active ? "var(--paper)" : "var(--ink)",
        fontFamily: "var(--type-sans)",
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: "0.14em",
        textTransform: "uppercase",
        opacity: disabled && !active ? 0.4 : 1,
        cursor: disabled ? "default" : "pointer",
        transition: "background-color 180ms var(--ease-out), color 180ms var(--ease-out), border-color 180ms var(--ease-out), opacity 180ms var(--ease-out)",
      }}
    >
      <span
        style={{
          display: "inline-block",
          width: 16,
          height: 16,
          borderRadius: 0,
          background: active ? "var(--paper)" : "transparent",
          color: active ? color : "var(--ink-4)",
          border: active ? "none" : "1px solid var(--rule)",
          fontFamily: "var(--type-mono)",
          fontSize: 10,
          fontWeight: 700,
          lineHeight: "16px",
          marginRight: 8,
          verticalAlign: "middle",
        }}
      >
        {index}
      </span>
      {label}
    </button>
  );
}
