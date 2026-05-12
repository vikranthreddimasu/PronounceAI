"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Accent } from "@/lib/types";
import { convertAccent } from "@/lib/api";
import { cloneAccent, speakInVoice, type VoiceProfile } from "@/lib/voiceProfile";

type Mode = "native" | "personal";

type Props = {
  userAudio: Blob | null;
  accent: Accent;
  /** Profile loaded from /api/voice/<id>. Null when no enrollment. */
  voiceProfile: VoiceProfile | null;
  /** Known target phrase; lets personal mode skip ASR and hit speculative voice cache. */
  overrideText?: string;
  /** Triggered when the user wants to (re-)enroll. */
  onOpenEnrollment: () => void;
};

const ACCENT_NAME: Record<Accent, string> = {
  GA: "American",
  RP: "British RP",
};

const MODE_DESC: Record<Mode, { title: string; sub: string }> = {
  native: {
    title: "Native speaker",
    sub: "Words rendered in a native speaker's voice. Fast.",
  },
  personal: {
    title: "Your voice",
    sub: "Your timbre with the target accent locked in.",
  },
};

export default function AccentConvertCard({
  userAudio,
  accent,
  voiceProfile,
  overrideText,
  onOpenEnrollment,
}: Props) {
  const [mode, setMode] = useState<Mode>(voiceProfile ? "personal" : "native");
  const [state, setState] = useState<"idle" | "converting" | "ready" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [convertedUrl, setConvertedUrl] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Reset whenever inputs change.
  useEffect(() => {
    setState("idle");
    setErrorMsg(null);
    if (convertedUrl) {
      URL.revokeObjectURL(convertedUrl);
      setConvertedUrl(null);
    }
    setIsPlaying(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userAudio, accent, mode]);

  // If profile appears/disappears, sync mode reasonably.
  useEffect(() => {
    if (!voiceProfile && mode === "personal") setMode("native");
  }, [voiceProfile, mode]);

  useEffect(() => () => {
    if (convertedUrl) URL.revokeObjectURL(convertedUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleConvert = useCallback(async () => {
    if (!userAudio || state === "converting") return;
    setState("converting");
    setErrorMsg(null);
    try {
      let blob: Blob;
      if (mode === "personal") {
        if (!voiceProfile) throw new Error("Set up your voice first.");
        if (overrideText?.trim()) {
          blob = (await speakInVoice(
            voiceProfile.user_id,
            overrideText,
            accent,
            voiceProfile.revision,
            "target_accent"
          )).audio;
        } else {
          blob = await cloneAccent(userAudio, accent, voiceProfile.user_id);
        }
      } else {
        blob = await convertAccent(userAudio, accent);
      }
      const url = URL.createObjectURL(blob);
      setConvertedUrl(url);
      setState("ready");
      if (!audioRef.current) audioRef.current = new Audio();
      audioRef.current.src = url;
      audioRef.current.onended = () => setIsPlaying(false);
      audioRef.current.onerror = () => setIsPlaying(false);
      setIsPlaying(true);
      audioRef.current.play().catch(() => setIsPlaying(false));
    } catch (e) {
      setErrorMsg((e as Error).message ?? "Could not convert");
      setState("error");
    }
  }, [userAudio, accent, mode, voiceProfile, overrideText, state]);

  const handleReplay = useCallback(() => {
    if (!convertedUrl) return;
    if (!audioRef.current) audioRef.current = new Audio();
    audioRef.current.src = convertedUrl;
    audioRef.current.currentTime = 0;
    audioRef.current.onended = () => setIsPlaying(false);
    audioRef.current.onerror = () => setIsPlaying(false);
    setIsPlaying(true);
    audioRef.current.play().catch(() => setIsPlaying(false));
  }, [convertedUrl]);

  if (!userAudio) return null;

  const isConverting = state === "converting";
  const isReady = state === "ready";
  const desc = MODE_DESC[mode];

  return (
    <div
      className="rounded-2xl fade-pop"
      style={{
        padding: 18,
        background: "var(--surface)",
        border: "1px solid var(--line)",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {isConverting && (
        <div
          className="shimmer-bar"
          aria-hidden
          style={{ position: "absolute", inset: 0, opacity: 0.35, pointerEvents: "none" }}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between" style={{ marginBottom: 10, position: "relative" }}>
        <div>
          <div
            className="text-xs uppercase tracking-wider"
            style={{ color: "var(--ink-3)", letterSpacing: "0.08em" }}
          >
            Accent conversion · {ACCENT_NAME[accent]}
          </div>
          <div className="text-sm font-semibold" style={{ color: "var(--ink)", marginTop: 2 }}>
            {desc.title}
          </div>
        </div>

        {isReady ? (
          <button
            className="press rounded-full text-xs font-semibold"
            style={{
              padding: "9px 16px",
              background: isPlaying ? "var(--surface-2)" : "var(--accent)",
              color: isPlaying ? "var(--ink-2)" : "var(--bg)",
              border: isPlaying ? "1px solid var(--line)" : "none",
              transition: "all 220ms var(--ease-out)",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
            }}
            onClick={handleReplay}
          >
            <span
              aria-hidden
              style={{
                width: 0,
                height: 0,
                borderLeft: `7px solid ${isPlaying ? "var(--ink-2)" : "var(--bg)"}`,
                borderTop: "5px solid transparent",
                borderBottom: "5px solid transparent",
                display: "inline-block",
                animation: isPlaying ? "glyph-bob 1.4s ease-in-out infinite" : undefined,
              }}
            />
            {isPlaying ? "Playing" : "Replay"}
          </button>
        ) : (
          <button
            className="press rounded-full text-xs font-semibold"
            style={{
              padding: "9px 16px",
              background: isConverting
                ? "var(--surface-2)"
                : "linear-gradient(160deg, var(--accent-soft), var(--accent))",
              color: isConverting ? "var(--ink-3)" : "var(--bg)",
              border: isConverting ? "1px solid var(--line)" : "none",
              opacity: isConverting ? 0.85 : 1,
              transition: "all 220ms var(--ease-out)",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
            }}
            disabled={isConverting || (mode === "personal" && !voiceProfile)}
            onClick={handleConvert}
          >
            {isConverting && (
              <span
                aria-hidden
                className="spin"
                style={{
                  width: 10,
                  height: 10,
                  border: "1.5px solid var(--ink-3)",
                  borderTopColor: "transparent",
                  borderRadius: "50%",
                  display: "inline-block",
                }}
              />
            )}
            {isConverting ? "Converting" : "Convert"}
          </button>
        )}
      </div>

      <p
        className="text-xs leading-snug"
        style={{ color: state === "error" ? "var(--rose)" : "var(--ink-3)", position: "relative", minHeight: 16 }}
      >
        {state === "error"
          ? errorMsg
          : isConverting
          ? mode === "personal"
            ? "Locking the target accent to your voice..."
            : "Mapping your speech into the target accent..."
          : isReady
          ? "Compare it with your original above."
          : desc.sub}
      </p>

      {/* Mode switcher */}
      <div
        className="flex items-center gap-0.5 rounded-lg"
        style={{ background: "var(--bg-2)", padding: 3, marginTop: 12, border: "1px solid var(--line)" }}
      >
        <ModeBtn
          label="Native speaker"
          active={mode === "native"}
          onClick={() => setMode("native")}
        />
        <ModeBtn
          label={voiceProfile ? "Your voice" : "Your voice"}
          active={mode === "personal"}
          onClick={() => {
            if (voiceProfile) setMode("personal");
            else onOpenEnrollment();
          }}
        />
      </div>

      {/* Enrollment CTA when not yet enrolled */}
      {!voiceProfile && (
        <button
          className="press hover-accent"
          onClick={onOpenEnrollment}
          style={{
            marginTop: 10,
            width: "100%",
            padding: "9px 0",
            borderRadius: 10,
            background: "transparent",
            border: "1px dashed var(--line-2, var(--line))",
            color: "var(--ink-3)",
            fontSize: 12,
            fontWeight: 500,
            transition: "all 200ms var(--ease-out)",
          }}
        >
          Set up your voice to hear this accent in your own timbre
        </button>
      )}
    </div>
  );
}

function ModeBtn({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className="press text-xs font-semibold"
      onClick={onClick}
      style={{
        flex: 1,
        padding: "7px 0",
        borderRadius: 8,
        background: active ? "var(--surface-2)" : "transparent",
        color: active ? "var(--ink)" : "var(--ink-4)",
        border: active ? "1px solid var(--line)" : "1px solid transparent",
        transition: "all 220ms var(--ease-out)",
      }}
    >
      {label}
    </button>
  );
}
