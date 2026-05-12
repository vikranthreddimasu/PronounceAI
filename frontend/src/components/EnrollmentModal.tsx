"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createRecorder, type Recorder } from "@/lib/recorder";
import {
  addVoiceTake,
  ENROLLMENT_PROMPTS,
  getOrCreateVoiceId,
  type EnrollmentPrompt,
  type VoiceProfile,
} from "@/lib/voiceProfile";
import { tap, confirm, release } from "@/lib/sounds";

type Props = {
  open: boolean;
  onClose: () => void;
  onEnrolled: (profile: VoiceProfile) => void;
  /** Prompts to record. Defaults to one clean CosyVoice reference prompt. */
  prompts?: EnrollmentPrompt[];
};

type Step = "intro" | "recording" | "uploading" | "between" | "done" | "error";

const MIN_DURATION_S = 3;
const MAX_DURATION_S = 18;

export default function EnrollmentModal({
  open,
  onClose,
  onEnrolled,
  prompts: promptsProp,
}: Props) {
  const prompts = promptsProp ?? ENROLLMENT_PROMPTS;
  const [idx, setIdx] = useState(0);
  const [step, setStep] = useState<Step>("intro");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [profile, setProfile] = useState<VoiceProfile | null>(null);
  const recorderRef = useRef<Recorder | null>(null);
  const startRef = useRef<number>(0);
  const rafRef = useRef<number>(0);
  const closeTimerRef = useRef<number | null>(null);
  const stoppingRef = useRef(false);
  const stopAndUploadRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (closeTimerRef.current !== null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    if (open) {
      setIdx(0);
      setStep("intro");
      setErrorMsg(null);
      setElapsed(0);
      setProfile(null);
      stoppingRef.current = false;
    } else {
      recorderRef.current?.dispose();
      recorderRef.current = null;
      cancelAnimationFrame(rafRef.current);
    }
  }, [open]);

  useEffect(
    () => () => {
      recorderRef.current?.dispose();
      if (closeTimerRef.current !== null) window.clearTimeout(closeTimerRef.current);
    },
    []
  );

  const scheduleClose = useCallback(
    (delayMs: number) => {
      if (closeTimerRef.current !== null) window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = window.setTimeout(() => {
        closeTimerRef.current = null;
        onClose();
      }, delayMs);
    },
    [onClose]
  );

  const requestClose = useCallback(() => {
    if (step === "recording" || step === "uploading") return;
    onClose();
  }, [onClose, step]);

  const startRecord = useCallback(async () => {
    setErrorMsg(null);
    tap();
    try {
      if (!recorderRef.current) recorderRef.current = await createRecorder();
      await recorderRef.current.start();
      startRef.current = performance.now();
      setElapsed(0);
      const tick = () => {
        const e = (performance.now() - startRef.current) / 1000;
        setElapsed(e);
        if (e >= MAX_DURATION_S) {
          // Auto-stop if user goes too long
          stopAndUploadRef.current();
          return;
        }
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
      setStep("recording");
    } catch (e) {
      setErrorMsg((e as Error).message ?? "Couldn't access microphone.");
      setStep("error");
    }
  }, []);

  const stopAndUpload = useCallback(async () => {
    if (!recorderRef.current || stoppingRef.current) return;
    stoppingRef.current = true;
    cancelAnimationFrame(rafRef.current);
    release();
    setStep("uploading");
    try {
      const blob = await recorderRef.current.stop();
      const userId = getOrCreateVoiceId();
      const refText = prompts[idx].text;
      const updated = await addVoiceTake(userId, blob, refText);
      setProfile(updated);
      onEnrolled(updated);
      confirm();
      if (idx + 1 >= prompts.length) {
        setStep("done");
        scheduleClose(1100);
      } else {
        setStep("between");
      }
    } catch (e) {
      setErrorMsg((e as Error).message ?? "Upload failed.");
      setStep("error");
    } finally {
      stoppingRef.current = false;
    }
  }, [idx, prompts, onEnrolled, scheduleClose]);

  useEffect(() => {
    stopAndUploadRef.current = stopAndUpload;
  }, [stopAndUpload]);

  const nextPrompt = useCallback(() => {
    tap();
    setIdx((i) => Math.min(i + 1, prompts.length - 1));
    setStep("intro");
    setElapsed(0);
    setErrorMsg(null);
  }, [prompts.length]);

  const saveNow = useCallback(() => {
    tap();
    setStep("done");
    scheduleClose(600);
  }, [scheduleClose]);

  if (!open) return null;

  const current = prompts[idx];
  const lastTake = profile?.takes?.[profile.takes.length - 1];
  const isSinglePrompt = prompts.length === 1;

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) requestClose();
      }}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15, 12, 8, 0.55)",
        backdropFilter: "blur(10px)",
        WebkitBackdropFilter: "blur(10px)",
        zIndex: 50,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 20,
        animation: "fade-pop 220ms var(--ease-paper) both",
      }}
    >
      <div
        className="fade-pop card-paper"
        style={{
          width: "100%",
          maxWidth: 520,
          padding: 28,
          color: "var(--ink)",
        }}
      >
        {/* Header */}
        <div className="flex items-start justify-between" style={{ marginBottom: 14 }}>
          <div>
            <p
              className="font-mono"
              style={{
                fontSize: 10,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                color: "var(--accent)",
                fontWeight: 600,
              }}
            >
              {isSinglePrompt ? "Voice profile" : `Voice profile · take ${idx + 1} of ${prompts.length}`}
            </p>
            <h2
              className="font-display"
              style={{
                fontSize: 22,
                fontWeight: 700,
                marginTop: 4,
                color: "var(--ink)",
                letterSpacing: 0,
              }}
            >
              {current.label}
            </h2>
          </div>
          <button
            className="press"
            onClick={requestClose}
            disabled={step === "recording" || step === "uploading"}
            aria-label="Close"
            style={{
              width: 30,
              height: 30,
              borderRadius: 8,
              background: "var(--paper-2)",
              border: "1px solid var(--line)",
              color: "var(--ink-3)",
              fontSize: 16,
              lineHeight: 1,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              opacity: step === "recording" || step === "uploading" ? 0.45 : 1,
              cursor: step === "recording" || step === "uploading" ? "not-allowed" : "pointer",
            }}
          >
            <CloseIcon />
          </button>
        </div>

        {!isSinglePrompt && (
          <div className="flex" style={{ gap: 6, marginBottom: 18 }}>
            {prompts.map((p, i) => (
              <div
                key={p.id}
                style={{
                  flex: 1,
                  height: 4,
                  borderRadius: 9999,
                  background: i < idx ? "var(--jade)" : i === idx ? "var(--accent)" : "var(--paper-3)",
                  transition: "background 240ms var(--ease-paper)",
                }}
              />
            ))}
          </div>
        )}

        {/* Phrase card */}
        <div
          className="card-paper-inset"
          style={{ padding: "18px 20px", marginBottom: 14 }}
        >
          <p
            className="font-display"
            style={{
              fontSize: 18,
              fontWeight: 560,
              color: "var(--ink)",
              lineHeight: 1.45,
              letterSpacing: 0,
            }}
          >
            {current.text}
          </p>
          {current.hint && (
            <p
              style={{
                fontSize: 11,
                color: "var(--ink-4)",
                marginTop: 10,
                fontStyle: "italic",
              }}
            >
              {current.hint}
            </p>
          )}
        </div>

        {/* Step content */}
        {step === "intro" && (
          <>
            <p style={{ fontSize: 12.5, color: "var(--ink-3)", lineHeight: 1.55, marginBottom: 16 }}>
              Read it once in a quiet room. The exact text is saved with the audio so the local model can clone your voice reliably.
            </p>
            <button
              className="btn-paper btn-primary press"
              onClick={startRecord}
              style={{ width: "100%", padding: "13px 0", fontSize: 14 }}
            >
              Record voice sample
            </button>
            {idx > 0 && (
              <button
                className="btn-paper btn-ghost press"
                onClick={saveNow}
                style={{ width: "100%", marginTop: 8, fontSize: 12 }}
              >
                Save what I have ({idx} take{idx === 1 ? "" : "s"})
              </button>
            )}
          </>
        )}

        {step === "recording" && (
          <div className="flex flex-col items-center" style={{ gap: 14 }}>
            <div className="flex items-center" style={{ gap: 10, color: "var(--rose)", fontWeight: 600 }}>
              <span
                aria-hidden
                className="pulse-ring"
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  background: "var(--rose)",
                  color: "var(--rose)",
                  display: "inline-block",
                }}
              />
              <span className="font-mono" style={{ fontSize: 13, letterSpacing: 0 }}>
                Recording · {elapsed.toFixed(1)}s
              </span>
            </div>
            <button
              className="btn-paper press"
              onClick={stopAndUpload}
              disabled={elapsed < MIN_DURATION_S}
              style={{
                width: "100%",
                padding: "13px 0",
                fontSize: 14,
                background: elapsed < MIN_DURATION_S ? "var(--paper-2)" : "var(--ink)",
                color: elapsed < MIN_DURATION_S ? "var(--ink-3)" : "var(--paper)",
                borderColor: elapsed < MIN_DURATION_S ? "var(--line)" : "var(--ink)",
                opacity: elapsed < MIN_DURATION_S ? 0.7 : 1,
              }}
            >
              {elapsed < MIN_DURATION_S
                ? `Read for ${(MIN_DURATION_S - elapsed).toFixed(1)}s more`
                : "Save voice sample"}
            </button>
          </div>
        )}

        {step === "uploading" && (
          <div className="flex flex-col items-center" style={{ gap: 12, padding: "14px 0" }}>
            <span
              className="spin"
              style={{
                width: 26,
                height: 26,
                borderRadius: "50%",
                border: "2.5px solid var(--line)",
                borderTopColor: "var(--accent)",
                display: "block",
              }}
            />
            <p style={{ fontSize: 12, color: "var(--ink-3)" }}>Saving voice sample...</p>
          </div>
        )}

        {step === "between" && (
          <div className="flex flex-col" style={{ gap: 12, padding: "8px 0" }}>
            <div className="flex items-center" style={{ gap: 10, color: "var(--jade)" }}>
              <span
                aria-hidden
                style={{
                  width: 22, height: 22, borderRadius: "50%",
                  background: "rgba(74,138,107,0.15)",
                  border: "1.5px solid var(--jade)",
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                  fontSize: 11, fontWeight: 700,
                }}
              >
                ✓
              </span>
              <span style={{ fontSize: 13, color: "var(--ink-2)", fontWeight: 600 }}>
                Take {idx + 1} saved
                {lastTake && (
                  <span className="font-mono" style={{ fontSize: 11, color: "var(--ink-4)", marginLeft: 8 }}>
                    {lastTake.duration_s.toFixed(1)}s
                  </span>
                )}
              </span>
            </div>
            <button
              className="btn-paper btn-primary press"
              onClick={nextPrompt}
              style={{ width: "100%", padding: "12px 0", fontSize: 13 }}
            >
              Next: {prompts[idx + 1]?.label}
            </button>
            <button
              className="btn-paper btn-ghost press"
              onClick={saveNow}
              style={{ width: "100%", fontSize: 12 }}
            >
              Save what I have ({idx + 1} take{idx === 0 ? "" : "s"})
            </button>
          </div>
        )}

        {step === "done" && (
          <div
            className="fade-pop flex flex-col items-center"
            style={{ gap: 8, padding: "12px 0" }}
          >
            <div
              style={{
                width: 44,
                height: 44,
                borderRadius: "50%",
                background: "rgba(74,138,107,0.15)",
                border: "2px solid var(--jade)",
                color: "var(--jade)",
                fontSize: 22,
                fontWeight: 700,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              ✓
            </div>
            <p
              className="font-display"
              style={{ fontSize: 16, color: "var(--ink)", fontWeight: 700, letterSpacing: 0 }}
            >
              Voice ready
            </p>
            {profile && (
              <p className="font-mono" style={{ fontSize: 11, color: "var(--ink-4)", letterSpacing: 0 }}>
                {profile.takes.length} take{profile.takes.length === 1 ? "" : "s"} ·{" "}
                {profile.bundle_duration_s.toFixed(1)}s reference
              </p>
            )}
          </div>
        )}

        {step === "error" && (
          <div className="flex flex-col items-center" style={{ gap: 12 }}>
            <p
              style={{
                fontSize: 12.5,
                color: "var(--rose)",
                textAlign: "center",
                lineHeight: 1.5,
                background: "rgba(184,82,63,0.08)",
                border: "1px solid rgba(184,82,63,0.18)",
                padding: "10px 14px",
                borderRadius: 10,
                width: "100%",
              }}
            >
              {errorMsg ?? "Something went wrong."}
            </p>
            <button
              className="btn-paper press"
              onClick={() => {
                tap();
                stoppingRef.current = false;
                setStep("intro");
                setElapsed(0);
                setErrorMsg(null);
              }}
              style={{ fontSize: 13, padding: "10px 22px" }}
            >
              Try again
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function CloseIcon() {
  return (
    <svg
      aria-hidden
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
    >
      <path d="M6 6l12 12" />
      <path d="M18 6L6 18" />
    </svg>
  );
}
